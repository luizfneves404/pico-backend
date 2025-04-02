import logging
from typing import (
    AsyncContextManager,
    AsyncGenerator,
    AsyncIterator,
    Callable,
    Generator,
    Literal,
    TypeVar,
)

import boto3
import pytest
import redis
from arq.worker import Worker, create_worker
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import app.arq_client as arq_client
from alembic.command import upgrade
from app.arq_worker import WorkerSettings
from app.config import settings
from app.database import DatabaseSessionManager, db_manager
from app.deps import get_db_session
from app.fcm_service import init_firebase
from app.redis_client import get_redis, use_redis
from app.users.models import User
from tests.db_utils import alembic_config_from_url, tmp_database
from tests.factories import UserFactory

T = TypeVar("T")
DEFAULT_TEST_PASSWORD = "defaultpassword"

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
def firebase_for_tests():
    init_firebase()


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

        from app.migration_state import get_migration_task

        await get_migration_task()

        yield tmp_url


@pytest.fixture(scope="session")
async def sessionmanager_for_tests(
    migrated_postgres_template: str,
) -> AsyncGenerator[DatabaseSessionManager, None]:
    async with db_manager.use_db(migrated_postgres_template):
        yield db_manager


@pytest.fixture()
async def session_factory(
    sessionmanager_for_tests: DatabaseSessionManager,
) -> AsyncGenerator[Callable[[], AsyncContextManager[AsyncSession]], None]:
    async with sessionmanager_for_tests.session_factory() as factory:
        yield factory


@pytest.fixture
async def session(
    session_factory: Callable[[], AsyncContextManager[AsyncSession]],
) -> AsyncIterator[AsyncSession]:
    """Get a new session for each test"""
    async with session_factory() as session:
        yield session


@pytest.fixture
async def redis_for_tests():
    async with use_redis():
        redis_client = get_redis()
        await redis_client.flushall()
        yield


@pytest.fixture()
async def arq_worker() -> AsyncGenerator[Worker, None]:
    async with arq_client.arq_redis():
        WorkerSettings.burst = True
        # Clear Redis at the start of the test session
        await arq_client.clear_redis()
        yield create_worker(WorkerSettings)


@pytest.fixture()
def app(
    session_factory: Callable[[], AsyncContextManager[AsyncSession]],
    arq_worker: Worker,
    redis_for_tests: redis.Redis,
    firebase_for_tests: None,
) -> Generator[FastAPI, None, None]:
    from app.main import app

    async def get_db_session_override():
        # Create a new session for each request
        async with session_factory() as session:
            async with session.begin():
                yield session

    app.dependency_overrides[get_db_session] = get_db_session_override
    yield app
    app.dependency_overrides.clear()
    app.dependency_overrides.clear()


@pytest.fixture
async def client(
    app: FastAPI,
) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


@pytest.fixture()
async def user(session: AsyncSession) -> User:
    async with session.begin():
        return await UserFactory.create(session=session)


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
