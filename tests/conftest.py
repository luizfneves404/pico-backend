import contextlib
import logging
from typing import (
    AsyncContextManager,
    AsyncGenerator,
    AsyncIterator,
    Awaitable,
    Callable,
    Generator,
    Literal,
    Sequence,
    TypeVar,
)

import pytest
import redis
from arq.worker import Worker, create_worker
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from httpx_ws.transport import ASGIWebSocketTransport
from sqlalchemy.ext.asyncio import AsyncSession

import app.arq_client as arq_client
import app.users.jwt_token as jwt_token
from alembic.command import upgrade
from app.arq_worker import WorkerSettings
from app.config import settings
from app.database import DatabaseSessionManager, db_manager
from app.deps import get_db_session
from app.fcm.fcm_service import init_firebase
from app.redis_client import get_redis, use_redis
from app.users.models import User
from app.ws.routers import get_db_session_websocket
from tests.db_utils import alembic_config_from_url, tmp_database
from tests.factories import UserFactory

T = TypeVar("T")
DEFAULT_TEST_PASSWORD = "defaultpassword"
BASE_URL = "http://test"
logger = logging.getLogger(__name__)


class DummySESClient:
    def __init__(self) -> None:
        self.sent_emails: list[
            dict[
                str,
                str
                | dict[str, Sequence[str]]
                | dict[str, dict[str, str | dict[str, str]]],
            ]
        ] = []

    def send_email(
        self,
        Source: str,
        Destination: dict[str, Sequence[str]],
        Message: dict[str, dict[str, str | dict[str, str]]],
    ) -> dict[str, str]:
        self.sent_emails.append(
            {"Source": Source, "Destination": Destination, "Message": Message}
        )
        return {"MessageId": "dummy-id"}


@pytest.fixture(autouse=True)
def dummy_ses_client() -> DummySESClient:
    """Returns a new dummy SES client instance for each test."""
    import app.mail as mail

    dummy_ses_client = DummySESClient()
    mail.inject_client(dummy_ses_client)
    return dummy_ses_client


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


@pytest.fixture()
async def websocket_session_factory(
    sessionmanager_for_tests: DatabaseSessionManager,
) -> AsyncGenerator[Callable[[], AsyncContextManager[AsyncSession]], None]:
    """
    Creates a session factory for WebSocket tests that commits data to make it
    visible across different event loops and database connections.
    """

    @contextlib.asynccontextmanager
    async def get_websocket_session() -> AsyncIterator[AsyncSession]:
        async with sessionmanager_for_tests.websocket_session() as session:
            yield session

    yield get_websocket_session


@pytest.fixture
async def session(
    session_factory: Callable[[], AsyncContextManager[AsyncSession]],
) -> AsyncIterator[AsyncSession]:
    """Get a new session for each test"""
    async with session_factory() as session:
        yield session


@pytest.fixture
async def websocket_session(
    websocket_session_factory: Callable[[], AsyncContextManager[AsyncSession]],
) -> AsyncIterator[AsyncSession]:
    """Get a new WebSocket-compatible session for each test"""
    async with websocket_session_factory() as session:
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
    websocket_session_factory: Callable[[], AsyncContextManager[AsyncSession]],
    arq_worker: Worker,
    redis_for_tests: redis.Redis,
    firebase_for_tests: None,
) -> Generator[FastAPI, None, None]:
    from app.main import fastapi_app

    async def get_db_session_override():
        async with session_factory() as session:
            async with session.begin():
                yield session

    fastapi_app.dependency_overrides[get_db_session] = get_db_session_override

    async def get_db_session_websocket_override():
        async with websocket_session_factory() as session:
            yield session

    fastapi_app.dependency_overrides[get_db_session_websocket] = (
        get_db_session_websocket_override
    )
    yield fastapi_app
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
async def client(
    app: FastAPI,
) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=BASE_URL
    ) as client:
        yield client


@pytest.fixture
async def ws_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGIWebSocketTransport(app)) as client:
        yield client


@pytest.fixture()
async def user(session: AsyncSession) -> User:
    async with session.begin():
        return await UserFactory.create(session)


@pytest.fixture()
async def websocket_user(
    sessionmanager_for_tests: DatabaseSessionManager,
) -> AsyncGenerator[User, None]:
    """
    Creates a user that's committed to the database for WebSocket tests.
    This ensures the user is visible to WebSocket sessions running in different event loops.
    """
    # Use a regular session with transaction to commit the user
    async with sessionmanager_for_tests.session_with_transaction() as session:
        user = await UserFactory.create(session)
        # Transaction is committed when context exits

    yield user

    # Clean up: delete the user after the test
    async with sessionmanager_for_tests.session_with_transaction() as session:
        await session.delete(user)


@pytest.fixture
def access_token(user: User) -> str:
    return jwt_token.generate_tokens(user)[0]


@pytest.fixture
def websocket_access_token(websocket_user: User) -> str:
    return jwt_token.generate_tokens(websocket_user)[0]


@pytest.fixture
async def user_client(
    client: AsyncClient, access_token: str
) -> AsyncIterator[AsyncClient]:
    client.headers["Authorization"] = f"Bearer {access_token}"

    yield client


@pytest.fixture
async def user2(session: AsyncSession) -> User:
    async with session.begin():
        return await UserFactory.create(session)


@pytest.fixture
def user_factory(session: AsyncSession) -> Callable[[int], Awaitable[Sequence[User]]]:
    """
    Returns a factory that creates a specified number of users.
    Args:
        n (int): Number of users to create.
    Returns:
        Awaitable[Sequence[User]]: Awaitable that yields the created users.
    """

    async def factory(n: int) -> Sequence[User]:
        async with session.begin():
            return await UserFactory.create_batch(n, session)

    return factory


@pytest.fixture
def user_client_factory(client: AsyncClient, session: AsyncSession):
    async def factory(n: int) -> list[tuple[User, AsyncClient]]:
        async with session.begin():
            users = await UserFactory.create_batch(n, session)
        pairs: list[tuple[User, AsyncClient]] = []
        for user in users:
            token_response = await client.post(
                "/api/token/pair",
                data={
                    "username": user.username,
                    "password": DEFAULT_TEST_PASSWORD,
                },
            )
            token_data = token_response.json()
            user_client = AsyncClient(
                base_url=client.base_url,
                headers={
                    **client.headers,
                    "Authorization": f"Bearer {token_data['access']}",
                },
            )
            pairs.append((user, user_client))
        return pairs

    return factory
