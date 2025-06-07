"""
Shares dependencies with the main app in order to reduce complexity of dependency management.
Otherwise i would have to take a lot of care not to import certain files, etc.
"""

import logging.config
from typing import Any, Literal, Sequence

from arq import run_worker
from arq.connections import RedisSettings
from arq.cron import CronJob
from arq.typing import StartupShutdown, WorkerCoroutine
from arq.worker import Function

import app.arq_client as arq_client
import app.redis_client as redis_client
from app.config import settings
from app.database import db_manager
from app.fcm.fcm_service import init_firebase, task_send_notifications
from app.flows.tasks import task_mark_question_timed_out
from app.logging_config import get_logging_config
from app.mail import task_send_email


async def ping(ctx: dict[Any, Any]) -> Literal["pong"]:
    return "pong"


def make_worker_settings(
    *,
    redis_url: str,
    database_url: str,
    burst_mode: bool,
    log_configured: bool,
) -> type:
    async def startup(ctx: dict[str, Any]):
        if not log_configured:
            logging.config.dictConfig(get_logging_config())

        init_firebase()
        db_manager.init(database_url)
        redis_client.init()
        await arq_client.init()

    async def shutdown(ctx: dict[str, Any]):
        await db_manager.close()
        await redis_client.close()
        await arq_client.close()

    class WorkerSettings:
        functions: Sequence[WorkerCoroutine | Function] = [
            ping,
            task_mark_question_timed_out,
            task_send_email,
            task_send_notifications,
        ]
        redis_settings: RedisSettings = RedisSettings.from_dsn(redis_url)
        on_startup: StartupShutdown | None = startup
        on_shutdown: StartupShutdown | None = shutdown
        burst: bool = burst_mode
        cron_jobs: Sequence[CronJob] | None = None

    return WorkerSettings


if __name__ == "__main__":
    run_worker(
        make_worker_settings(
            redis_url=settings.redis_url,
            database_url=settings.database_url,
            burst_mode=False,
            log_configured=False,
        )
    )
