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
import app.chat.notifications as notifications_service
import app.chat.service as chat_service
import app.mail as mail
import app.timezone as timezone
from app.quiz import quiz_service
from app.quiz.models import (
    Choice,
    Question,
    SessionQuestion,
    SessionQuestionUser,
    UserInfo,
)
from app.schools.models import School
from app.users.models import College, Course, EducationLevel, SignupSource, User
from app.users.schemas import PhoneNumber

from .constants import (
    WELCOME_EMAIL_MESSAGE,
    WELCOME_EMAIL_SUBJECT,
)

ACCESS_TOKEN_EXPIRE_MINUTES = 30

DELETED_USERNAME = "deleted"
DELETED_PHONE_NUMBER = "1121111111"
DELETED_EMAIL = "deleted@pico.fyi"
PICO_USERNAME = "pico"
PICO_PHONE_NUMBER = "1122211111"
PICO_EMAIL = "pico@pico.fyi"
SYSTEM_USERNAME = "system"
SYSTEM_PHONE_NUMBER = "1122111111"
SYSTEM_EMAIL = "system@pico.fyi"

SENTINEL_USERNAMES = [DELETED_USERNAME, PICO_USERNAME, SYSTEM_USERNAME]

NUM_RANKED_USERS = 10

logger = logging.getLogger(__name__)

phone_number_adapter = TypeAdapter(PhoneNumber)


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


class SchoolNotFoundError(Exception):
    pass


class CollegeDoesNotHaveCourseError(Exception):
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
    username: str | None = None,
    id: int | None = None,
    phone_number: str | None = None,
    email: str | None = None,
    exclude_sentinel: bool = True,
) -> User | None:
    """Get a user by either username or user_id.

    Args:
        db_session (AsyncSession): The database session
        username (str | None): Username to look up. Defaults to None.
        id (int | None): User ID to look up. Defaults to None.
        phone_number (str | None): Phone number to look up. Defaults to None.
        email (str | None): Email to look up. Defaults to None.
        exclude_sentinel (bool): Whether to exclude sentinel usernames. Defaults to True.

    Returns:
        UserDBModel: The found user

    Raises:
        UserNotFound: If no user is found
        ValueError: If neither username nor user_id is provided
    """
    if username is None and id is None:
        raise ValueError("Must provide either username or user_id")

    if username is not None:
        stmt = select(User).where(func.lower(User.username) == func.lower(username))
    elif id is not None:
        stmt = select(User).where(User.id == id)
    elif phone_number is not None:
        stmt = select(User).where(User.phone_number == phone_number)
    elif email is not None:
        stmt = select(User).where(User.email == email)
    else:
        raise ValueError("Must provide either username or user_id")

    if exclude_sentinel:
        stmt = stmt.where(~User.username.in_(SENTINEL_USERNAMES))

    user = (await db_session.scalars(stmt)).first()

    return user


async def _get_or_create_college_course(
    db_session: AsyncSession, chosen_college: str, chosen_course: str
) -> tuple[College | None, Course | None]:
    """Get or create college and course records.

    Args:
        db_session: Database session
        chosen_college: Name of college to get/create
        chosen_course: Name of course to get/create

    Returns:
        Tuple of (college, course) - either may be None if not specified
    """
    college = None
    course = None

    if chosen_college:
        # Use selectinload to eagerly load courses relationship
        stmt = (
            select(College)
            .where(College.name == chosen_college)
            .options(selectinload(College.courses))
        )
        college = (await db_session.scalars(stmt)).first()
        if not college:
            college = College(name=chosen_college, user_submitted=True)
            db_session.add(college)

    if chosen_course:
        course = (
            await db_session.scalars(select(Course).where(Course.name == chosen_course))
        ).first()
        if not course:
            course = Course(name=chosen_course, user_submitted=True)
            db_session.add(course)

    if college and course and course not in college.courses:
        college.courses.append(course)

    return college, course


async def _get_or_create_school(db_session: AsyncSession, name: str) -> School:
    school_obj = (
        await db_session.scalars(select(School).where(School.name == name))
    ).first()
    if not school_obj:
        school_obj = School(name=name)
        db_session.add(school_obj)
    return school_obj


