import itertools
import logging
from typing import (
    Any,
    AsyncGenerator,
    AsyncIterator,
    Awaitable,
    Callable,
    Generator,
    Literal,
    TypeVar,
)

import boto3
import pytest
from alembic.command import upgrade
from arq_client import ArqClientManager, arq_client_manager
from base import Base
from config import settings
from database import DatabaseSessionManager, db_manager
from fastapi import FastAPI
from httpx import AsyncClient
from redis_client import RedisManager, redis_manager
from schools.models import School
from sqlalchemy.ext.asyncio import AsyncSession
from tests.db_utils import alembic_config_from_url, tmp_database
from users.models import College, Course, EducationLevel, User
from users.service import get_password_hash

T = TypeVar("T")

logger = logging.getLogger(__name__)


class DummySESClient:
    def __init__(self) -> None:
        self.sent_emails: list[dict[str, str | dict[str, str]]] = []

    def send_email(
        self, Source: str, Destination: dict[str, str], Message: dict[str, str]
    ) -> dict[str, str]:
        self.sent_emails.append(
            {"Source": Source, "Destination": Destination, "Message": Message}
        )
        return {"MessageId": "dummy-id"}


@pytest.fixture
def dummy_ses_client() -> DummySESClient:
    """Returns a new dummy SES client instance for each test."""
    return DummySESClient()


@pytest.fixture(autouse=True)
def patch_boto3_client(
    monkeypatch: pytest.MonkeyPatch, dummy_ses_client: DummySESClient
):
    """Monkeypatch boto3.client so that SES clients are our dummy instance."""

    def dummy_boto3_client(
        service_name: str, region_name: str | None = None
    ) -> DummySESClient:
        if service_name == "ses":
            return dummy_ses_client
        raise ValueError("Unexpected service: " + service_name)

    monkeypatch.setattr(boto3, "client", dummy_boto3_client)


@pytest.fixture(scope="session", autouse=True)
def anyio_backend() -> tuple[Literal["asyncio"], dict[str, bool]]:
    return "asyncio", {"use_uvloop": True}


@pytest.fixture(scope="session")
def pg_url() -> str:
    """Provides base PostgreSQL URL for creating temporary databases."""
    return settings.database_url


@pytest.fixture(scope="session")
async def migrated_postgres_template(pg_url: str) -> AsyncGenerator[str, None]:
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
async def sessionmanager_for_tests(
    migrated_postgres_template: str,
) -> AsyncGenerator[DatabaseSessionManager, None]:
    db_manager.init(db_url=migrated_postgres_template)
    yield db_manager
    await db_manager.close()


@pytest.fixture()
async def session(
    sessionmanager_for_tests: DatabaseSessionManager,
) -> AsyncIterator[AsyncSession]:
    async with sessionmanager_for_tests.session() as session:
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


@pytest.fixture(scope="session")
async def redis_manager_for_tests():
    redis_manager.init(settings.redis_url)
    yield redis_manager
    await redis_manager.close()


@pytest.fixture(scope="session")
async def arq_client_manager_for_tests():
    await arq_client_manager.init(settings.redis_url)
    yield arq_client_manager
    await arq_client_manager.close()


@pytest.fixture()
def app() -> Generator[FastAPI, None, None]:
    from main import app

    yield app


@pytest.fixture()
async def client(
    session: AsyncSession,
    redis_manager_for_tests: RedisManager,
    arq_client_manager_for_tests: ArqClientManager,
    app: FastAPI,
) -> AsyncIterator[AsyncClient]:
    from httpx import ASGITransport

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


class _Auto:
    """
    Sentinel value indicating an automatic default will be used.
    """

    def __bool__(self) -> Literal[False]:
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
USER_PHONE_NUMBER_SEQUENCE = sequence(lambda n: f"tel:+55-21-99933-2{n:03d}")
USER_USERNAME_SEQUENCE = sequence(lambda n: f"testuser{n}")

SCHOOL_NAME_SEQUENCE = sequence(lambda n: f"School {n}")
COLLEGE_NAME_SEQUENCE = sequence(lambda n: f"College {n}")
COURSE_NAME_SEQUENCE = sequence(lambda n: f"Course {n}")
DEFAULT_TEST_PASSWORD = "defaultpassword"


async def create_college_courses(
    session: AsyncSession, name: str = Auto, num_courses: int = 3
):
    if name is Auto:
        name = next(COLLEGE_NAME_SEQUENCE)
    college = College(name=name)
    session.add(college)

    courses: list[Course] = []
    for _ in range(num_courses):
        course = Course(name=next(COURSE_NAME_SEQUENCE))
        session.add(course)
        courses.append(course)

    college.courses = courses
    return college


@pytest.fixture
async def school_factory(session: AsyncSession):
    async def create_school(name: str = Auto) -> School:
        if name is Auto:
            name = next(SCHOOL_NAME_SEQUENCE)
        school = School(name=name)
        session.add(school)
        return school

    return create_school


@pytest.fixture
def user_factory(
    session: AsyncSession, school_factory: Callable[[], Awaitable[School]]
) -> Callable[[], Awaitable[User]]:
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
        async with session.begin():
            hashed_password = get_password_hash(password or DEFAULT_TEST_PASSWORD)

            # Handle school
            if school_id is Auto:
                school = await school_factory()
            elif school_id is None:
                school = None
            else:
                school = await session.get(School, school_id)

            # Initialize college and course variables
            chosen_college = None
            chosen_course = None

            # Handle college and course
            if chosen_college_id is Auto and chosen_course_id is Auto:
                chosen_college = await create_college_courses(session)
                chosen_course = chosen_college.courses[0]
            else:
                if chosen_college_id is not Auto and chosen_college_id is not None:
                    chosen_college = await session.get(College, chosen_college_id)

                if chosen_course_id is not Auto and chosen_course_id is not None:
                    chosen_course = await session.get(Course, chosen_course_id)

            user = User(
                username=username or next(USER_USERNAME_SEQUENCE),
                hashed_password=hashed_password,
                phone_number=phone_number or next(USER_PHONE_NUMBER_SEQUENCE),
                email=email or next(USER_EMAIL_SEQUENCE),
                school=school,
                chosen_college=chosen_college,
                chosen_course=chosen_course,
                education_level=education_level
                or EducationLevel.THIRD_YEAR_HIGH_SCHOOL,
                commitment=commitment or 17,
                is_premium=is_premium or False,
                is_bot=False,
                bot_difficulty=None,
            )
            if save:
                session.add(user)
            else:
                user.chosen_college = chosen_college
                user.chosen_course = chosen_course
                if school:
                    user.school = school
                else:
                    user.school_id = None
            return user

    return create_user


@pytest.fixture
def bot_factory(session: AsyncSession):
    async def create_bot(
        username: str = Auto,
        bot_difficulty: float = Auto,
    ) -> User:
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


@pytest.fixture
async def user(user_factory: Callable[[], Awaitable[User]]) -> User:
    return await user_factory()


@pytest.fixture()
async def auth_client(client: AsyncClient, user: User) -> AsyncIterator[AsyncClient]:
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
