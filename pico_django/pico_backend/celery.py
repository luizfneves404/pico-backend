import os
from functools import wraps
from typing import Any, Callable

from asgiref.sync import sync_to_async
from celery import Celery, shared_task
from celery.contrib.django.task import DjangoTask
from celery.signals import worker_process_init

from app.config import settings
from app.fcm.fcm_service import init_firebase

if os.environ.get("DJANGO_SETTINGS_MODULE") != settings.django_settings_module:
    print(
        f"Warning: DJANGO_SETTINGS_MODULE is being overridden. "
        f"{os.environ.get('DJANGO_SETTINGS_MODULE')} -> {settings.django_settings_module}"
    )
os.environ["DJANGO_SETTINGS_MODULE"] = settings.django_settings_module
import asyncio
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


@worker_process_init.connect(weak=False)
def init_worker_dependencies(*args: Any, **kwargs: Any) -> None:
    # Initialize Firebase in each worker process
    init_firebase()


class LogErrorsDjangoTask(DjangoTask):
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.exception(
            f"Celery task with task_id {task_id} failed with exception: {exc}. Arguments: {args}. Keyword arguments: {kwargs}.",
            exc_info=einfo,
        )
        super(LogErrorsDjangoTask, self).on_failure(exc, task_id, args, kwargs, einfo)


app = Celery("pico_backend", task_cls=LogErrorsDjangoTask)

app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()


@shared_task(name="celery.ping")
def ping():
    return "pong"


class FakeError(Exception):
    pass


@shared_task
def fake_error():
    raise FakeError("Fake error")


def celery_async_workflow(workflow_func: Callable):
    """
    Decorator that awaits a Celery workflow function using sync_to_async, if CELERY_TASK_ALWAYS_EAGER is set to True,
    or calls the function directly otherwise, because it will be executed in the worker.

    :param workflow_func: The workflow function to be decorated, which should be a synchronous function.
    """

    @wraps(workflow_func)
    async def wrapper(*args, **kwargs):
        if settings.CELERY_TASK_ALWAYS_EAGER:
            # Run the workflow asynchronously and await its completion in async contexts (celery tasks eager)
            await sync_to_async(workflow_func)(*args, **kwargs)
        else:
            # Run the workflow asynchronously in normal operation
            workflow_func(*args, **kwargs)

    return wrapper


def task_to_async(task):
    async def wrapper(*args, **kwargs):
        delay = 0.1
        async_result = await sync_to_async(task.delay)(*args, **kwargs)
        while not async_result.ready():
            await asyncio.sleep(delay)
            delay = min(delay * 1.5, 2)
        return async_result.get()

    return wrapper
