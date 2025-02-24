import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

import jwt
from config import settings
from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession
from users import user_service
from users.models import User as UserDB

router = APIRouter(prefix="/token", tags=["token"])

logger = logging.getLogger(__name__)


class TokenError(Exception):
    """Base class for token-related errors"""

    def __init__(self, message):
        self.message = message


class ExpiredTokenError(TokenError):
    pass


class InvalidTokenError(TokenError):
    pass


class UserNotFoundError(TokenError):
    pass


def generate_tokens(user: UserDB) -> tuple[str, str]:
    """Generate a pair of access and refresh tokens for a user.

    Args:
        user (UserDB): The user to generate tokens for.

    Returns:
        tuple[str, str]: A tuple containing the access, refresh tokens.
    """
    now = datetime.now(timezone.utc)
    common_payload = {
        "user_id": user.id,
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

    access_token = jwt.encode(access_payload, settings.secret_key, algorithm="HS256")
    refresh_token = jwt.encode(refresh_payload, settings.secret_key, algorithm="HS256")
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
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        if expected_type and payload.get("token_type") != expected_type:
            raise InvalidTokenError(f"Invalid {expected_type} token")
        user = await user_service.get_user(db_session, id=payload.get("user_id"))
        if not user:
            raise UserNotFoundError("User not found")
        return user
    except jwt.ExpiredSignatureError:
        logger.info(f"Expired {expected_type} token")
        raise ExpiredTokenError(f"{expected_type.capitalize()} token expired")
    except jwt.InvalidTokenError:
        logger.info(f"Invalid {expected_type} token")
        raise InvalidTokenError(f"Invalid {expected_type} token")
