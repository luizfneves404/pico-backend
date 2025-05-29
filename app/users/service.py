import datetime
import logging
from typing import Any, Literal

import bcrypt
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import app.amp as amp
import app.mail as mail
import app.timezone as timezone
import app.ws.service as ws_service
from app.education import service as education_service
from app.education.models import Education

# from app.flows import quiz_service
from app.flows.models import (
    Choice,
    FlowQuestion,
    FlowQuestionUser,
    Question,
)
from app.shared.validation import CustomPhoneNumber
from app.users.models import (
    EducationLevel,
    SignupSource,
    User,
    UserProfile,
)

from .constants import (
    WELCOME_EMAIL_MESSAGE,
    WELCOME_EMAIL_SUBJECT,
)

ACCESS_TOKEN_EXPIRE_MINUTES = 30

DELETED_USERNAME = "deleted"
DELETED_PHONE_NUMBER = "1121111111"
DELETED_EMAIL = "deleted@sophinity.co"
PICO_USERNAME = "pico"
PICO_PHONE_NUMBER = "1122211111"
PICO_EMAIL = "pico@sophinity.co"
SYSTEM_USERNAME = "system"
SYSTEM_PHONE_NUMBER = "1122111111"
SYSTEM_EMAIL = "system@sophinity.co"

SENTINEL_USERNAMES = [DELETED_USERNAME, PICO_USERNAME, SYSTEM_USERNAME]

NUM_RANKED_USERS = 10

logger = logging.getLogger(__name__)

phone_number_adapter: TypeAdapter[CustomPhoneNumber] = TypeAdapter(CustomPhoneNumber)


class UserNotFoundError(Exception):
    pass


class UsernameAlreadyExists(Exception):
    pass


class PhoneNumberAlreadyExists(Exception):
    pass


class EmailAlreadyExists(Exception):
    pass


class ReferredByNotFoundError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


async def get_user(
    db_session: AsyncSession,
    *,
    username: str | None = None,
    id: int | None = None,
    phone_number: str | None = None,
    email: str | None = None,
    exclude_sentinel: bool = True,
) -> User | None:
    """Get a user by either username or user_id.

    Args:
        db_session: The database session
        username: Username to look up. Defaults to None.
        id: User ID to look up. Defaults to None.
        phone_number: Phone number to look up. Defaults to None.
        email: Email to look up. Defaults to None.
        exclude_sentinel: Whether to exclude sentinel usernames. Defaults to True.

    Returns:
        The found user

    Raises:
        UserNotFound: If no user is found
        ValueError: If neither username nor user_id is provided
    """
    if username is None and id is None and phone_number is None and email is None:
        raise ValueError(
            "Must provide either username, user_id, phone_number, or email"
        )

    if username is not None:
        stmt = select(User).where(func.lower(User.username) == func.lower(username))
    elif id is not None:
        stmt = select(User).where(User.id == id)
    elif phone_number is not None:
        stmt = select(User).where(User.phone_number == phone_number)
    elif email is not None:
        stmt = select(User).where(User.email == email)
    else:
        raise ValueError(
            "Must provide either username, user_id, phone_number, or email"
        )

    if exclude_sentinel:
        stmt = stmt.where(~User.username.in_(SENTINEL_USERNAMES))

    user = (await db_session.scalars(stmt)).first()
    return user


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


async def create_user(
    db_session: AsyncSession,
    *,
    username: str,
    password: str,
    phone_number: str,
    email: str,
    referred_by_username: str | None,
    signup_source: SignupSource,
    current_education: dict[str, Any] | None,
    intended_education: dict[str, Any] | None,
) -> User:
    """Create a new user.

    Args:
        db_session: The database session
        username: The username of the user to create
        password: The password of the user to create
        phone_number: The phone number of the user to create
        email: The email of the user to create
        referred_by_username: The username of the user who referred the new user. Defaults to None.
        signup_source: How the user came to know the app. Defaults to SignupSource.UNKNOWN.
        current_education: Current education data. Defaults to None.
        intended_education: Intended education data. Defaults to None.

    Raises:
        ReferredByNotFoundError: The referred by user was not found
        UsernameAlreadyExists: There's a user with this username, case insensitive
        PhoneNumberAlreadyExists: There's a user with this phone number
        EmailAlreadyExists: There's a user with this email

    Returns:
        The created user
    """
    # Create education records
    current_education_obj = await _create_education_from_data(
        db_session, current_education
    )
    intended_education_obj = await _create_education_from_data(
        db_session, intended_education
    )

    # Handle referral
    referred_by_id = None
    if referred_by_username:
        referred_by = await get_user(db_session, username=referred_by_username)
        if not referred_by:
            raise ReferredByNotFoundError
        referred_by_id = referred_by.id

    # Create user object with common attributes
    db_user = User(
        username=username,
        hashed_password=get_password_hash(password),
        phone_number=phone_number,
        email=email,
        referred_by_id=referred_by_id,
        signup_source=signup_source,
        current_education=current_education_obj,
        intended_education=intended_education_obj,
    )
    db_session.add(UserProfile(user=db_user))

    # Save user to database
    try:
        db_session.add(db_user)
        await db_session.flush()
    except IntegrityError as e:
        error_msg = str(e.orig)
        if "username" in error_msg:
            raise UsernameAlreadyExists
        elif "phone_number" in error_msg:
            raise PhoneNumberAlreadyExists
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


