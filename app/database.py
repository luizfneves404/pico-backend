import asyncio
import contextlib
import logging
from typing import AsyncIterator

# all of these are needed so that the Base subclasses are registered
import chat.models  # noqa: F401
import currency.models  # noqa: F401
import essays.models  # noqa: F401
import files.models  # noqa: F401
import quiz.models  # noqa: F401
import schools.models  # noqa: F401
import tournaments.models  # noqa: F401
import users.models  # noqa: F401
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_scoped_session,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger(__name__)

# Module-level scoped session that will be initialized with the manager
sc_session: async_scoped_session[AsyncSession] | None = None


class DatabaseSessionManager:
    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None

    def init(self, db_url: str) -> None:
        global sc_session
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
        sc_session = async_scoped_session(
            self._sessionmaker, scopefunc=asyncio.current_task
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
        global sc_session
        if self._engine is None:
            return
        await self._engine.dispose()
        self._engine = None
        self._sessionmaker = None
        sc_session = None

    @contextlib.asynccontextmanager
    async def connect_db(self, db_url: str) -> AsyncIterator[None]:
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
    async def connect(self) -> AsyncIterator[AsyncConnection]:
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


db_manager = DatabaseSessionManager()


async def get_db_session():
    """
    This function is used to get a database session.
    It will begin a transaction and yield the session.
    The transaction will be committed if the session is used.
    If an exception is raised, the transaction will be rolled back.
    If you wish to keep the session useful after an error, use nested transactions.
    """
    async with db_manager.session() as session, session.begin():
        yield session
