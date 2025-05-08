import contextlib
import logging
from typing import AsyncContextManager, AsyncIterator, Callable

from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# all of these are needed so that the Base subclasses are registered
import app.chat.models  # noqa: F401
import app.currency.models  # noqa: F401
import app.essays.models  # noqa: F401
import app.fcm.models  # noqa: F401
import app.files.models  # noqa: F401
import app.quiz.models  # noqa: F401
import app.schools.models  # noqa: F401
import app.tournaments.models  # noqa: F401
import app.users.models  # noqa: F401

logger = logging.getLogger(__name__)


class DatabaseSessionManager:
    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None

    def init(self, db_url: str) -> None:
        self._engine = create_async_engine(
            url=db_url,
            pool_pre_ping=True,
            isolation_level="READ COMMITTED",
        )
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
    async def use_db(self, db_url: str) -> AsyncIterator[None]:
        """Context manager that initializes the database connection and closes it when done.

        Args:
            db_url: Database connection URL

        Yields:
            None
        """
        self.init(db_url)
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
    ) -> AsyncIterator[Callable[[], AsyncContextManager[AsyncSession]]]:
        """
        Creates a factory function that yields new sessions all bound to the same connection/transaction.
        The transaction will be rolled back when the context is exited.

        This is useful for testing scenarios where you need multiple independent sessions
        that should all see the same database state and be rolled back together.

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

            # Roll back the transaction when we're done
            await connection.rollback()


db_manager = DatabaseSessionManager()