async def create_user(
    db_session: AsyncSession,
    *,
    username: str,
    password: str,
    phone_number: str,
    email: str,
    chosen_college: str,
    chosen_course: str,
    education_level: EducationLevel,
    commitment: int,
    referred_by_username: str | None = None,
    school_id: int | None = None,
    signup_source: SignupSource = SignupSource.UNKNOWN,
) -> User:
    """Create a new user.

    Args:
        db_session (AsyncSession): The database session
        username (str): The username of the user to create
        password (str): The password of the user to create
        phone_number (str): The phone number of the user to create
        email (str): The email of the user to create
        chosen_college (str): The college the user has chosen
        chosen_course (str): The course the user has chosen
        education_level (EducationLevel): The education level of the user
        commitment (int): The commitment of the user
        referred_by_username (str | None, optional): The username of the user who referred the new user. Defaults to None.
        school_id (int | None, optional): The ID of the school the user is attending. Defaults to None.
        signup_source (SignupSource, optional): How the user came to know the app. Defaults to SignupSource.UNKNOWN.
    Raises:
        ReferredByNotFoundError: The referred by user was not found
        UsernameAlreadyExists: There's a user with this username, case insensitive
        PhoneNumberAlreadyExists: There's a user with this phone number
        EmailAlreadyExists: There's a user with this email

    Returns:
        UserDBModel: The created user
    """
    # Get or create related entities
    college, course = await _get_or_create_college_course(
        db_session, chosen_college, chosen_course
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
        chosen_college=college,
        chosen_course=course,
        education_level=education_level,
        commitment=commitment,
        referred_by_id=referred_by_id,
        signup_source=signup_source,
    )

    # Handle school information
    if school_id:
        db_user.school_id = school_id

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

    await db_session.refresh(db_user, ["referrals"])

    db_session.add(UserInfo(user=db_user))

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
        db_session (AsyncSession): The database session.
        username (str): The username of the user to authenticate.
        password (str): The password of the user to authenticate.

    Returns:
        User: The user if the credentials are valid, otherwise False.
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


async def set_username(
    db_session: AsyncSession, user: User, new_username: str, current_password: str
) -> None:
    if not verify_password(current_password, user.hashed_password):
        raise InvalidCredentialsError
    try:
        user.username = new_username
        await db_session.flush()
    except IntegrityError as e:
        error_msg = str(e.orig)
        if "username" in error_msg:
            raise UsernameAlreadyExists
        else:
            raise
    logger.info(f"User {user.id} changed their username to {new_username}")


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


async def set_school(
    db_session: AsyncSession,
    user: User,
    new_school: str = "",
    new_school_id: int | None = None,
) -> None:
    if new_school:
        school_obj = await _get_or_create_school(db_session, new_school)
    else:
        school_obj = None
    user.school_id = (
        new_school_id if new_school_id else school_obj.id if school_obj else None
    )
    try:
        await db_session.flush()
    except IntegrityError as e:
        error_msg = str(e.orig)
        if "school" in error_msg:
            raise SchoolNotFoundError
        else:
            raise
    logger.info(
        f"User {user.id} changed their school to {new_school} or {new_school_id}"
    )


async def set_chosen_college(
    db_session: AsyncSession, user: User, new_chosen_college: str
) -> None:
    if new_chosen_college:
        await db_session.refresh(user, ["chosen_course"])
        college, _ = await _get_or_create_college_course(
            db_session,
            new_chosen_college,
            user.chosen_course.name if user.chosen_course else "",
        )
    else:
        college = None

    user.chosen_college = college

    await db_session.flush()
    logger.info(
        f"User {user.id} changed their chosen college to '{new_chosen_college}'"
    )


async def set_chosen_course(
    db_session: AsyncSession, user: User, new_chosen_course: str
) -> None:
    if new_chosen_course:
        await db_session.refresh(user, ["chosen_college"])
        _, course = await _get_or_create_college_course(
            db_session,
            user.chosen_college.name if user.chosen_college else "",
            new_chosen_course,
        )
    else:
        course = None

    user.chosen_course = course

    await db_session.flush()
    logger.info(f"User {user.id} changed their chosen course to '{new_chosen_course}'")


async def set_education_level(
    db_session: AsyncSession, user: User, new_education_level: EducationLevel
) -> None:
    user.education_level = new_education_level
    await db_session.flush()
    logger.info(
        f"User {user.id} changed their education level to '{new_education_level}'"
    )