async def authenticate_user(
    db_session: AsyncSession, username: str, password: str
) -> User | Literal[False]:
    """Given credentials, return a user if they are valid.

    Args:
        db_session: The database session.
        username: The username of the user to authenticate.
        password: The password of the user to authenticate.

    Returns:
        The user if the credentials are valid, otherwise False.
    """
    user = await get_user(db_session, username=username)
    if not user:
        logger.info(f"User with username {username} not found when authenticating")
        return False
    if not verify_password(password, user.hashed_password):
        logger.info(
            f"User with username {username} password is incorrect when authenticating"
        )
        return False
    return user


async def validate_username(db_session: AsyncSession, username: str) -> None:
    if await get_user(db_session, username=username):
        raise UsernameAlreadyExists


async def validate_phone_number(db_session: AsyncSession, phone_number: str) -> None:
    if await get_user(db_session, phone_number=phone_number):
        raise PhoneNumberAlreadyExists


async def validate_email(db_session: AsyncSession, email: str) -> None:
    if await get_user(db_session, email=email):
        raise EmailAlreadyExists


async def set_password(
    db_session: AsyncSession, user: User, new_password: str, current_password: str
) -> None:
    if not verify_password(current_password, user.hashed_password):
        raise InvalidCredentialsError
    user.hashed_password = get_password_hash(new_password)
    await db_session.flush()
    logger.info(f"User {user.id} changed their password")


async def set_phone_number(
    db_session: AsyncSession, user: User, new_phone_number: str, current_password: str
) -> None:
    if not verify_password(current_password, user.hashed_password):
        raise InvalidCredentialsError
    user.phone_number = new_phone_number
    try:
        await db_session.flush()
    except IntegrityError as e:
        error_msg = str(e.orig)
        if "phone_number" in error_msg:
            raise PhoneNumberAlreadyExists
        else:
            raise
    logger.info(f"User {user.id} changed their phone number to {new_phone_number}")


async def set_email(
    db_session: AsyncSession, user: User, new_email: str, current_password: str
) -> None:
    if not verify_password(current_password, user.hashed_password):
        raise InvalidCredentialsError
    user.email = new_email
    try:
        await db_session.flush()
    except IntegrityError as e:
        error_msg = str(e.orig)
        if "email" in error_msg:
            raise EmailAlreadyExists
        else:
            raise
    logger.info(f"User {user.id} changed their email to {new_email}")


async def set_current_education(
    db_session: AsyncSession, user: User, education_data: dict[str, Any]
) -> None:
    """Update user's current education.

    Args:
        db_session: The database session
        user: The user to update
        education_data: Dictionary containing education information
    """
    if user.current_education:
        # Update existing education
        await education_service.update_education(
            db_session,
            user.current_education,
            level=education_data.get("level"),
            institution_id=education_data.get("institution_id"),
            course_id=education_data.get("course_id"),
        )
    else:
        # Create new education
        new_education = await _create_education_from_data(db_session, education_data)
        user.current_education = new_education

    await db_session.flush()
    logger.info(f"User {user.id} updated their current education")


