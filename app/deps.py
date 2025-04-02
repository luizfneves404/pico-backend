from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import db_manager
from app.users import jwt_token as token_service
from app.users.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token/pair")


async def get_db_session():
    """
    This function is used to get a database session.
    It will begin a transaction and yield the session.
    The transaction will be committed if the session is used.
    If an exception is raised, the transaction will be rolled back.
    If you wish to keep the session useful after an error, use nested transactions.
    """
    async with db_manager.session_with_transaction() as session:
        yield session


DBSessionAnnotated = Annotated[AsyncSession, Depends(get_db_session)]


class TokenData(BaseModel):
    username: str


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], db_session: DBSessionAnnotated
) -> User:
    try:
        return await token_service.process_token(db_session, token, "access")
    except token_service.TokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


CurrentUserDep = Depends(get_current_user)
CurrentUserAnnotated = Annotated[User, CurrentUserDep]
