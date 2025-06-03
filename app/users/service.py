import logging
import random
import re
import unicodedata
from typing import Any, Literal

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import app.amp as amp
import app.mail as mail
import app.users.external_auth as external_auth
from app.education import service as education_service
from app.education.models import Education
from app.users.constants import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    DELETED_EMAIL,
    DELETED_PHONE_NUMBER,
    DELETED_USERNAME,
    NUM_RANKED_USERS,
    PICO_EMAIL,
    PICO_PHONE_NUMBER,
    PICO_USERNAME,
    SENTINEL_USERNAMES,
    SYSTEM_EMAIL,
    SYSTEM_PHONE_NUMBER,
    SYSTEM_USERNAME,
    WELCOME_EMAIL_MESSAGE,
    WELCOME_EMAIL_SUBJECT,
)
from app.users.exceptions import (
    AccountExistsError,
    EmailAlreadyExists,
    InvalidCredentialsError,
    InvalidTokenError,
    PhoneNumberAlreadyExists,
    ReferredByNotFoundError,
    SocialAuthError,
    UsernameAlreadyExists,
    UserNotFoundError,
)
from app.users.models import EducationLevel, SignupSource, User, UserProfile
from app.users.social import (
    check_contacts,
    get_ranking,
    search_username,
)
from app.users.utils import (
    get_online_info,
    get_streak_info,
)

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
    # Constants
    "ACCESS_TOKEN_EXPIRE_MINUTES",
    "DELETED_USERNAME",
    "DELETED_PHONE_NUMBER",
    "DELETED_EMAIL",
    "PICO_USERNAME",
    "PICO_PHONE_NUMBER",
    "PICO_EMAIL",
    "SYSTEM_USERNAME",
    "SYSTEM_PHONE_NUMBER",
    "SYSTEM_EMAIL",
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
    "get_online_info",
    "get_streak_info",
]


async def _set_education_field(
    db_session: AsyncSession,
    user: User,
    education_data: dict[str, Any],
    field_name: Literal["current_education", "intended_education"],
) -> None:
    """Set either current or intended education for a user.

    Args:
        db_session: Database session
        user: User to update
        education_data: Education data to set
        field_name: Which education field to update
    """
    current_education = getattr(user, field_name)

    if current_education:
        await education_service.update_education(
            db_session,
            current_education,
            level=education_data.get("level"),
            institution_id=education_data.get("institution_id"),
            course_id=education_data.get("course_id"),
        )
    else:
        new_education = await _create_education_from_data(db_session, education_data)
        setattr(user, field_name, new_education)

    await db_session.flush()
    logger.info(f"User {user.id} updated their {field_name}")