async def set_intended_education(
    db_session: AsyncSession, user: User, education_data: dict[str, Any]
) -> None:
    """Update user's intended education.

    Args:
        db_session: The database session
        user: The user to update
        education_data: Dictionary containing education information
    """
    if user.intended_education:
        # Update existing education
        await education_service.update_education(
            db_session,
            user.intended_education,
            level=education_data.get("level"),
            institution_id=education_data.get("institution_id"),
            course_id=education_data.get("course_id"),
        )
    else:
        # Create new education
        new_education = await _create_education_from_data(db_session, education_data)
        user.intended_education = new_education

    await db_session.flush()
    logger.info(f"User {user.id} updated their intended education")


async def delete_user(
    db_session: AsyncSession, user: User, current_password: str
) -> None:
    if not verify_password(current_password, user.hashed_password):
        raise InvalidCredentialsError
    logger.info(f"Deleting user {user.id}")
    await amp.delete_user(user.id)
    await db_session.delete(user)
    await db_session.flush()


async def check_contacts(
    db_session: AsyncSession, raw_phone_numbers: list[str]
) -> list[User]:
    phone_numbers: list[str] = []
    for phone_number in raw_phone_numbers:
        try:
            phone_numbers.append(phone_number_adapter.validate_python(phone_number))
        except ValidationError:
            pass
    logger.debug(
        f"Contacts checked! There were {len(phone_numbers)} valid phone numbers"
    )
    matched_users = (
        await db_session.scalars(
            select(User)
            .where(User.phone_number.in_(phone_numbers))
            .order_by(User.username)
        )
    ).all()
    logger.debug(f"Found {len(matched_users)} matching users after checking contacts")
    return list(matched_users)


async def search_username(db_session: AsyncSession, username: str) -> list[User]:
    logger.debug(f"Searching for username containing '{username}'")
    return list(
        (
            await db_session.scalars(
                select(User)
                .where(User.username.ilike(f"%{username}%"))
                .order_by(User.username)
            )
        ).all()
    )


async def get_sentinel_users(db_session: AsyncSession) -> list[User]:
    return list(
        (
            await db_session.scalars(
                select(User).where(User.username.in_(SENTINEL_USERNAMES))
            )
        ).all()
    )


def get_streak_info(answer_timestamps: list[datetime.datetime]) -> tuple[bool, int]:
    """
    Receives a list of user answer timestamps (must be timezone-aware).
    Returns a tuple of (done_today, streak).
    """

    if not answer_timestamps:
        return False, 0

    # Ensure all timestamps are timezone-aware
    if any(
        ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None for ts in answer_timestamps
    ):
        raise ValueError("All timestamps must be timezone-aware")

    # Convert timestamps to server's timezone
    ordered_timestamps = sorted(
        (timezone.localtime(ts) for ts in answer_timestamps), reverse=True
    )

    streak = 0
    today = timezone.localdate()
    done_today = False
    last_processed_date = None

    for timestamp in ordered_timestamps:
        current_date = timestamp.date()

        if last_processed_date == current_date:
            continue
        last_processed_date = current_date

        if streak == 0:
            if current_date == today:
                done_today = True
                streak += 1
            elif current_date == today - datetime.timedelta(days=1):
                streak += 1
            else:
                break
        else:
            if current_date == today - datetime.timedelta(
                days=streak + 1 if not done_today else streak
            ):
                streak += 1
            else:
                break

    return done_today, streak


async def get_user_stats(
    db_session: AsyncSession,
    *,
    user_id: int | None = None,
    username: str | None = None,
) -> dict[str, Any]:
    """Get statistics for a user.

    Args:
        db_session: Database session
        user_id: Optional user ID to look up
        username: Optional username to look up

    Returns:
        Dictionary containing user statistics

    Raises:
        UserNotFoundError: If the user cannot be found
    """
    if user_id is not None:
        found_user = await get_user(db_session, id=user_id)
    elif username is not None:
        found_user = await get_user(db_session, username=username)
    else:
        raise ValueError("Must provide either user_id or username")

    if not found_user:
        raise UserNotFoundError

    # user_stats = await quiz_service.calc_user_stats(db_session, found_user.id)
    # Placeholder user stats - ignoring flow/quiz issues
    user_stats = {
        "score": 0.0,
        "total_answers": 0,
        "correct_answers": 0,
        "area_expected_scores": {
            "Matemática": 0.0,
            "Linguagens": 0.0,
            "Ciências Humanas": 0.0,
            "Ciências da Natureza": 0.0,
        },
    }

    await db_session.refresh(
        found_user, ["current_education", "intended_education", "profile"]
    )
    # Get user answer timestamps
    stmt = (
        select(FlowQuestionUser.created_at)
        .where(
            or_(
                FlowQuestionUser.choice_id.is_not(None),
                FlowQuestionUser.submitted_text != "",
            ),
            FlowQuestionUser.user_id == found_user.id,
        )
        .order_by(FlowQuestionUser.created_at.desc())
    )

    result = await db_session.execute(stmt)
    user_answers_timestamps = [row[0] for row in result.all()]

    done_today, streak = get_streak_info(user_answers_timestamps)

    user_stats.update(
        {
            "id": found_user.id,
            "username": found_user.username,
            "current_education": found_user.current_education,
            "intended_education": found_user.intended_education,
            "score": user_stats["score"],
            "area_expected_scores": {
                "Matemática": user_stats["area_expected_scores"]["Matemática"],
                "Linguagem": user_stats["area_expected_scores"][
                    "Linguagens"
                ],  # deveria ser Linguagens, mas o front ta esperando errado
                "Ciências Humanas": user_stats["area_expected_scores"][
                    "Ciências Humanas"
                ],
                "Ciências da Natureza": user_stats["area_expected_scores"][
                    "Ciências da Natureza"
                ],
            },
            "streak": streak,
            "done_today": done_today,
            "percentage_score": await get_user_percentage_score(
                db_session, found_user.id
            ),
        }
    )
    return user_stats


