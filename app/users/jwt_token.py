import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

import jwt
from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.users import service
from app.users.models import User as UserDB

JWT_ALGORITHM = "HS256"
router = APIRouter(prefix="/token", tags=["token"])

logger = logging.getLogger(__name__)


class TokenError(Exception):
    """Base class for token-related errors"""

    def __init__(self, message: str):
        self.message = message


class ExpiredTokenError(TokenError):
    pass


class InvalidTokenError(TokenError):
    pass


class UserNotFoundError(TokenError):
    pass


def generate_tokens(user: UserDB, auth_provider: str = "local") -> tuple[str, str]:
    """Generate a pair of access and refresh tokens for a user.

    Args:
        user (UserDB): The user to generate tokens for.
        auth_provider (str): The authentication provider ('local', 'google', 'apple').

    Returns:
        tuple[str, str]: A tuple containing the access, refresh tokens.
    """
    now = datetime.now(timezone.utc)
    common_payload = {
        "user_id": user.id,
        "email": user.email,
        "auth_provider": auth_provider,
        "iat": int(now.timestamp()),
        "jti": str(uuid.uuid4()),
    }

    access_payload = {
        **common_payload,
        "exp": int((now + settings.jwt_access_expiration_delta).timestamp()),
        "token_type": "access",
    }

    refresh_payload = {
        **common_payload,
        "exp": int((now + settings.jwt_refresh_expiration_delta).timestamp()),
        "token_type": "refresh",
    }

    access_token: str = jwt.encode(
        access_payload, settings.secret_key, algorithm=JWT_ALGORITHM
    )
    refresh_token: str = jwt.encode(
        refresh_payload, settings.secret_key, algorithm=JWT_ALGORITHM
    )
    return access_token, refresh_token


async def process_token(
    db_session: AsyncSession,
    token: str,
    expected_type: Literal["access", "refresh", ""] = "",
):
    """Given a token, return a user if it is valid.

    Args:
        db_session (AsyncSession): The database session.
        token (str): The token to process.
        expected_type (Literal["access", "refresh", ""]): The expected type of token. if "" it performs no validation of type.

    Raises:
        InvalidTokenError: The token is invalid.
        ExpiredTokenError: The token has expired.
        InvalidTokenError: The token is invalid.
        UserNotFoundError: The user was not found.

    Returns:
        UserDBModel: The user associated with the token.
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[JWT_ALGORITHM])
        if expected_type and payload.get("token_type") != expected_type:
            raise InvalidTokenError(
                f"Token type {payload.get('token_type')} is not {expected_type}"
            )
        user = await service.get_user(db_session, id=payload.get("user_id"))
        if not user:
            raise UserNotFoundError("User not found")
        return user
    except jwt.ExpiredSignatureError:
        logger.info(f"Expired {expected_type} token")
        raise ExpiredTokenError(f"{expected_type.capitalize()} token expired")
    except jwt.InvalidTokenError:
        logger.info(f"Invalid {expected_type} token")
        raise InvalidTokenError(f"Invalid {expected_type} token")
