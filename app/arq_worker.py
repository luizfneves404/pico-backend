"""
Shares dependencies with the main app in order to reduce complexity of dependency management.
Otherwise i would have to take a lot of care not to import certain files, etc.
"""

import asyncio
import logging.config
import sys
from typing import Any, Literal, Sequence

import uvloop
from arq import run_worker
from arq.connections import RedisSettings
from arq.cron import CronJob, cron
from arq.typing import SecondsTimedelta, StartupShutdown, WorkerCoroutine
from arq.worker import Function, check_health

import app.arq_client as arq_client
import app.redis_client as redis_client
from app.config import settings
from app.database import SessionFactory, db_manager
from app.fcm.fcm_service import task_send_notifications
from app.firebase_config import init_firebase
from app.flows.question_service import (
    task_generate_transcriptions,
    task_generate_flow_cover_image,
)
from app.flows.question_utils import (
    task_compute_question_embeddings,
    task_categorize_minor_tags,
    task_categorize_major_tags,
    task_generate_question_answers,
    task_analyze_question_quantitativeness,
    task_consolidate_flow_tags,
    task_generate_and_consolidate_tags,
)
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
    session_factory: SessionFactory | None,
) -> type:
    async def startup(ctx: dict[str, Any]):
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

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
            task_generate_transcriptions,
            task_compute_question_embeddings,
            task_categorize_minor_tags,
            task_categorize_major_tags,
            task_generate_question_answers,
            task_analyze_question_quantitativeness,
            task_generate_flow_cover_image,
            task_consolidate_flow_tags,
            task_generate_and_consolidate_tags,
        ]
        redis_settings: RedisSettings = RedisSettings.from_dsn(redis_url)
        on_startup: StartupShutdown | None = startup
        on_shutdown: StartupShutdown | None = shutdown
        burst: bool = burst_mode
        cron_jobs: Sequence[CronJob] | None = None
        health_check_interval: SecondsTimedelta = 30
        ctx: dict[str, Any] = {"session_factory": session_factory}
        job_timeout: SecondsTimedelta = 900

    return WorkerSettings


if __name__ == "__main__":
    settings = make_worker_settings(
        redis_url=settings.redis_url,
        database_url=settings.database_url,
        burst_mode=False,
        log_configured=False,
        session_factory=None,
    )
    if "--check" in sys.argv:
        check_health(settings)
    else:
        run_worker(settings)
