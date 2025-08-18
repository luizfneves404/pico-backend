import logging
import random
import re
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Literal

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Request
from geoalchemy2 import WKTElement
from pydantic import AwareDatetime, BaseModel, TypeAdapter, ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import app.community.service as community_service
import app.mail as mail
import app.users.external_auth as external_auth
from app.countries.service import CountryNotFound, get_country
from app.education import service as education_service
from app.education.models import EducationInfo
from app.mail import send_password_reset_email
from app.redis_client import get_redis
from app.shared.validation import (
    LowercaseEmailStr,
    UnsetDefault,
    UsernameStr,
    phone_number_adapter,
)
from app.users.constants import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    DELETED_EMAIL,
    DELETED_PHONE_NUMBER,
    DELETED_USERNAME,
    NUM_RANKED_USERS,
    SENTINEL_USERNAMES,
    SOCIAL_SCORE_INCREMENT_BY_REFERRAL,
    WELCOME_EMAIL_MESSAGE,
    WELCOME_EMAIL_SUBJECT,
)
from app.users.exceptions import (
    AccountExistsError,
    EmailAlreadyExists,
    InvalidCountryCodeError,
    InvalidCourseIdError,
    InvalidCredentialsError,
    InvalidInstitutionIdError,
    InvalidLevelIdError,
    InvalidResetTokenError,
    InvalidStageIdError,
    InvalidTokenError,
    PhoneNumberAlreadyExists,
    ReferredByNotFoundError,
    SocialAuthError,
    UsernameAlreadyExists,
    UserNotFoundError,
)
from app.users.models import SignupSource, User
from app.users.schemas import EducationInfoIn, UserUpdate
from app.users.social import (
    check_contacts,
    get_ranking,
    search_username,
)
from app.users.utils import get_streak_info

logger = logging.getLogger(__name__)
__all__ = [
    # Exceptions
    "UserNotFoundError",
    "UsernameAlreadyExists",
    "PhoneNumberAlreadyExists",
    "EmailAlreadyExists",
    "ReferredByNotFoundError",
    "InvalidCredentialsError",
    "SocialAuthError",
    "InvalidTokenError",
    "AccountExistsError",
    "InvalidCountryCodeError",
    "InvalidResetTokenError",
    # Constants
    "ACCESS_TOKEN_EXPIRE_MINUTES",
    "DELETED_USERNAME",
    "DELETED_PHONE_NUMBER",
    "DELETED_EMAIL",
    "SENTINEL_USERNAMES",
    "NUM_RANKED_USERS",
    "WELCOME_EMAIL_SUBJECT",
    "WELCOME_EMAIL_MESSAGE",
    # Authentication
    "authenticate_user_by_apple",
    "authenticate_user_by_google",
    "authenticate_user_by_password",
    "get_password_hash",
    "verify_password",
    # CRUD
    "create_user_by_password",
    "delete_user",
    "get_sentinel_users",
    "get_user",
    "to_other_user_out",
    # Profile management
    "update_user_fields",
    # Social
    "check_contacts",
    "get_ranking",
    "search_username",
    # Utils
    "get_streak_info",
]

PASSWORD_REQUIRED_FIELDS = {"username", "phone_number", "email", "password"}
HASH_PREFIX = "$argon2id$"


