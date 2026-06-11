import logging
from urllib.parse import parse_qs

from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

from pico_backend.auth import (
    AsyncJWTBearer,
    ExpiredTokenError,
    InvalidTokenError,
    UserNotFoundError,
)

User = get_user_model()

logger = logging.getLogger(__name__)


def get_token_from_scope(scope):
    if header_token := next(
        (
            header_value.split()[1]
            for header_name, header_value in scope["headers"]
            if header_name == "Authorization"
        ),
        None,
    ):
        return header_token

    # If not found in headers, check query parameters
    query_string = scope["query_string"].decode("utf-8")
    parsed_qs = parse_qs(query_string)

    return parsed_qs.get("token", [None])[0]


class JWTAuthenticationMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        if token_value := get_token_from_scope(scope):
            jwt_auth = AsyncJWTBearer()
            try:
                scope["user"] = await jwt_auth.authenticate(scope, token_value)
            except (InvalidTokenError, ExpiredTokenError):
                logger.warning(
                    "Invalid or expired token inside JWT websocket authentication middleware"
                )
                scope["user"] = AnonymousUser()
                scope["error_code"] = 4011

            except UserNotFoundError:
                logger.warning(
                    "Could not find user corresponding to the token inside JWT websocket authentication middleware"
                )
                scope["user"] = AnonymousUser()
                scope["error_code"] = 4020
        else:
            logger.warning(
                "Could not find token in URL query string or in Authorization headers, inside JWT websocket authentication middleware"
            )
            scope["user"] = AnonymousUser()
            scope["error_code"] = 4010

        logger.debug(
            f"User inside JWT websocket authentication middleware: {scope['user']}"
        )

        return await super().__call__(scope, receive, send)
