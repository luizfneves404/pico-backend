import contextlib
from typing import AsyncIterator

# all of these are needed so that the Base subclasses are registered
import chatrooms.models  # noqa: F401
import users.models  # noqa: F401
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

users.models.init()


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

    async def close(self) -> None:
        if self._engine is None:
            return
        await self._engine.dispose()
        self._engine = None
        self._sessionmaker = None

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