async def _set_education_field(
    db_session: AsyncSession,
    user: User,
    education_data: EducationInfoIn,
    field_name: Literal["current_education", "intended_education"],
) -> None:
    """Set either current or intended education for a user.

    Args:
        db_session: Database session
        user: User to update
        education_data: Education data to set
        field_name: Which education field to update
    """
    education_info: EducationInfo | None = getattr(user, field_name)

    if education_info:
        # Update existing education
        if education_data.level_id is not UnsetDefault:
            education_info.level_id = education_data.level_id

        if education_data.stage_id is not UnsetDefault:
            education_info.stage_id = education_data.stage_id

        if education_data.institution_id is not UnsetDefault:
            education_info.institution_id = education_data.institution_id

        if education_data.course_id is not UnsetDefault:
            education_info.course_id = education_data.course_id

        try:
            await db_session.flush()
        except IntegrityError as e:
            if "level_id" in str(e.orig):
                raise InvalidLevelIdError
            elif "stage_id" in str(e.orig):
                raise InvalidStageIdError
            elif "institution_id" in str(e.orig):
                raise InvalidInstitutionIdError
            elif "course_id" in str(e.orig):
                raise InvalidCourseIdError
        await db_session.refresh(education_info)
    else:
        # Create new education
        try:
            new_education = await _create_education_from_data(
                db_session, education_data
            )
            setattr(user, field_name, new_education)
            await db_session.flush()
        except IntegrityError as e:
            if "level_id" in str(e.orig):
                raise InvalidLevelIdError
            elif "stage_id" in str(e.orig):
                raise InvalidStageIdError
            elif "institution_id" in str(e.orig):
                raise InvalidInstitutionIdError
            elif "course_id" in str(e.orig):
                raise InvalidCourseIdError

    logger.info(f"User {user.id} updated their {field_name}")

    # Automatically join communities based on education information
    await db_session.refresh(user, ["current_education", "intended_education"])
    if user.current_education:
        await db_session.refresh(
            user.current_education, ["institution", "course", "stage"]
        )
        if user.current_education.institution and (
            user.current_education.course or user.current_education.stage
        ):
            joined_community = await community_service.change_user_education_community(
                db_session,
                user=user,
                institution=user.current_education.institution,
                course=user.current_education.course,
                stage=user.current_education.stage,
            )
            if joined_community:
                logger.info(
                    f"User {user.id} automatically joined the community {joined_community.name} with subtitle {joined_community.subtitle} because of their education, leaving the previous community"
                )
            else:
                logger.info(
                    f"User {user.id} was already in the community when changing education"
                )


async def _create_user(
    db_session: AsyncSession,
    *,
    name: str,
    email: str,
    signup_source: SignupSource,
    referred_by_username: str | None,
    hashed_password: str | None,
    google_id: str | None,
    apple_id: str | None,
) -> User:
    """Centralized user creation function.

    Args:
        db_session: Database session
        name: User's name
        email: User's email
        signup_source: How the user came to know the app
        referred_by_username: Username of the referring user
        hashed_password: Pre-hashed password for password-based auth
        google_id: Google ID for Google auth
        apple_id: Apple ID for Apple auth

    Returns:
        Created user

    Raises:
        ReferredByNotFoundError: If referring user not found
        UsernameAlreadyExists: If generated username is taken
        EmailAlreadyExists: If email is taken
    """
    referred_by_id = None
    if referred_by_username:
        referred_by = await get_user(db_session, username=referred_by_username)
        if not referred_by:
            raise ReferredByNotFoundError
        referred_by_id = referred_by.id

    base_username = _normalize_username(name)
    username = f"{base_username}{random.randint(1000, 9999)}"

    new_user = User(
        name=name,
        username=username,
        email=email,
        hashed_password=hashed_password or "",
        google_id=google_id or "",
        apple_id=apple_id or "",
        signup_source=signup_source,
        referred_by_id=referred_by_id,
    )

    try:
        db_session.add(new_user)
        await db_session.flush()
    except IntegrityError as e:
        error_msg = str(e.orig)
        if "username" in error_msg:
            raise UsernameAlreadyExists
        elif "email" in error_msg:
            raise EmailAlreadyExists
        else:
            raise

    if referred_by_id:
        await db_session.execute(
            update(User)
            .where(User.id == new_user.referred_by_id)
            .values(social_score=User.social_score + SOCIAL_SCORE_INCREMENT_BY_REFERRAL)
        )

    await db_session.refresh(new_user, ["referrals"])

    if new_user.email:
        await mail.enqueue_email(
            mail.EmailMessage(
                subject=WELCOME_EMAIL_SUBJECT,
                body_html=WELCOME_EMAIL_MESSAGE.format(username=new_user.username),
                to_emails=[new_user.email],
            ),
        )

    return new_user


