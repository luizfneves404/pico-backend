import contextlib
import logging
import ssl
from contextlib import asynccontextmanager
from typing import Any, AsyncContextManager, AsyncGenerator, AsyncIterator, Callable

import logfire
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

# all of these are needed so that the Base subclasses are registered
import app.community.models  # noqa: F401
import app.countries.models  # noqa: F401
import app.education.models  # noqa: F401
import app.fcm.models  # noqa: F401
import app.files.models  # noqa: F401
import app.flows.models  # noqa: F401
import app.notifications.models  # noqa: F401
import app.users.models  # noqa: F401
import app.ws.models  # noqa: F401
from app.config import settings

logger = logging.getLogger(__name__)


CONNECTION_POOL_SIZE = 5
CONNECTION_POOL_MAX_OVERFLOW = 30

type SessionFactory = Callable[[], AsyncContextManager[AsyncSession]]


class DatabaseSessionManager:
    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None

    def init(
        self,
        db_url: str = settings.database_pool_url or settings.database_url,
        create_pool: bool = settings.database_pool_url is not None,
    ) -> None:
        """Initializes the database session manager.

        Args:
            db_url (str, optional): The database URL. If not provided, settings.database_pool_url will take precedence, and then settings.database_url.
            create_pool (bool, optional): Whether to create a pool of connections. Defaults to True if settings.database_pool_url is not None, otherwise False.
        """
        if settings.database_ssl_verify_full:
            sslctx = ssl.create_default_context(
                ssl.Purpose.SERVER_AUTH, cafile=settings.database_ca_cert_file
            )
            sslctx.check_hostname = True
        else:
            sslctx = False
        if create_pool:
            self._engine = create_async_engine(
                url=db_url,
                pool_pre_ping=True,
                isolation_level="READ COMMITTED",
                pool_size=CONNECTION_POOL_SIZE,
                max_overflow=CONNECTION_POOL_MAX_OVERFLOW,
                connect_args={"ssl": sslctx},
            )
        else:
            self._engine = create_async_engine(
                url=db_url,
                isolation_level="READ COMMITTED",
                connect_args={"ssl": sslctx},
                poolclass=NullPool,
            )
        logfire.instrument_sqlalchemy(engine=self._engine)
        self._sessionmaker = async_sessionmaker(
            bind=self._engine,
            expire_on_commit=False,
            autobegin=False,
            autoflush=False,
        )

    @property
    def engine(self) -> AsyncEngine:
        """Returns the engine instance.

        Raises:
            IOError: If DatabaseSessionManager is not initialized.
        """
        if self._engine is None:
            raise IOError("DatabaseSessionManager is not initialized")
        return self._engine

    async def close(self) -> None:
        if self._engine is None:
            return
        await self._engine.dispose()
        self._engine = None
        self._sessionmaker = None

    @contextlib.asynccontextmanager
    async def use_db(
        self,
        db_url: str = settings.database_pool_url or settings.database_url,
        create_pool: bool = settings.database_pool_url is not None,
    ) -> AsyncIterator[None]:
        """Context manager that initializes the database connection and closes it when done.

        Args:
            db_url: Database connection URL

        Yields:
            None
        """
        self.init(db_url=db_url, create_pool=create_pool)
        try:
            yield
        finally:
            await self.close()

    @contextlib.asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Does not start a transaction.
        Use session.begin() to start a transaction.
        """
        if self._sessionmaker is None:
            raise IOError("DatabaseSessionManager is not initialized")

        async with self._sessionmaker() as session:
            yield session

    @contextlib.asynccontextmanager
    async def session_with_transaction(self) -> AsyncIterator[AsyncSession]:
        async with self.session() as session, session.begin():
            yield session

    @contextlib.asynccontextmanager
    async def connect_with_transaction(self) -> AsyncIterator[AsyncConnection]:
        """
        This context manager is used to connect to the database.
        It will begin a transaction and yield the connection.
        The transaction will be committed if the connection is used.
        If an exception is raised, the transaction will be rolled back.
        """
        if self._engine is None:
            raise IOError("DatabaseSessionManager is not initialized")
        async with self._engine.begin() as connection:
            yield connection

    @contextlib.asynccontextmanager
    async def session_factory(
        self,
    ) -> AsyncIterator[SessionFactory]:
        """
        Creates a factory function that yields new sessions all bound to the same connection/transaction.
        The transaction will be rolled back when the context is exited.

        This is useful for testing scenarios where you need multiple independent sessions
        that should all see the same database state and be rolled back together.

        If you don't use this and you use different sessions, each session won't see what the other one is doing.
        For example, I was using this on the tests but not using it on the arq worker (which was using the session_with_transaction),
        and so the arq worker couldn't see the changes made by the tests.

        Yields:
            A callable that returns an async context manager yielding new sessions
        """
        async with self.connect_with_transaction() as connection:
            # Create a factory function that yields new sessions bound to the same connection
            @contextlib.asynccontextmanager
            async def get_session() -> AsyncIterator[AsyncSession]:
                if self._sessionmaker is None:
                    raise IOError("DatabaseSessionManager is not initialized")
                async with self._sessionmaker(
                    bind=connection, join_transaction_mode="create_savepoint"
                ) as session:
                    yield session

            yield get_session

            await connection.rollback()


db_manager = DatabaseSessionManager()


@asynccontextmanager
async def get_db_session_for_worker(
    ctx: dict[str, Any],
) -> AsyncGenerator[AsyncSession, None]:
    session_cm: AsyncContextManager[AsyncSession]
    if ctx["session_factory"]:
        # Use the same connection / outer transaction as the test
        session_cm = ctx["session_factory"]()
    else:
        # Normal production path
        session_cm = db_manager.session()
    async with session_cm as session, session.begin():
        yield session
