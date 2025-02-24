import itertools
import logging
from typing import Any, AsyncIterator, Callable, Generator, TypeVar

import pytest
from alembic.command import upgrade
from base import Base
from config import settings
from database import db_manager
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.db_utils import alembic_config_from_url, tmp_database
from users.models import College, Course, School, User
from users.user_service import get_password_hash

T = TypeVar("T")

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session", autouse=True)
def anyio_backend():
    return "asyncio", {"use_uvloop": True}


@pytest.fixture(scope="session")
def pg_url() -> str:
    """Provides base PostgreSQL URL for creating temporary databases."""
    return settings.database_url


@pytest.fixture(scope="session")
async def migrated_postgres_template(pg_url):
    """
    Creates temporary database and applies migrations.

    Has "session" scope, so is called only once per tests run.
    """
    async with tmp_database(pg_url, "pytest") as tmp_url:
        alembic_config = alembic_config_from_url(tmp_url)
        upgrade(alembic_config, "head")

        from migration_state import get_migration_task

        await get_migration_task()

        yield tmp_url


@pytest.fixture(scope="session")
async def sessionmanager_for_tests(migrated_postgres_template):
    db_manager.init(db_url=migrated_postgres_template)
    # can add another init (redis, etc...)
    yield db_manager
    await db_manager.close()


@pytest.fixture()
async def session(sessionmanager_for_tests) -> AsyncIterator[AsyncSession]:
    async with db_manager.session() as session, session.begin():
        yield session

    # Clean tables after each test. I tried:
    # 1. Create new database using an empty `migrated_postgres_template` as template
    # (postgres could copy whole db structure)
    # 2. Do TRUNCATE after each test.
    # 3. Do DELETE after each test.
    # DELETE FROM is the fastest
    # https://www.lob.com/blog/truncate-vs-delete-efficiently-clearing-data-from-a-postgres-table
    # BUT DELETE FROM query does not reset any AUTO_INCREMENT counter
    async with db_manager.connect() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            # Clean tables in such order that tables which depend on another go first
            await conn.execute(table.delete())


@pytest.fixture()
def app():
    from main import app

    yield app


@pytest.fixture()
async def client(session, app):
    from httpx import ASGITransport

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


class _Auto:
    """
    Sentinel value indicating an automatic default will be used.
    """

    def __bool__(self):
        # Allow `Auto` to be used like `None` or `False` in boolean expressions
        return False


Auto: Any = _Auto()


def sequence(func: Callable[[int], T]) -> Generator[T, None, None]:
    """
    Generates a sequence of values from a sequence of integers starting at zero,
    passed through the callable, which must take an integer argument.
    """
    return (func(n) for n in itertools.count())


USER_EMAIL_SEQUENCE = sequence(lambda n: f"testuser{n}@example.com")
USER_PHONE_NUMBER_SEQUENCE = sequence(lambda n: f"+5521999205{str(n).zfill(3)}")
USER_USERNAME_SEQUENCE = sequence(lambda n: f"testuser{n}")

SCHOOL_NAME_SEQUENCE = sequence(lambda n: f"School {n}")
COLLEGE_NAME_SEQUENCE = sequence(lambda n: f"College {n}")
COURSE_NAME_SEQUENCE = sequence(lambda n: f"Course {n}")
DEFAULT_TEST_PASSWORD = "defaultpassword"


async def create_school(session: AsyncSession, name: str = Auto):
    if name is Auto:
        name = next(SCHOOL_NAME_SEQUENCE)
    school = School(name=name)
    session.add(school)
    return school


async def create_college_courses(
    session: AsyncSession, name: str = Auto, num_courses: int = 3
):
    if name is Auto:
        name = next(COLLEGE_NAME_SEQUENCE)
    college = College(name=name)
    logger.info("is in transaction before adding college", session.in_transaction())
    session.add(college)

    courses = []
    for _ in range(num_courses):
        course = Course(name=next(COURSE_NAME_SEQUENCE))
        session.add(course)
        courses.append(course)

    college.courses = courses
    return college


@pytest.fixture
def user_factory(session: AsyncSession):
    async def create_user(
        username: str = Auto,
        password: str = Auto,
        phone_number: str = Auto,
        email: str = Auto,
        school_id: int | None = Auto,
        chosen_college_id: int | None = Auto,
        chosen_course_id: int | None = Auto,
        education_level: str = Auto,
        commitment: int = Auto,
        is_premium: bool = Auto,
        save: bool = True,
    ) -> User:
        logger.info("is in transaction before creating user", session.in_transaction())
        hashed_password = get_password_hash(password or DEFAULT_TEST_PASSWORD)
        if school_id is Auto:
            school = await create_school(session)
        if chosen_college_id is Auto and chosen_course_id is Auto:
            college = await create_college_courses(session)
            chosen_college_id = college.id
            chosen_course_id = college.courses[0].id
        elif chosen_college_id is Auto:
            chosen_college_id = None
        elif chosen_course_id is Auto:
            chosen_course_id = None

        user = User(
            username=username or next(USER_USERNAME_SEQUENCE),
            hashed_password=hashed_password,
            phone_number=phone_number or next(USER_PHONE_NUMBER_SEQUENCE),
            email=email or next(USER_EMAIL_SEQUENCE),
            school_id=school.id,
            chosen_college_id=chosen_college_id,
            chosen_course_id=chosen_course_id,
            education_level=education_level or "TYHS",
            commitment=commitment or 17,
            is_premium=is_premium,
            is_bot=False,
            bot_difficulty=None,
        )
        if save:
            session.add(user)
            await session.refresh(user)
        else:
            user.chosen_college = college
            user.chosen_course = college.courses[0]
        return user

    logger.info("is in transaction after user factory", session.in_transaction())
    return create_user


@pytest.fixture
def bot_factory(session: AsyncSession):
    async def create_bot(
        username: str = Auto,
        bot_difficulty: float = Auto,
    ):
        hashed_password = get_password_hash("defaultpassword")
        bot = User(
            username=username or next(USER_USERNAME_SEQUENCE),
            phone_number=next(USER_PHONE_NUMBER_SEQUENCE),
            email=next(USER_EMAIL_SEQUENCE),
            hashed_password=hashed_password,
            is_bot=True,
            bot_difficulty=bot_difficulty or 0.2,
        )
        return bot

    return create_bot


@pytest.fixture()
async def auth_client(client, user_factory):
    user = await user_factory()

    token_response = await client.post(
        "/token/pair",
        data={
            "username": user.username,
            "password": DEFAULT_TEST_PASSWORD,
        },
    )
    token_data = token_response.json()

    client.headers["Authorization"] = f"Bearer {token_data['access']}"

    yield client