async def _create_social_user(
    db_session: AsyncSession,
    *,
    name: str | None,
    email: str,
    signup_source: SignupSource,
    referred_by_username: str,
    google_id: str | None = None,
    apple_id: str | None = None,
) -> User:
    """Create a new user from social authentication.

    Args:
        db_session: Database session
        name: User's name
        email: User's email
        google_id: Google ID if authenticating with Google
        apple_id: Apple ID if authenticating with Apple
        signup_source: How the user came to know the app. Defaults to SignupSource.UNKNOWN.
    Returns:
        Created user

    Raises:
        UsernameAlreadyExists: If generated username is taken
        EmailAlreadyExists: If email is taken
    """
    display_name = name or f"User {random.randint(1000, 9999)}"

    return await _create_user(
        db_session,
        name=display_name,
        email=email,
        signup_source=signup_source,
        referred_by_username=referred_by_username,
        hashed_password="",
        google_id=google_id,
        apple_id=apple_id,
    )


async def _create_education_from_data(
    db_session: AsyncSession,
    education_data: EducationInfoIn,
) -> EducationInfo:
    """Create an Education object from input data.

    Args:
        db_session: The database session
        education_data: Dictionary containing education information

    Returns:
        Created Education object or None if no data provided
    """
    if education_data.level_id is UnsetDefault:
        raise ValueError("Level id is required if creating education")

    institution_id = (
        education_data.institution_id
        if education_data.institution_id is not UnsetDefault
        else None
    )
    course_id = (
        education_data.course_id
        if education_data.course_id is not UnsetDefault
        else None
    )
    stage_id = (
        education_data.stage_id if education_data.stage_id is not UnsetDefault else None
    )

    return await education_service.build_education(
        db_session,
        level_id=education_data.level_id,
        stage_id=stage_id,
        institution_id=institution_id,
        course_id=course_id,
    )


async def validate_username(
    db_session: AsyncSession, username: str
) -> tuple[bool, str | None]:
    try:
        username_adapter: TypeAdapter[UsernameStr] = TypeAdapter(UsernameStr)
        validated_username = username_adapter.validate_python(username)
        user = await get_user(db_session, username=validated_username)
        return user is None, validated_username
    except ValueError:
        return False, None


async def validate_email(
    db_session: AsyncSession, email: str
) -> tuple[bool, str | None]:
    try:
        email_adapter: TypeAdapter[LowercaseEmailStr] = TypeAdapter(LowercaseEmailStr)
        validated_email = email_adapter.validate_python(email)
        user = await get_user(db_session, email=validated_email)
        return user is None, validated_email
    except ValueError:
        return False, None


async def validate_phone_number(
    db_session: AsyncSession, phone_number: str
) -> tuple[bool, str | None]:
    try:
        validated_phone_number = phone_number_adapter.validate_python(phone_number)
        user = await get_user(db_session, phone_number=validated_phone_number)
        return user is None, validated_phone_number
    except ValidationError:
        return False, None


async def validate_user_field(
    db_session: AsyncSession,
    field_name: Literal["username", "email", "phone_number"],
    field_value: str,
) -> tuple[bool, str | None]:
    if field_name == "username":
        return await validate_username(db_session, field_value)
    elif field_name == "email":
        return await validate_email(db_session, field_value)
    elif field_name == "phone_number":
        return await validate_phone_number(db_session, field_value)


