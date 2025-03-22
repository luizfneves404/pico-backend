import logging.config
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from admin_registry import admin_views, authentication_backend
from arq_client import arq_client_manager
from chat.websockets import router as websockets_router
from chatrooms.api import router as chatrooms_router
from config import settings
from database import db_manager
from fastapi import FastAPI, Request
from redis_client import redis_manager
from schools.routers import router as schools_router
from sqladmin import Admin
from users.routers import token_router, user_router

logging.config.fileConfig("logging.ini", disable_existing_loggers=False)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    db_manager.init(settings.database_url)
    redis_manager.init(settings.redis_url)
    await arq_client_manager.init(settings.redis_url)

    admin = Admin(app, db_manager.engine, authentication_backend=authentication_backend)

    for view in admin_views:
        admin.add_view(view)

    yield

    await db_manager.close()
    await redis_manager.close()
    await arq_client_manager.close()


app = FastAPI(lifespan=lifespan)

app.include_router(token_router)
app.include_router(user_router)
app.include_router(websockets_router)
app.include_router(chatrooms_router)
app.include_router(schools_router)


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    start_time = time.monotonic()
    logger.info(f"Request started: {request.method} {request.url}")

    response = await call_next(request)

    duration = time.monotonic() - start_time

    logger.info(
        f"{request.method} {request.url} {response.status_code} - {duration:.6f}s total"
    )
    return response


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.uvicorn_host,
        port=settings.uvicorn_port,
        reload=settings.uvicorn_reload,
        loop="uvloop",
    )
