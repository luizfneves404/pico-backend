import logging.config
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator, Awaitable, Callable

import uvicorn
from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from sqladmin import Admin

import app.arq_client as arq_client
from app.admin_registry import admin_views, authentication_backend
from app.amp import track_amplitude_endpoint_event
from app.chat.websockets import router as websockets_router
from app.config import settings
from app.database import db_manager
from app.deps import CurrentUserDep
from app.fcm_service import init_firebase
from app.redis_client import use_redis
from app.schools.routers import router as schools_router
from app.users.routers import token_router, user_router

logging.config.fileConfig("logging.ini", disable_existing_loggers=False)
logger = logging.getLogger(__name__)


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
                )

                for view in admin_views:
                    admin.add_view(view)

                yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.allowed_hosts,
)
authenticated_routers = APIRouter(dependencies=[CurrentUserDep])
app.include_router(authenticated_routers)
app.include_router(token_router)
app.include_router(user_router)
app.include_router(websockets_router)
app.include_router(schools_router)


@app.middleware("http")
async def health_check_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
):
    if request.url.path == "/health":
        return Response(content="Healthy")
    return await call_next(request)


@app.middleware("http")
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


@app.middleware("http")
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


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.uvicorn_host,
        port=settings.uvicorn_port,
        reload=settings.uvicorn_reload,
        loop="uvloop",
    )