async def set_referred_by(
    db_session: AsyncSession, user: User, new_referred_by_username: str
) -> None:
    new_referred_by = await get_user(db_session, username=new_referred_by_username)
    if not new_referred_by:
        raise ReferredByNotFoundError
    user.referred_by = new_referred_by
    await db_session.flush()
    logger.info(
        f"User {user.id} changed their referred by to '{new_referred_by_username}'"
    )


async def set_commitment(db_session: AsyncSession, user: User, commitment: int) -> None:
    user.commitment = commitment
    await db_session.flush()
    logger.info(f"User {user.id} changed their commitment to {commitment}")


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

    user_stats = await quiz_service.calc_user_stats(db_session, found_user.id)

    await db_session.refresh(
        found_user, ["chosen_course", "chosen_college", "user_info"]
    )
    # Get user answer timestamps
    stmt = (
        select(SessionQuestionUser.timestamp)
        .where(
            or_(
                SessionQuestionUser.choice_id.is_not(None),
                SessionQuestionUser.submitted_text != "",
            ),
            SessionQuestionUser.user_id == found_user.id,
        )
        .order_by(SessionQuestionUser.timestamp.desc())
    )

    result = await db_session.execute(stmt)
    user_answers_timestamps = [row[0] for row in result.all()]

    done_today, streak = get_streak_info(user_answers_timestamps)

    user_stats.update(
        {
            "id": found_user.id,
            "username": found_user.username,
            "school_id": found_user.school_id,
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
            "chosen_college": found_user.chosen_college,
            "chosen_course": found_user.chosen_course,
            "education_level": found_user.education_level,
            "streak": streak,
            "done_today": done_today,
            "dynamic_score": found_user.user_info.dynamic_score,
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
        func.count(SessionQuestionUser.id)
        .filter(
            or_(
                SessionQuestionUser.choice_id.is_not(None),
                SessionQuestionUser.timed_out.is_(True),
            )
        )
        .label("total_answers"),
        func.count(SessionQuestionUser.id)
        .filter(Choice.is_correct.is_(True))
        .label("correct_answers"),
    ).select_from(SessionQuestionUser)

    # Always join with Choice for correct answer counting
    query = query.outerjoin(Choice, SessionQuestionUser.choice_id == Choice.id)

    # Apply user filter
    query = query.where(SessionQuestionUser.user_id == user_id)

    # Only join with Question tables if we need to filter by subject
    if subject:
        query = (
            query.join(
                SessionQuestion,
                SessionQuestionUser.session_question_id == SessionQuestion.id,
            )
            .join(Question, SessionQuestion.question_id == Question.id)
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
    stmt = select(User.id)
    if school_filter:
        stmt = stmt.where(User.school_id == school_filter)
    if course_filter:
        stmt = stmt.join(User.chosen_course).where(Course.name == course_filter)
    if education_level_filter:
        stmt = stmt.where(User.education_level == education_level_filter)

    users_ids = await db_session.scalars(stmt)
    if score_type == "dynamic":
        return await quiz_service.get_ranked_users_stats_by_dynamic_score(
            users_ids, NUM_RANKED_USERS, asking_user_id
        )
    elif score_type == "percentage":
        return await quiz_service.get_ranked_users_stats_by_percentage(
            users_ids, NUM_RANKED_USERS, asking_user_id, subject
        )
    else:
        raise ValueError(f"Invalid score type: {score_type}")


async def get_user_infos(
    db_session: AsyncSession, users: list[User]
) -> list[dict[str, str | int | datetime.datetime]]:
    total_answers = (
        select(SessionQuestionUser.user_id, func.count(SessionQuestionUser.id))
        .where(SessionQuestionUser.user_id.in_(users))
        .group_by(SessionQuestionUser.user_id)
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
    statuses = await notifications_service.get_user_statuses(user_ids)

    # Get last online time for offline users
    offline_user_ids = [
        user_id for user_id, status in zip(user_ids, statuses) if status != "online"
    ]
    last_online_users = await chat_service.get_last_online_users(
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
            selectinload(User.chosen_college),
            selectinload(User.chosen_course),
        )
    )
    users = list(result.all())
    return users
