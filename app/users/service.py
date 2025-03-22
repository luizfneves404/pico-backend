import datetime
import logging
from typing import Literal

import amp
import bcrypt
import mail
import timezone
from fastapi import BackgroundTasks
from pydantic import TypeAdapter, ValidationError
from schools.models import School
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from users.models import College, Course, EducationLevel, User
from users.schemas import PhoneNumber

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
    background_tasks: BackgroundTasks,
    db_session: AsyncSession,
    username: str,
    password: str,
    phone_number: str,
    email: str,
    chosen_college: str,
    chosen_course: str,
    education_level: EducationLevel,
    commitment: int,
    referred_by_username: str | None = None,
    school: str = "",  # deprecated
    school_id: int | None = None,
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
        school (str, optional): Deprecated. The name of the school the user is attending.
        school_id (int | None, optional): The ID of the school the user is attending. Defaults to None.

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
    )

    # Handle school information
    if school_id:
        db_user.school_id = school_id
    elif school:
        db_user.school = await _get_or_create_school(db_session, school)

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

    await db_session.refresh(db_user, ["referral_count", "school"])

    # TODO: create user info

    mail.send_email(
        background_tasks,
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
    amp.delete_user(user.id)
    await db_session.delete(user)
    await db_session.flush()


async def check_contacts(
    db_session: AsyncSession, raw_phone_numbers: list[str]
) -> list[User]:
    phone_numbers = []
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


def send_bulk_email(
    background_tasks: BackgroundTasks,
    users: list[User],
    subject: str,
    html_string: str,
    id_zero_padding: int = 0,
) -> None:
    messages = []
    for user in users:
        # Replace template markers with user data
        personalized_html = (
            html_string.replace(
                "%%id%%",
                (
                    str(user.id).zfill(id_zero_padding)
                    if id_zero_padding
                    else str(user.id)
                ),
            )
            .replace("%%username%%", user.username)
            .replace("%%email%%", user.email)
        )
        messages.append(
            mail.EmailMessage(
                subject=subject,
                body_html=personalized_html,
                to_emails=[user.email],
            )
        )
    mail.send_email(background_tasks, messages)
    logger.info(f"Sent bulk email to {len(users)} users")


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


async def get_user_stats_from_username(db_session: AsyncSession, username: str) -> dict:
    user = await get_user(db_session, username=username)
    if not user:
        raise UserNotFoundError
    return await get_user_stats(user)


async def get_user_stats_from_id(db_session: AsyncSession, user_id: int) -> dict:
    user = await get_user(db_session, id=user_id)
    return await get_user_stats(user)


async def get_user_stats(user: User) -> dict:
    user_stats = await quiz_service.acalc_user_stats(user.id)

    user_out = (await ato_user_out([user.id]))[0]
    user_answers_timestamps = [
        answer["timestamp"]
        async for answer in SessionQuestionUser.objects.filter(
            Q(choice__isnull=False) | ~Q(submitted_text__exact=""),
            user_id=user.id,
        )
        .order_by("-timestamp")
        .values("timestamp")
    ]
    done_today, streak = get_streak_info(user_answers_timestamps)

    user_stats.update(
        {
            "id": user.id,
            "username": user.username,
            "school": user_out["school"],
            "school_id": user_out["school_id"],
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
            "chosen_college": user_out["chosen_college"],
            "chosen_course": user_out["chosen_course"],
            "education_level": user_out["education_level"],
            "streak": streak,
            "done_today": done_today,
        }
    )
    return user_stats


async def get_ranking(
    db_session: AsyncSession,
    asking_user_id: int,
    school_id_filter: int | None,
    course_filter: str | None,
) -> list[dict]:
    stmt = select(User.id)
    if school_id_filter:
        stmt = stmt.where(User.school_id == school_id_filter)
    if course_filter:
        stmt = stmt.join(User.chosen_course).where(Course.name == course_filter)

    users_ids = await db_session.scalars(stmt)
    return await quiz_service.get_top_users_stats(
        users_ids, NUM_RANKED_USERS, asking_user_id
    )


def get_user_infos(users: list[User]) -> list[dict]:
    total_answers = (
        SessionQuestionUser.objects.filter(user__in=users)
        .values("user")
        .annotate(total_answers=Count("id"))
    )
    answer_dict = {item["user"]: item["total_answers"] for item in total_answers}

    return [
        {
            "username": user.username,
            "total_answers": answer_dict.get(user.id, 0),
            "date_joined": user.date_joined,
        }
        for user in users
    ]


async def get_online_info(user_ids: list[int]) -> list[dict]:
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
    statuses = await notification_utils.aget_user_statuses(user_ids)

    # Get last online time for offline users
    offline_user_ids = [
        user_id for user_id, status in zip(user_ids, statuses) if status != "online"
    ]
    last_online_users = await sync_to_async(chat_service.get_last_online_users)(
        offline_user_ids
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


async def get_balance(user_id: int) -> int:
    user = await User.objects.filter(id=user_id).values("balance").afirst()
    if not user:
        raise UserNotFoundError
    return user["balance"]
