import logging
import uuid

import jwt
from django.contrib.auth import aauthenticate, get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest
from django.utils import timezone
from ninja import Schema
from ninja.errors import HttpError
from ninja.router import Router
from ninja.security import HttpBearer

from app.config import settings

User = get_user_model()

router = Router()

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


def generate_tokens(user) -> tuple[str, str]:
    now = timezone.now()
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


async def process_token(token: str, expected_type: str = ""):
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        if expected_type and payload.get("token_type") != expected_type:
            raise InvalidTokenError(f"Invalid {expected_type} token")
        user = await User.objects.aget(id=payload.get("user_id"))
        return user
    except jwt.ExpiredSignatureError:
        logger.info(f"Expired {expected_type} token")
        raise ExpiredTokenError(f"{expected_type.capitalize()} token expired")
    except jwt.InvalidTokenError:
        logger.info(f"Invalid {expected_type} token")
        raise InvalidTokenError(f"Invalid {expected_type} token")
    except ObjectDoesNotExist:
        logger.info(f"User not found for {expected_type} token")
        raise UserNotFoundError("User not found")


class AsyncJWTBearer(HttpBearer):
    async def __call__(self, request: HttpRequest):
        token = request.headers.get("Authorization", "").split(" ")[-1]
        if not token:
            return None
        try:
            return await self.authenticate(request, token)
        except TokenError as e:
            raise HttpError(401, e.message)

    async def authenticate(self, request: HttpRequest, token: str):
        try:
            return await process_token(token, "access")
        except TokenError:
            raise


class TokenRequest(Schema):
    username: str
    password: str


class TokenResponse(Schema):
    access: str
    refresh: str


class RefreshRequest(Schema):
    refresh: str


class VerifyRequest(Schema):
    token: str


@router.post("/pair", response=TokenResponse, auth=None, url_name="token_obtain_pair")
async def login(request: HttpRequest, credentials: TokenRequest):
    user = await aauthenticate(
        username=credentials.username.strip(), password=credentials.password
    )
    if user is None:
        raise HttpError(401, "Invalid credentials")
    access, refresh = generate_tokens(user)
    return {"access": access, "refresh": refresh}


@router.post("/refresh", response=TokenResponse, auth=None, url_name="token_refresh")
async def refresh_token(request: HttpRequest, refresh_request: RefreshRequest):
    try:
        user = await process_token(refresh_request.refresh, "refresh")
        access, refresh = generate_tokens(user)
        return {"access": access, "refresh": refresh}
    except TokenError as e:
        raise HttpError(401, e.message)


@router.post("/verify", auth=None, url_name="token_verify")
async def verify_token(request: HttpRequest, verify_request: VerifyRequest):
    try:
        await process_token(verify_request.token)
    except TokenError as e:
        raise HttpError(401, e.message)
