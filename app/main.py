import logging.config
import os
import sys

sys.path.insert(
    1,
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "pico_django")),
)
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator, Awaitable, Callable

import uvicorn
from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from sqladmin import Admin
from starlette.types import ASGIApp, Receive, Scope, Send

import app.arq_client as arq_client
from app.admin_registry import admin_views, authentication_backend
from app.amp import track_amplitude_endpoint_event
from app.chat.websockets import router as websockets_router
from app.config import settings
from app.database import db_manager
from app.deps import CurrentUserDep
from app.essays.routers import router as essay_topics_router
from app.fcm.fcm_service import init_firebase
from app.files.routers import router as files_router
from app.log_filters import add_log_filters
from app.redis_client import use_redis
from app.schools.routers import router as schools_router
from app.users.routers import token_router, user_router
from pico_django.pico_backend.asgi import application as django_application

logging.config.fileConfig("logging.ini", disable_existing_loggers=False)
logger = logging.getLogger(__name__)

add_log_filters()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_firebase()

    async with db_manager.use_db(settings.database_url):
        async with use_redis():
            async with arq_client.arq_redis():
                admin = Admin(
                    app,
                    db_manager.engine,
                    authentication_backend=authentication_backend,
                    base_url="/" + settings.admin_url,
                )

                for view in admin_views:
                    admin.add_view(view)

                yield


fastapi_app = FastAPI(
    lifespan=lifespan,
    openapi_url=settings.openapi_url,
    docs_url=settings.docs_url,
)

# have to do this weird thing instead of using /api as base_url of FastAPI() because sqladmin hardcoded admin urls without /api
base_api_router = APIRouter(prefix="/api")

authenticated_routers = APIRouter(dependencies=[CurrentUserDep])

# not authenticated (unless some authentication is required inside the router)
base_api_router.include_router(token_router)
base_api_router.include_router(user_router)
base_api_router.include_router(websockets_router)
base_api_router.include_router(schools_router)

# authenticated
authenticated_routers.include_router(essay_topics_router)
authenticated_routers.include_router(files_router)

# including base routers
base_api_router.include_router(authenticated_routers)
fastapi_app.include_router(base_api_router)

# middlewares

fastapi_app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.allowed_hosts,
)


@fastapi_app.middleware("http")
async def analytics_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
):
    response = await call_next(request)
    try:
        if (
            response.status_code >= 200
            and response.status_code < 300
            and request.url.path.startswith("/api/")
        ):
            await track_amplitude_endpoint_event(request, response)
    except Exception as e:
        logger.error(f"Error tracking amplitude event: {e}")
    finally:
        return response


@fastapi_app.middleware("http")
async def logging_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
):
    start_time = time.monotonic()
    logger.info(f"Request started: {request.method} {request.url}")

    response = await call_next(request)

    duration = time.monotonic() - start_time

    logger.info(
        f"{request.method} {request.url} {response.status_code} - {duration:.6f}s total"
    )
    return response


@fastapi_app.middleware("http")
async def health_check_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
):
    if request.url.path == "/health":
        return Response(content="Healthy")
    return await call_next(request)


class HostRouter:
    def __init__(self, host_app_map: dict[str, ASGIApp], default_app: ASGIApp):
        self.host_app_map = host_app_map
        self.default_app = default_app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http" and scope["type"] != "websocket":
            return await self.default_app(scope, receive, send)

        # Extract Host header
        headers = dict((k.decode(), v.decode()) for k, v in scope["headers"])
        host = headers.get("host", "").split(":")[0]

        app = self.host_app_map.get(host, self.default_app)
        return await app(scope, receive, send)


application = HostRouter(
    host_app_map={
        settings.django_host: django_application,
        settings.fastapi_host: fastapi_app,
    },
    default_app=fastapi_app,
)


if __name__ == "__main__":
    uvicorn.run(
        "app.main:application",
        host=settings.uvicorn_host,
        port=settings.uvicorn_port,
        reload=settings.uvicorn_reload,
        loop="uvloop",
    )
