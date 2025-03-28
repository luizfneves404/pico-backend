from typing import Annotated

from database import get_db_session
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from users import jwt_token as token_service
from users.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token/pair")

DBSessionDep = Annotated[AsyncSession, Depends(get_db_session)]


class TokenData(BaseModel):
    username: str


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], db_session: DBSessionDep
) -> User:
    try:
        return await token_service.process_token(db_session, token, "access")
    except token_service.TokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


CurrentUserDep = Annotated[User, Depends(get_current_user)]