async def update_user_fields(
    db_session: AsyncSession,
    *,
    user: User,
    updates: UserUpdate,
    current_password: str | None = None,
) -> tuple[User, list[str]]:
    """Update multiple user fields atomically with field-specific validation.

    Args:
        db_session: Database session
        user: User to update
        updates: Typed update data
        current_password: Current password for sensitive field updates

    Returns:
        Tuple of (updated_user, list_of_updated_fields)

    Raises:
        InvalidCredentialsError: If password required but invalid
        UsernameAlreadyExists: If username already taken
        PhoneNumberAlreadyExists: If phone number already taken
        EmailAlreadyExists: If email already taken
        InvalidCountryCodeError: If country code is invalid
    """
    # Check if any sensitive fields are being updated
    sensitive_fields_to_update = PASSWORD_REQUIRED_FIELDS.intersection(
        updates.model_fields_set
    )

    if sensitive_fields_to_update:
        if not current_password:
            raise InvalidCredentialsError(
                "Password required for sensitive field updates"
            )
        if not verify_password(current_password, user.hashed_password):
            raise InvalidCredentialsError("Invalid password")

    updated_fields: list[str] = []

    # Handle current_education field explicitly
    if updates.current_education is not UnsetDefault:
        await _set_education_field(
            db_session, user, updates.current_education, "current_education"
        )
        updated_fields.append("current_education")

    # Handle intended_education field explicitly
    if updates.intended_education is not UnsetDefault:
        await _set_education_field(
            db_session, user, updates.intended_education, "intended_education"
        )
        updated_fields.append("intended_education")

    # Handle username field explicitly
    if updates.username is not UnsetDefault:
        if updates.username.strip().lower() != user.username.lower():
            try:
                user.username = updates.username.strip()
                await db_session.flush()
                updated_fields.append("username")
            except IntegrityError as e:
                await db_session.rollback()
                if "username" in str(e.orig):
                    raise UsernameAlreadyExists
                raise

    # Handle name field explicitly
    if updates.name is not UnsetDefault:
        if updates.name != user.name:
            user.name = updates.name.strip()
            updated_fields.append("name")

    # Handle password field explicitly
    if updates.password is not UnsetDefault:
        user.hashed_password = get_password_hash(updates.password.get_secret_value())
        updated_fields.append("password")

    # Handle phone_number field explicitly
    if updates.phone_number is not UnsetDefault:
        if updates.phone_number != user.phone_number:
            try:
                user.phone_number = updates.phone_number
                await db_session.flush()
                updated_fields.append("phone_number")
            except IntegrityError as e:
                await db_session.rollback()
                if "phone_number" in str(e.orig):
                    raise PhoneNumberAlreadyExists
                raise

    # Handle email field explicitly
    if updates.email is not UnsetDefault:
        if updates.email != user.email:
            try:
                user.email = updates.email
                await db_session.flush()
                updated_fields.append("email")
            except IntegrityError as e:
                await db_session.rollback()
                if "email" in str(e.orig):
                    raise EmailAlreadyExists
                raise

    # Handle country_code field explicitly
    if updates.country_code is not UnsetDefault:
        try:
            country = await get_country(db_session, country_code=updates.country_code)
        except CountryNotFound:
            raise InvalidCountryCodeError(
                f"Invalid country code: {updates.country_code}"
            )
        user.country_id = country.id
        await db_session.flush()
        updated_fields.append("country_code")

    if updates.location is not UnsetDefault:
        new_location = WKTElement(
            f"POINT({updates.location.longitude} {updates.location.latitude})",
            srid=4326,
        )
        user.location = new_location  # type: ignore # this should work according to geoalchemy2
        await db_session.flush()
        updated_fields.append("location")

    if updated_fields:
        await db_session.flush()
        logger.info(f"User {user.id} updated fields: {', '.join(updated_fields)}")

    return user, updated_fields


async def authenticate_user_by_password(
    db_session: AsyncSession, email: str, password: str
) -> User | Literal[False]:
    """Given credentials, return a user if they are valid.

    Args:
        db_session: The database session.
        email: The email of the user to authenticate.
        password: The password of the user to authenticate.

    Returns:
        The user if the credentials are valid, otherwise False.
    """
    user = await get_user(db_session, email=email)
    if not user:
        logger.info(f"User with email {email} not found when authenticating")
        return False
    if not verify_password(password, user.hashed_password):
        logger.info(
            f"User with email {email} password is incorrect when authenticating"
        )
        return False
    return user


async def authenticate_user_by_google(
    db_session: AsyncSession,
    *,
    id_token: str,
    signup_source: SignupSource,
    referred_by_username: str,
) -> User:
    """Authenticate user using Google ID token.

    Args:
        db_session: Database session
        id_token: Google ID token
        signup_source: How the user came to know the app
        referred_by_username: Username of referring user
        country_code: Country code for the user

    Returns:
        Authenticated user

    Raises:
        InvalidTokenError: If token is invalid
        AccountExistsError: If account exists with different auth method
    """
    google_user_info = await external_auth.verify_google_id_token(id_token)

    existing_user = await get_user(db_session, google_id=google_user_info.sub)
    if existing_user:
        return existing_user

    existing_user = await get_user(db_session, email=google_user_info.email)
    if existing_user:
        if google_user_info.email_verified:
            # oh, sorry, this email on your google account must be yours! let me give it to you!
            existing_user.google_id = google_user_info.sub
            existing_user.hashed_password = ""  # now you can't login with password
            await db_session.flush()
            return existing_user
        else:
            # you're going to have to do more to convince me that this email on your google account is yours
            raise AccountExistsError

    # there is no user with the same email nor google_id

    return await _create_social_user(
        db_session,
        name=google_user_info.name,
        email=google_user_info.email,
        google_id=google_user_info.sub,
        signup_source=signup_source,
        referred_by_username=referred_by_username,
    )