async def get_user_percentage_score(
    db_session: AsyncSession, user_id: int, subject: str | None = None
) -> float:
    """
    Calculate percentage score for a single user.
    Returns the ratio of correct answers to total answers.
    """
    # Start with base query counting answers
    query = select(
        func.count(FlowQuestionUser.id)
        .filter(
            or_(
                FlowQuestionUser.choice_id.is_not(None),
            )
        )
        .label("total_answers"),
        func.count(FlowQuestionUser.id)
        .filter(Choice.is_correct.is_(True))
        .label("correct_answers"),
    ).select_from(FlowQuestionUser)

    # Always join with Choice for correct answer counting
    query = query.outerjoin(Choice, FlowQuestionUser.choice_id == Choice.id)

    # Apply user filter
    query = query.where(FlowQuestionUser.user_id == user_id)

    # Only join with Question tables if we need to filter by subject
    if subject:
        query = (
            query.join(
                FlowQuestion,
                FlowQuestionUser.flow_element_id == FlowQuestion.id,
            )
            .join(Question, FlowQuestion.question_id == Question.id)
            .where(Question.subject == subject)
        )

    # Execute query
    result = await db_session.execute(query)
    row = result.one()

    total_answers = row.total_answers
    correct_answers = row.correct_answers

    return correct_answers / total_answers if total_answers else 0.0


async def get_ranking(
    db_session: AsyncSession,
    asking_user_id: int,
    score_type: Literal["dynamic", "percentage"],
    school_filter: int | None,
    course_filter: str | None,
    education_level_filter: EducationLevel | None,
    subject: str | None = None,
) -> list[dict[str, Any]]:
    # Note: This function needs to be updated to work with the new education structure
    # For now, keeping the basic structure but this will need more work
    stmt = select(User.id)
    # TODO: Update filtering logic to work with new education structure
    # if school_filter:
    #     stmt = stmt.where(User.school_id == school_filter)
    # if course_filter:
    #     stmt = stmt.join(User.chosen_course).where(Course.name == course_filter)
    # if education_level_filter:
    #     stmt = stmt.where(User.education_level == education_level_filter)

    # users_ids = await db_session.scalars(stmt)
    # Note: quiz_service is not imported, this will need to be fixed
    # if score_type == "dynamic":
    #     return await quiz_service.get_ranked_users_stats_by_dynamic_score(
    #         users_ids, NUM_RANKED_USERS, asking_user_id
    #     )
    # elif score_type == "percentage":
    #     return await quiz_service.get_ranked_users_stats_by_percentage(
    #         users_ids, NUM_RANKED_USERS, asking_user_id, subject
    #     )
    # else:
    #     raise ValueError(f"Invalid score type: {score_type}")
    return []  # Placeholder


async def get_user_infos(
    db_session: AsyncSession, users: list[User]
) -> list[dict[str, str | int | datetime.datetime]]:
    total_answers = (
        select(FlowQuestionUser.user_id, func.count(FlowQuestionUser.id))
        .where(FlowQuestionUser.user_id.in_(users))
        .group_by(FlowQuestionUser.user_id)
    )
    result = await db_session.execute(total_answers)
    answer_dict: dict[int, int] = {row[0]: row[1] for row in result.all()}

    return [
        {
            "username": user.username,
            "total_answers": answer_dict.get(user.id, 0),
            "date_joined": user.created_at,
        }
        for user in users
    ]


