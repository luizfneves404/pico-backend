import logging.config
from contextlib import asynccontextmanager
from typing import AsyncIterator

from chat.websockets import router as websockets_router
from chatrooms.api import router as chatrooms_router
from config import settings
from database import db_manager
from fastapi import FastAPI
from users.api import token_router, user_router

DEBUG = settings.debug


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    db_manager.init(settings.database_url)
    yield
    await db_manager.close()


app = FastAPI(lifespan=lifespan)

app.include_router(token_router)
app.include_router(user_router)
app.include_router(websockets_router)
app.include_router(chatrooms_router)


logging.config.fileConfig("logging.ini")