async def authenticate_user_by_apple(
    db_session: AsyncSession,
    *,
    id_token: str,
    name: str,
    signup_source: SignupSource,
    referred_by_username: str,
) -> User:
    """Authenticate user using Apple ID token.

    Args:
        db_session: Database session
        id_token: Apple ID token
        signup_source: How the user came to know the app. Defaults to SignupSource.UNKNOWN.
    Returns:
        Authenticated user

    Raises:
        InvalidTokenError: If token is invalid
        AccountExistsError: If account exists with different auth method
    """
    user_info = await external_auth.verify_apple_id_token(id_token)

    existing_user = await get_user(db_session, apple_id=user_info.sub)
    if existing_user:
        return existing_user

    existing_user = await get_user(db_session, email=user_info.email)
    if existing_user:
        if user_info.email_verified:
            # oh, sorry, this email on your apple account must be yours! let
            # me give you access to this existing account!
            existing_user.apple_id = user_info.sub
            existing_user.hashed_password = ""  # now you can't login with password
            await db_session.flush()
            return existing_user
        else:
            # you're going to have to do more to convince me that
            # this email on your apple account is yours
            raise AccountExistsError

    return await _create_social_user(
        db_session,
        name=name,
        email=user_info.email,
        apple_id=user_info.sub,
        signup_source=signup_source,
        referred_by_username=referred_by_username,
    )


def _normalize_username(raw_name: str) -> str:
    """Normalize a name to create a username.

    Args:
        raw_name: The raw name to normalize

    Returns:
        Normalized username
    """
    nfkd_form = unicodedata.normalize("NFKD", raw_name)
    no_accents = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
    no_spaces = no_accents.replace(" ", "_")
    only_alnum = re.sub(r"[^a-zA-Z0-9_]", "", no_spaces)
    username = only_alnum.lower()
    return username


async def get_user(
    db_session: AsyncSession,
    *,
    username: str | None = None,
    id: int | None = None,
    phone_number: str | None = None,
    email: str | None = None,
    google_id: str | None = None,
    apple_id: str | None = None,
    exclude_sentinel: bool = True,
) -> User | None:
    """Get a user by either username or user_id.

    Args:
        db_session: The database session
        username: Username to look up. Defaults to None.
        id: User ID to look up. Defaults to None.
        phone_number: Phone number to look up. Defaults to None.
        email: Email to look up. Defaults to None.
        google_id: Google ID to look up. Defaults to None.
        apple_id: Apple ID to look up. Defaults to None.
        exclude_sentinel: Whether to exclude sentinel usernames. Defaults to True.

    Returns:
        The found user

    Raises:
        UserNotFound: If no user is found
        ValueError: If neither username nor user_id is provided
    """

    if username is not None:
        stmt = select(User).where(User.username == username.strip())
    elif id is not None:
        stmt = select(User).where(User.id == id)
    elif phone_number is not None:
        stmt = select(User).where(User.phone_number == phone_number)
    elif email is not None:
        stmt = select(User).where(User.email == email.strip().lower())
    elif google_id is not None:
        stmt = select(User).where(User.google_id == google_id)
    elif apple_id is not None:
        stmt = select(User).where(User.apple_id == apple_id)
    else:
        raise ValueError(
            "Must provide either username, user_id, phone_number, email, google_id, or apple_id"
        )

    if exclude_sentinel:
        stmt = stmt.where(~User.username.in_(SENTINEL_USERNAMES))

    user = (await db_session.scalars(stmt)).first()
    return user


async def create_user_by_password(
    db_session: AsyncSession,
    *,
    name: str,
    password: str,
    email: str,
    referred_by_username: str | None,
    signup_source: SignupSource,
) -> User:
    """Create a new user, choosing a username based on the name.

    Args:
        db_session: The database session
        name: The name of the user to create
        password: The password of the user to create
        email: The email of the user to create
        referred_by_username: The username of the user who referred the new user. Defaults to None.
        signup_source: How the user came to know the app. Defaults to SignupSource.UNKNOWN.

    Raises:
        ReferredByNotFoundError: The referred by user was not found
        UsernameAlreadyExists: There's a user with this username, case insensitive
        PhoneNumberAlreadyExists: There's a user with this phone number
        EmailAlreadyExists: There's a user with this email

    Returns:
        The created user
    """
    return await _create_user(
        db_session,
        name=name,
        email=email,
        signup_source=signup_source,
        referred_by_username=referred_by_username,
        hashed_password=get_password_hash(password),
        google_id=None,
        apple_id=None,
    )


