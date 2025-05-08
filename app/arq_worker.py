"""
Shares dependencies with the main app in order to reduce complexity of dependency management.
Otherwise i would have to take a lot of care not to import certain files, etc.
"""

import logging.config
from typing import Any, Literal, Optional, Sequence

from arq.connections import RedisSettings
from arq.cron import CronJob
from arq.typing import StartupShutdown, WorkerCoroutine
from arq.worker import Function

import app.arq_client as arq_client
import app.redis_client as redis_client
from app.config import settings
from app.database import db_manager
from app.essays.tasks import task_extract_and_clean
from app.fcm.fcm_service import init_firebase, task_send_notifications
from app.mail import task_send_email
from app.quiz.tasks import task_mark_question_timed_out

REDIS_SETTINGS = RedisSettings.from_dsn(settings.redis_url)

logging.config.fileConfig("logging.ini", disable_existing_loggers=False)


async def startup(ctx: dict[Any, Any]):
    init_firebase()
    db_manager.init(settings.database_url)
    redis_client.init()
    await arq_client.init()


async def shutdown(ctx: dict[Any, Any]):
    await db_manager.close()
    await redis_client.close()
    await arq_client.close()


async def ping(ctx: dict[Any, Any]) -> Literal["pong"]:
    return "pong"


class WorkerSettings:
    functions: Sequence[WorkerCoroutine | Function] = [
        ping,
        task_mark_question_timed_out,
        task_send_email,
        task_send_notifications,
        task_extract_and_clean,
    ]
    redis_settings: RedisSettings = REDIS_SETTINGS
    on_startup: Optional[StartupShutdown] = startup
    on_shutdown: Optional[StartupShutdown] = shutdown
    burst: bool = False
    cron_jobs: Optional[Sequence[CronJob]] = None