async def get_online_info(
    db_session: AsyncSession,
    user_ids: list[int],
) -> list[dict[str, int | bool | datetime.datetime | None]]:
    """Get online status and last online time for a list of users.

    Args:
        user_ids: List of user IDs to check status for

    Returns:
        List of dicts containing:
            - id: user ID
            - is_online: boolean indicating if the user is online
            - last_online: last online time for offline users, None for online users
    """
    # Get current online/offline status for all users
    statuses = await ws_service.get_user_statuses(user_ids)

    # Get last online time for offline users
    offline_user_ids = [
        user_id for user_id, status in zip(user_ids, statuses) if status != "online"
    ]
    last_online_users = await ws_service.get_last_online_users(
        db_session, offline_user_ids
    )

    # Build response combining status and last online time
    return [
        {
            "id": user_id,
            "is_online": status == "online",  # Convert to boolean
            "last_online": last_online_users.get(user_id)
            if status != "online"
            else None,
        }
        for user_id, status in zip(user_ids, statuses)
    ]


async def get_balance(db_session: AsyncSession, user_id: int) -> int:
    """Get user's currency balance."""
    user = await get_user(db_session, id=user_id)
    if not user:
        raise UserNotFoundError
    return user.balance


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


async def update_user_fields(
    db_session: AsyncSession,
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
    # Define which fields require password verification
    password_required_fields = {"username", "phone_number", "email", "password"}

    # Check if any sensitive fields are being updated
    sensitive_updates = password_required_fields.intersection(updates.keys())

    # Verify password if needed
    if sensitive_updates:
        if not current_password:
            raise InvalidCredentialsError(
                "Password required for sensitive field updates"
            )
        if not verify_password(current_password, user.hashed_password):
            raise InvalidCredentialsError("Invalid password")

    updated_fields: list[str] = []

    # Handle each field type with specific validation
    for field_name, new_value in updates.items():
        if new_value is None:
            continue

        if field_name == "username":
            if new_value != user.username:
                try:
                    user.username = str(new_value).strip()
                    await db_session.flush()
                    updated_fields.append(field_name)
                except IntegrityError as e:
                    await db_session.rollback()
                    if "username" in str(e.orig):
                        raise UsernameAlreadyExists
                    raise

        elif field_name == "password":
            # Update password (current_password already verified above)
            # Extract the actual password string from SecretStr
            password_value = (
                new_value.get_secret_value()
                if hasattr(new_value, "get_secret_value")
                else str(new_value)
            )
            user.hashed_password = get_password_hash(password_value)
            await db_session.flush()
            updated_fields.append(field_name)

        elif field_name == "phone_number":
            if str(new_value) != user.phone_number:
                try:
                    user.phone_number = str(new_value)
                    await db_session.flush()
                    updated_fields.append(field_name)
                except IntegrityError as e:
                    await db_session.rollback()
                    if "phone_number" in str(e.orig):
                        raise PhoneNumberAlreadyExists
                    raise

        elif field_name == "email":
            if str(new_value) != user.email:
                try:
                    user.email = str(new_value)
                    await db_session.flush()
                    updated_fields.append(field_name)
                except IntegrityError as e:
                    await db_session.rollback()
                    if "email" in str(e.orig):
                        raise EmailAlreadyExists
                    raise

        elif field_name == "current_education":
            # Convert education data to dict if needed
            education_data = new_value
            if hasattr(new_value, "model_dump"):
                education_data = new_value.model_dump()
            elif hasattr(new_value, "dict"):
                education_data = new_value.dict()
            await set_current_education(db_session, user, education_data)
            updated_fields.append(field_name)

        elif field_name == "intended_education":
            # Convert education data to dict if needed
            education_data = new_value
            if hasattr(new_value, "model_dump"):
                education_data = new_value.model_dump()
            elif hasattr(new_value, "dict"):
                education_data = new_value.dict()
            await set_intended_education(db_session, user, education_data)
            updated_fields.append(field_name)

    if updated_fields:
        await db_session.flush()
        logger.info(f"User {user.id} updated fields: {', '.join(updated_fields)}")

    return user, updated_fields
