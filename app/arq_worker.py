"""
Shares dependencies with the main app in order to reduce complexity of dependency management.
Otherwise i would have to take a lot of care not to import certain files, etc.
"""

import asyncio
import logging.config
from typing import Any, Literal, Sequence

import uvloop
from arq import run_worker
from arq.connections import RedisSettings
from arq.cron import CronJob, cron
from arq.typing import SecondsTimedelta, StartupShutdown, WorkerCoroutine
from arq.worker import Function

import app.arq_client as arq_client
import app.redis_client as redis_client
from app.config import settings
from app.database import SessionFactory, db_manager
from app.fcm.fcm_service import task_send_notifications
from app.firebase_config import init_firebase
from app.flows.flow_feed import task_score_flows_for_feed
from app.flows.question_service import (
    task_generate_flow_cover_image,
    task_generate_transcriptions,
)
from app.flows.question_utils import (
    task_analyze_question_quantitativeness,
    task_categorize_major_tags,
    task_categorize_minor_tags,
    task_compute_question_embeddings,
    task_consolidate_flow_tags,
    task_generate_and_consolidate_tags,
    task_generate_question_answers,
    task_recompute_question_embeddings,
)
from app.flows.tasks import task_mark_question_timed_out
from app.instrumentation import instrument_worker
from app.logging_config import get_logging_config
from app.mail import task_send_email

logger = logging.getLogger(__name__)


async def ping(ctx: dict[Any, Any]) -> Literal["pong"]:
    return "pong"


def make_worker_settings(
    *,
    database_url: str = settings.database_url,
    redis_url: str,
    burst_mode: bool,
    inside_app: bool,
    session_factory: SessionFactory | None,
) -> type:
    """
    Create a worker settings object.

    Args:
        redis_url (str): The URL of the Redis server.
        database_url (str): The URL of the database.
        burst_mode (bool): Whether to run in burst mode.
        inside_app (bool): Whether the worker is running inside the app. If True, worker will not configure it's own logging or instrumentation.
        session_factory (SessionFactory | None): The session factory.

    Returns:
        type: The worker settings object.
    """

    async def startup(ctx: dict[str, Any]):
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

        if not inside_app:
            instrument_worker()
            logging.config.dictConfig(get_logging_config())
            init_firebase()

        db_manager.init(db_url=database_url)
        redis_client.init(redis_url)
        await arq_client.init(redis_url)

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
            task_recompute_question_embeddings,
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
        # Performance optimizations
        max_concurrent_jobs: int = 20  # Increase from default 10
        job_timeout: int = 600  # 10 minutes timeout (increase from 5 min default)
        max_tries: int = 3  # Reduce retries from default 5 to prevent queue clogging
        # Additional optimizations
        poll_delay: float = 0.5  # Check for jobs more frequently (default 1s)
        queue_read_limit: int = 100  # Read more jobs from queue at once (default 10)
        cron_jobs: Sequence[CronJob] | None = [
            cron(
                task_score_flows_for_feed,
                minute={10, 30, 50},
                name="score_flows_for_feed",
            )
        ]

        health_check_interval: SecondsTimedelta = 30
        ctx: dict[str, Any] = {"session_factory": session_factory}
        job_timeout: SecondsTimedelta = 900

    return WorkerSettings


if __name__ == "__main__":
    settings = make_worker_settings(
        redis_url=settings.redis_url,
        burst_mode=False,
        inside_app=False,
        session_factory=None,
    )
    run_worker(settings)
