import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from asgiref.local import Local
from django.db.backends.utils import CursorWrapper
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.decorators import sync_and_async_middleware

import pico_backend.amp as pico_backend_amp

logger = logging.getLogger(__name__)


@sync_and_async_middleware
def health_check_middleware(get_response: Callable[[HttpRequest], HttpResponse]):
    if asyncio.iscoroutinefunction(get_response):

        async def middleware(request: HttpRequest):
            if request.path == "/health":
                return JsonResponse({"status": "Healthy"})
            return await get_response(request)

    else:

        def middleware(request: HttpRequest):
            if request.path == "/health":
                return JsonResponse({"status": "Healthy"})
            return get_response(request)

    return middleware


def should_track_event(request: HttpRequest, response: HttpResponse) -> bool:
    return (
        response.status_code >= 200
        and response.status_code < 300
        and request.path.startswith("/api/")
    )


def handle_error(e: Exception, response_var_exists: bool) -> None:
    logger.error(f"Amplitude middleware error: {e}", exc_info=True)


@sync_and_async_middleware
def analytics_middleware(get_response: Callable[[HttpRequest], HttpResponse]):
    """Middleware that tracks Amplitude events for all registered endpoints."""

    if asyncio.iscoroutinefunction(get_response):

        async def middleware(request: HttpRequest):
            try:
                pico_backend_amp.prepare_request_body(request)
                response = await get_response(request)

                if should_track_event(request, response):
                    pico_backend_amp.track_amplitude_endpoint_event(request, response)

                return response
            except Exception as e:
                handle_error(e, "response" in locals())
                if "response" not in locals():
                    response = await get_response(request)
                return response
    else:

        def middleware(request: HttpRequest) -> HttpResponse:
            try:
                pico_backend_amp.prepare_request_body(request)
                response: HttpResponse = get_response(request)

                if should_track_event(request, response):
                    pico_backend_amp.track_amplitude_endpoint_event(request, response)

                return response
            except Exception as e:
                handle_error(e, "response" in locals())
                if "response" not in locals():
                    response: HttpResponse = get_response(request)
                return response

    return middleware


_local_storage = Local()


@sync_and_async_middleware
def view_time_middleware(get_response: Callable[[HttpRequest], HttpResponse]):
    if asyncio.iscoroutinefunction(get_response):

        async def middleware(request: HttpRequest) -> HttpResponse:
            _local_storage.total_sql_time = 0.0
            _local_storage.num_queries = 0
            start_time: float = time.monotonic()

            response: HttpResponse = await get_response(request)

            duration: float = time.monotonic() - start_time
            total_sql_time: float = _local_storage.total_sql_time
            num_queries = _local_storage.num_queries

            # Build log message
            parts: list[str] = [
                f"{request.method} {request.get_full_path()} {response.status_code}"
            ]
            if hasattr(response, "content"):
                parts.append(str(len(response.content)))
            elif hasattr(response, "streaming_content"):
                parts.append("streaming")
            parts.append(
                f"{duration:.6f}s total, {total_sql_time:.6f}s SQL ({num_queries} queries)"
            )
            logger.info(" ".join(parts))
            return response

    else:

        def middleware(request: HttpRequest) -> HttpResponse:
            _local_storage.total_sql_time = 0.0
            _local_storage.num_queries = 0
            start_time: float = time.monotonic()

            response: HttpResponse = get_response(request)

            duration: float = time.monotonic() - start_time
            total_sql_time: float = _local_storage.total_sql_time
            num_queries: int = _local_storage.num_queries

            # Build log message
            parts: list[str] = [
                f"{request.method} {request.get_full_path()} {response.status_code}"
            ]
            if hasattr(response, "content"):
                parts.append(str(len(response.content)))
            elif hasattr(response, "streaming_content"):
                parts.append("streaming")
            parts.append(
                f"{duration:.6f}s total, {total_sql_time:.6f}s SQL ({num_queries} queries)"
            )
            logger.info(" ".join(parts))
            return response

    return middleware


# Save original methods for later use
_original_execute = CursorWrapper.execute
_original_executemany = CursorWrapper.executemany


def instrumented_execute(self: CursorWrapper, sql: str, params: Any = None) -> None:
    """
    Instrument CursorWrapper.execute to measure and accumulate the SQL execution time.
    """
    if not hasattr(_local_storage, "total_sql_time"):
        _local_storage.total_sql_time = 0.0
    if not hasattr(_local_storage, "num_queries"):
        _local_storage.num_queries = 0

    start: float = time.monotonic()
    try:
        return _original_execute(self, sql, params)
    finally:
        _local_storage.total_sql_time += time.monotonic() - start
        _local_storage.num_queries += 1


def instrumented_executemany(self: CursorWrapper, sql: str, param_list: Any) -> None:
    """
    Instrument CursorWrapper.executemany to measure and accumulate SQL execution time,
    accounting for multiple executions.
    """
    if not hasattr(_local_storage, "total_sql_time"):
        _local_storage.total_sql_time = 0.0
    if not hasattr(_local_storage, "num_queries"):
        _local_storage.num_queries = 0

    start: float = time.monotonic()
    try:
        return _original_executemany(self, sql, param_list)
    finally:
        _local_storage.total_sql_time += time.monotonic() - start
        _local_storage.num_queries += len(param_list)


# Apply the monkey-patch
CursorWrapper.execute = instrumented_execute
CursorWrapper.executemany = instrumented_executemany
