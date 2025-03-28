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
from database import DatabaseSessionManager, db_manager
from fastapi import FastAPI
from httpx import AsyncClient
from quiz.models import Choice, Question, QuestionType, Quiz, SessionQuestion
from redis_client import RedisManager, redis_manager
from schools.models import School
from sqlalchemy.ext.asyncio import AsyncSession
from tests.db_utils import alembic_config_from_url, tmp_database
from tests.factories import UserFactory
from users.models import College, Course, User

from app.config import settings

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
    async with db_manager.connect_db(migrated_postgres_template):
        yield db_manager


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
QUESTION_TEXT_SEQUENCE = sequence(lambda n: f"Test question {n}")
DEFAULT_TEST_PASSWORD = "defaultpassword"


async def create_college_courses(
    session: AsyncSession, name: str = Auto, num_courses: int = 3
):
    if name is Auto:
        name = next(COLLEGE_NAME_SEQUENCE)
    college = College(name=name, user_submitted=True)
    session.add(college)

    courses: list[Course] = []
    for _ in range(num_courses):
        course = Course(name=next(COURSE_NAME_SEQUENCE), user_submitted=True)
        session.add(course)
        courses.append(course)

    college.courses = courses
    return college


async def create_school(session: AsyncSession, name: str = Auto) -> School:
    if name is Auto:
        name = next(SCHOOL_NAME_SEQUENCE)
    school = School(name=name, user_submitted=True)
    session.add(school)
    return school


@pytest.fixture()
async def user(session: AsyncSession) -> User:
    return await UserFactory.create()


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


@pytest.fixture
def question_factory(session: AsyncSession) -> Callable[..., Awaitable[Question]]:
    async def create_question(
        text: str = Auto,
        subject: str = Auto,
        difficulty: str = Auto,
        source: str = Auto,
        is_active: bool = Auto,
        allow_resubmit: bool = Auto,
        choices: list[dict[str, str | bool]] | None = None,
        answer_text: str = Auto,
        save: bool = True,
    ) -> Question:
        if text is Auto:
            text = next(QUESTION_TEXT_SEQUENCE)
        if subject is Auto:
            subject = "Matemática"
        if difficulty is Auto:
            difficulty = "Fácil"
        if source is Auto:
            source = "ENEM"
        if is_active is Auto:
            is_active = True
        if allow_resubmit is Auto:
            allow_resubmit = False
        if answer_text is Auto:
            answer_text = "This is the correct answer"

        async with session.begin():
            question = Question(
                text=text,
                subject=subject,
                difficulty=difficulty,
                source=source,
                is_active=is_active,
                allow_resubmit=allow_resubmit,
                answer_text=answer_text,
            )

            if choices is not None:
                for i, choice_data in enumerate(choices):
                    choice = Choice(
                        text=choice_data.get("text", f"Choice {i}"),
                        is_correct=choice_data.get("is_correct", False),
                        order=i,
                    )
                    question.choices.append(choice)

            if save:
                session.add(question)

        return question

    return create_question


@pytest.fixture
async def quiz1(
    session: AsyncSession, question_factory: Callable[..., Awaitable[Question]]
) -> AsyncIterator[Quiz]:
    async with session.begin():
        quiz = Quiz(
            question_type=QuestionType.MULTIPLE_CHOICE,
            source_filter="",
            difficulty="",
        )
        session.add(quiz)

        # Create 10 multiple choice questions
        for _ in range(10):
            question: Question = await question_factory(
                choices=[
                    {"text": "Correct answer", "is_correct": True},
                    {"text": "Wrong answer 1", "is_correct": False},
                    {"text": "Wrong answer 2", "is_correct": False},
                    {"text": "Wrong answer 3", "is_correct": False},
                    {"text": "Wrong answer 4", "is_correct": False},
                ]
            )
            session_question = SessionQuestion(
                session_id=quiz.id,
                question_id=question.id,
                order=len(quiz.questions),
            )
            session.add(session_question)

    yield quiz


@pytest.fixture
async def quiz2(
    session: AsyncSession, question_factory: Callable[..., Awaitable[Question]]
) -> AsyncIterator[Quiz]:
    async with session.begin():
        quiz = Quiz(
            question_type=QuestionType.MULTIPLE_CHOICE,
            source_filter="",
            difficulty="",
        )
        session.add(quiz)

        # Create 10 multiple choice questions
        for _ in range(10):
            question: Question = await question_factory(
                choices=[
                    {"text": "Correct answer", "is_correct": True},
                    {"text": "Wrong answer 1", "is_correct": False},
                    {"text": "Wrong answer 2", "is_correct": False},
                    {"text": "Wrong answer 3", "is_correct": False},
                    {"text": "Wrong answer 4", "is_correct": False},
                ]
            )
            session_question = SessionQuestion(
                session_id=quiz.id,
                question_id=question.id,
                order=len(quiz.questions),
            )
            session.add(session_question)

    yield quiz


@pytest.fixture
async def open_ended_quiz1(
    session: AsyncSession, question_factory: Callable[..., Awaitable[Question]]
) -> AsyncIterator[Quiz]:
    async with session.begin():
        quiz = Quiz(
            question_type=QuestionType.OPEN_ENDED,
            source_filter="",
            difficulty="",
        )
        session.add(quiz)

        # Create 10 open ended questions
        for _ in range(10):
            question: Question = await question_factory(
                text=next(QUESTION_TEXT_SEQUENCE),
                answer_text="This is the correct answer",
            )
            session_question = SessionQuestion(
                session_id=quiz.id,
                question_id=question.id,
                order=len(quiz.questions),
            )
            session.add(session_question)

    yield quiz


@pytest.fixture
async def open_ended_quiz2(
    session: AsyncSession, question_factory: Callable[..., Awaitable[Question]]
) -> AsyncIterator[Quiz]:
    async with session.begin():
        quiz = Quiz(
            question_type=QuestionType.OPEN_ENDED,
            source_filter="",
            difficulty="",
        )
        session.add(quiz)

        # Create 10 open ended questions
        for _ in range(10):
            question: Question = await question_factory(
                text=f"Open ended question {next(itertools.count())}",
                answer_text="This is the correct answer",
            )
            session_question = SessionQuestion(
                session_id=quiz.id,
                question_id=question.id,
                order=len(quiz.questions),
            )
            session.add(session_question)

    yield quiz