async def _create_social_user(
    db_session: AsyncSession,
    *,
    name: str | None,
    email: str | None,
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
    base_username = _normalize_username(display_name)
    username = f"{base_username}{random.randint(1000, 9999)}"

    referred_by_id = None
    if referred_by_username:
        referred_by = await get_user(db_session, username=referred_by_username)
        if not referred_by:
            raise ReferredByNotFoundError
        referred_by_id = referred_by.id

    new_user = User(
        name=display_name,
        username=username,
        email=email,
        google_id=google_id,
        apple_id=apple_id,
        signup_source=signup_source,
        referred_by_id=referred_by_id,
    )
    db_session.add(UserProfile(user=new_user))

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

    await db_session.refresh(new_user, ["referrals", "profile"])

    if new_user.email:
        await mail.enqueue_email(
            mail.EmailMessage(
                subject=WELCOME_EMAIL_SUBJECT,
                body_html=WELCOME_EMAIL_MESSAGE.format(username=new_user.username),
                to_emails=[new_user.email],
            ),
        )

    return new_user


async def _create_education_from_data(
    db_session: AsyncSession,
    education_data: dict[str, Any] | None,
) -> Education | None:
    """Create an Education object from input data.

    Args:
        db_session: The database session
        education_data: Dictionary containing education information

    Returns:
        Created Education object or None if no data provided
    """
    if not education_data:
        return None

    level = education_data.get("level", EducationLevel.UNKNOWN)
    institution_id = education_data.get("institution_id")
    course_id = education_data.get("course_id")

    return await education_service.create_education(
        db_session,
        level=level,
        institution_id=institution_id,
        course_id=course_id,
    )


async def update_user_fields(
    db_session: AsyncSession,
    *,
    user: User,
    updates: dict[str, Any],
    current_password: str | None = None,
) -> tuple[User, list[str]]:
    """Update multiple user fields atomically with field-specific validation.

    Args:
        db_session: Database session
        user: User to update
        updates: Dictionary of field names to new values
        current_password: Current password for sensitive field updates

    Returns:
        Tuple of (updated_user, list_of_updated_fields)

    Raises:
        InvalidCredentialsError: If password required but invalid
        UsernameAlreadyExists: If username already taken
        PhoneNumberAlreadyExists: If phone number already taken
        EmailAlreadyExists: If email already taken
    """
    password_required_fields = {"username", "phone_number", "email", "password"}
    sensitive_updates = password_required_fields.intersection(updates.keys())

    if sensitive_updates:
        if not current_password:
            raise InvalidCredentialsError(
                "Password required for sensitive field updates"
            )
        if not verify_password(current_password, user.hashed_password):
            raise InvalidCredentialsError("Invalid password")

    updated_fields: list[str] = []

    for field_name, new_value in updates.items():
        # Handle education fields that can be set to None
        if field_name in ("current_education", "intended_education"):
            if new_value is None:
                setattr(user, field_name, None)
                setattr(user, f"{field_name}_id", None)
                updated_fields.append(field_name)
                continue

            education_data = new_value
            if hasattr(new_value, "model_dump"):
                education_data = new_value.model_dump()
            elif hasattr(new_value, "dict"):
                education_data = new_value.dict()

            await _set_education_field(db_session, user, education_data, field_name)
            updated_fields.append(field_name)
            continue

        if new_value is None:
            continue

        if field_name == "username":
            if new_value.strip().lower() != user.username.lower():
                try:
                    user.username = str(new_value).strip()
                    await db_session.flush()
                    updated_fields.append(field_name)
                except IntegrityError as e:
                    await db_session.rollback()
                    if "username" in str(e.orig):
                        raise UsernameAlreadyExists
                    raise

        elif field_name == "name":
            if new_value != user.name:
                user.name = str(new_value).strip()
                await db_session.flush()
                updated_fields.append(field_name)

        elif field_name == "password":
            password_value = (
                new_value.get_secret_value()
                if hasattr(new_value, "get_secret_value")
                else str(new_value)
            )
            user.hashed_password = get_password_hash(password_value)
            await db_session.flush()
            updated_fields.append(field_name)

        elif field_name in ("phone_number", "email"):
            if str(new_value) != getattr(user, field_name):
                try:
                    setattr(user, field_name, str(new_value))
                    await db_session.flush()
                    updated_fields.append(field_name)
                except IntegrityError as e:
                    await db_session.rollback()
                    error_msg = str(e.orig)
                    if field_name in error_msg:
                        if field_name == "phone_number":
                            raise PhoneNumberAlreadyExists
                        else:  # email
                            raise EmailAlreadyExists
                    raise

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
        signup_source: How the user came to know the app. Defaults to SignupSource.UNKNOWN.
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
        stmt = select(User).where(User.username == username)
    elif id is not None:
        stmt = select(User).where(User.id == id)
    elif phone_number is not None:
        stmt = select(User).where(User.phone_number == phone_number)
    elif email is not None:
        stmt = select(User).where(User.email == email)
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

    referred_by_id = None
    if referred_by_username:
        referred_by = await get_user(db_session, username=referred_by_username)
        if not referred_by:
            raise ReferredByNotFoundError
        referred_by_id = referred_by.id

    base_username = _normalize_username(name)
    username = f"{base_username}{random.randint(1000, 9999)}"

    db_user = User(
        name=name,
        username=username,
        hashed_password=get_password_hash(password),
        email=email,
        referred_by_id=referred_by_id,
        signup_source=signup_source,
    )
    db_session.add(UserProfile(user=db_user))

    try:
        db_session.add(db_user)
        await db_session.flush()
    except IntegrityError as e:
        error_msg = str(e.orig)
        if "username" in error_msg:
            raise UsernameAlreadyExists
        elif "email" in error_msg:
            raise EmailAlreadyExists
        else:
            raise

    await db_session.refresh(db_user, ["referrals", "profile"])

    await mail.enqueue_email(
        mail.EmailMessage(
            subject=WELCOME_EMAIL_SUBJECT,
            body_html=WELCOME_EMAIL_MESSAGE.format(username=db_user.username),
            to_emails=[db_user.email],
        ),
    )

    return db_user


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
    if not verify_password(current_password, user.hashed_password):
        raise InvalidCredentialsError
    logger.info(f"Deleting user {user.id}")
    await amp.delete_user(user.id)
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
            selectinload(User.profile),
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
