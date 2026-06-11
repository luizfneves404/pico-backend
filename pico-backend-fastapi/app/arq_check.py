from collections.abc import Sequence

from arq.connections import RedisSettings
from arq.cron import CronJob
from arq.typing import StartupShutdown, WorkerCoroutine
from arq.worker import Function, check_health

from app.config import settings


class CheckSettings:
    redis_settings: RedisSettings = RedisSettings.from_dsn(settings.redis_url)
    functions: Sequence[WorkerCoroutine | Function] = []
    on_startup: StartupShutdown | None = None
    on_shutdown: StartupShutdown | None = None
    cron_jobs: Sequence[CronJob] | None = None


check_health(CheckSettings)
