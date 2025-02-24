import bcrypt
from config import settings
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from users.models import College, Course, EducationLevel, School, User

SECRET_KEY = settings.secret_key

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


class UserNotFound(Exception):
    pass


class UsernameAlreadyExists(Exception):
    pass


class PhoneNumberAlreadyExists(Exception):
    pass


class EmailAlreadyExists(Exception):
    pass


class ReferredByNotFoundError(Exception):
    pass


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


async def get_user(
    db_session: AsyncSession, username: str | None = None, id: int | None = None
) -> User | None:
    """Get a user by either username or user_id.

    Args:
        db_session (AsyncSession): The database session
        username (str | None): Username to look up. Defaults to None.
        user_id (int | None): User ID to look up. Defaults to None.

    Returns:
        UserDBModel: The found user

    Raises:
        UserNotFound: If no user is found
        ValueError: If neither username nor user_id is provided
    """
    if username is None and id is None:
        raise ValueError("Must provide either username or user_id")

    if username is not None:
        condition = User.username == username
    else:
        condition = User.id == id

    user = (await db_session.scalars(select(User).where(condition))).first()

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
            college = College(name=chosen_college)
            db_session.add(college)

    if chosen_course:
        course = (
            await db_session.scalars(select(Course).where(Course.name == chosen_course))
        ).first()
        if not course:
            course = Course(name=chosen_course)
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
    college, course = await _get_or_create_college_course(
        db_session, chosen_college, chosen_course
    )

    if referred_by_username:
        referred_by = await get_user(db_session, username=referred_by_username)
        if not referred_by:
            raise ReferredByNotFoundError
    else:
        referred_by = None

    if school:
        school_obj = await _get_or_create_school(db_session, school)
    else:
        school_obj = None

    if school_id:
        db_user = User(
            username=username,
            hashed_password=get_password_hash(password),
            phone_number=phone_number,
            email=email,
            school_id=school_id,
            chosen_college=college,
            chosen_course=course,
            education_level=education_level,
            commitment=commitment,
            referred_by_id=referred_by.id if referred_by else None,
        )
    else:
        db_user = User(
            username=username,
            hashed_password=get_password_hash(password),
            phone_number=phone_number,
            email=email,
            school=school_obj,
            chosen_college=college,
            chosen_course=course,
            education_level=education_level,
            commitment=commitment,
            referred_by_id=referred_by.id if referred_by else None,
        )
    try:
        db_session.add(db_user)
        await db_session.flush()
        await db_session.refresh(db_user, ["referral_count"])
        return db_user
    except IntegrityError as e:
        if "username" in str(e.orig):
            raise UsernameAlreadyExists
        elif "phone_number" in str(e.orig):
            raise PhoneNumberAlreadyExists
        elif "email" in str(e.orig):
            raise EmailAlreadyExists
        else:
            raise


async def authenticate_user(db_session: AsyncSession, username: str, password: str):
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
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user