async def delete_user(
    db_session: AsyncSession, user: User, current_password: str
) -> None:
    """Delete a user after password verification.

    Args:
        db_session: The database session
        user: The user to delete
        current_password: Current password for verification

    Raises:
        InvalidCredentialsError: If password is incorrect
    """
    # TODO: improve dealing with google and apple users
    if not user.google_id and not user.apple_id:
        if not verify_password(current_password, user.hashed_password):
            raise InvalidCredentialsError

    logger.info(f"Deleting user {user.id}")
    # TODO: delete from analytics too
    await db_session.delete(user)
    await db_session.flush()


async def get_sentinel_users(db_session: AsyncSession) -> list[User]:
    """Get all sentinel users (system users).

    Args:
        db_session: The database session

    Returns:
        List of sentinel users
    """
    return list(
        (
            await db_session.scalars(
                select(User).where(User.username.in_(SENTINEL_USERNAMES))
            )
        ).all()
    )


async def to_other_user_out(
    db_session: AsyncSession,
    user_ids: list[int],
) -> list[User]:
    """Convert user IDs to OtherUserOut objects.

    Args:
        db_session: The database session
        user_ids: List of user IDs to convert

    Returns:
        List of OtherUserOut objects
    """
    result = await db_session.scalars(
        select(User)
        .where(User.id.in_(user_ids))
        .options(
            selectinload(User.current_education),
            selectinload(User.intended_education),
        )
    )
    users = list(result.all())
    return users


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its hashed version.

    Args:
        plain_password: The plain text password to verify
        hashed_password: The hashed password to verify against

    Returns:
        True if password matches, False otherwise
    """
    ph = PasswordHasher()
    try:
        ph.verify(hashed_password, plain_password)
        return True
    except VerifyMismatchError:
        return False


def get_password_hash(password: str) -> str:
    """Generate a hash for the given password.

    Args:
        password: The plain text password to hash

    Returns:
        The hashed password
    """
    ph = PasswordHasher()
    return ph.hash(password)


class ResetPasswordTokenData(BaseModel):
    user_id: int
    email: str
    expires_at: AwareDatetime


async def request_password_reset(
    request: Request, db_session: AsyncSession, email: str
) -> None:
    """Request password reset for user by email"""
    user = await get_user(db_session, email=email)
    if not user:
        return

    # Generate secure token
    token = secrets.token_urlsafe(32)

    now = datetime.now(timezone.utc)

    # Store token with expiration (15 minutes)
    token_data = ResetPasswordTokenData(
        user_id=user.id,
        email=email,
        expires_at=now + timedelta(minutes=15),
    )

    await get_redis().setex(
        f"reset_token:{token}",
        timedelta(minutes=15),
        token_data.model_dump_json(),
    )

    await send_password_reset_email(request, email, token)


async def get_valid_reset_token(token: str) -> ResetPasswordTokenData:
    """Get a valid reset token"""
    try:
        token_data = ResetPasswordTokenData.model_validate_json(
            await get_redis().get(f"reset_token:{token}")
        )
    except ValidationError as e:
        raise InvalidResetTokenError(f"Invalid or expired reset token: {e.errors()}")

    if token_data.expires_at < datetime.now(timezone.utc):
        raise InvalidResetTokenError("Reset token has expired")
    return token_data


async def reset_password(
    db_session: AsyncSession, token: str, new_password: str
) -> bool:
    """Reset password using token from email"""
    # Get token data
    token_data = await get_valid_reset_token(token)

    # Get user and update password
    user = await get_user(db_session, id=token_data.user_id)
    if not user:
        raise UserNotFoundError("User not found")

    user.hashed_password = get_password_hash(new_password)

    # Delete used token
    await get_redis().delete(f"reset_token:{token}")

    return True
