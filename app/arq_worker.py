"""
These dependencies are carefully chosen so that the worker container only requires the dependencies it needs.
"""

from typing import Any, Literal

from arq.connections import RedisSettings
from database import db_manager
from quiz.tasks import task_mark_question_timed_out

from app.config import settings

REDIS_SETTINGS = RedisSettings.from_dsn(settings.redis_url)


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


async def startup(ctx: dict[Any, Any]):
    db_manager.init(settings.database_url)


async def shutdown(ctx: dict[Any, Any]):
    await db_manager.close()


async def ping() -> Literal["pong"]:
    return "pong"


class WorkerSettings:
    functions = [ping, task_mark_question_timed_out]
    redis_settings = REDIS_SETTINGS
    on_startup = startup
    on_shutdown = shutdown
