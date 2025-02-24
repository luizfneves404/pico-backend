from functools import lru_cache
from typing import Annotated

from config import Settings, settings
from database import get_db_session
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from users import token as token_service
from users.models import User as User

ALGORITHM = "HS256"


@lru_cache
def get_settings():
    return Settings()


SECRET_KEY = settings.secret_key

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

DBSessionDep = Annotated[AsyncSession, Depends(get_db_session)]

credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid authentication credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


class TokenData(BaseModel):
    username: str


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], db_session: DBSessionDep
) -> User:
    return await token_service.process_token(db_session, token, "access")


CurrentUserDep = Annotated[User, Depends(get_current_user)]
