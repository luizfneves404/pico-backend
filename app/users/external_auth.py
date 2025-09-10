import contextlib
import json
import logging
import time
from typing import Any, TypedDict

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from jwt.algorithms import RSAAlgorithm
from pydantic import BaseModel

from app.config import settings
from app.users.exceptions import (
    InvalidTokenError,
)

logger = logging.getLogger(__name__)

APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
APPLE_ISSUER = "https://appleid.apple.com"
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"


# In-memory cache for JWKs
class GoogleJWKsCache(TypedDict):
    keys: dict[str, Any] | None
    expires_at: float


_google_jwks_cache: GoogleJWKsCache = {"keys": None, "expires_at": 0}


class GoogleIdToken(BaseModel):
    sub: str
    email: str
    email_verified: bool
    name: str | None = None
    picture: str | None = None


class AppleIdToken(BaseModel):
    sub: str
    email: str
    email_verified: bool = False


async def _get_jwks() -> dict[str, Any]:
    """
    Fetches and caches Google's JWKS (JSON Web Key Set).
    Uses the HTTP Cache-Control header to determine expiration.
    """
    now = time.time()
    if _google_jwks_cache["keys"] and now < _google_jwks_cache["expires_at"]:
        return _google_jwks_cache["keys"]

    async with httpx.AsyncClient() as client:
        response = await client.get(GOOGLE_JWKS_URL)
        response.raise_for_status()
        jwks = response.json()

        # Determine cache expiration from headers
        cache_control = response.headers.get("Cache-Control", "")
        max_age = 0
        for part in cache_control.split(","):
            part_stripped = part.strip()
            if part_stripped.startswith("max-age="):
                with contextlib.suppress(ValueError):
                    max_age = int(part_stripped.split("=")[1])
        _google_jwks_cache["keys"] = jwks
        _google_jwks_cache["expires_at"] = now + max_age
        return jwks


async def verify_google_id_token(id_token: str) -> GoogleIdToken:
    """
    Verify Google ID token and extract user information asynchronously.

    Args:
        id_token: The Google ID token (JWT) to verify.

    Returns:
        GoogleIdToken: Parsed user information.

    Raises:
        InvalidTokenError: If the token is invalid or verification fails.
    """
    try:
        jwks = await _get_jwks()

        header = jwt.get_unverified_header(id_token)
        kid = header.get("kid")
        if not kid:
            raise InvalidTokenError("No 'kid' found in token header")

        key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
        if not key_data:
            raise InvalidTokenError("Unable to find matching JWK for token")

        public_key = RSAAlgorithm.from_jwk(json.dumps(key_data))

        if not isinstance(public_key, RSAPublicKey):
            raise InvalidTokenError("Unable to find matching public key")

        decoded = jwt.decode(
            id_token,
            public_key,
            algorithms=["RS256"],
            audience=settings.google_client_id,
            issuer=["https://accounts.google.com", "accounts.google.com"],
        )

    except (jwt.InvalidTokenError, httpx.HTTPError) as e:
        raise InvalidTokenError(f"Invalid Google ID token: {e}") from e

    sub = decoded.get("sub")
    email = decoded.get("email")
    email_verified = decoded.get("email_verified", False)
    name = decoded.get("name")

    if not sub or not email:
        raise InvalidTokenError("Missing required token claims")

    return GoogleIdToken(sub=sub, email=email, email_verified=email_verified, name=name)


async def verify_apple_id_token(id_token: str) -> AppleIdToken:
    """Verify Apple ID token and extract user information.

    Args:
        id_token: The Apple ID token to verify

    Returns:
        Dictionary containing user information from Apple

    Raises:
        InvalidTokenError: If the token is invalid or verification fails
    """
    # Get Apple's public keys
    async with httpx.AsyncClient() as client:
        jwks_response = await client.get(APPLE_JWKS_URL)
        jwks_response.raise_for_status()
        jwks = jwks_response.json()

    # Decode the token header to get the key ID
    unverified_header = jwt.get_unverified_header(id_token)
    key_id = unverified_header["kid"]

    # Find the matching public key
    correct_key: dict[str, Any] | None = None
    for key in jwks["keys"]:
        if key["kid"] == key_id:
            correct_key = key
            break

    if not correct_key:
        raise InvalidTokenError("Unable to find matching public key")

    rsa_key = RSAAlgorithm.from_jwk(correct_key)

    if not isinstance(rsa_key, RSAPublicKey):
        raise InvalidTokenError("Unable to find matching public key")

    algorithm = correct_key["alg"]

    try:
        decoded_token = jwt.decode(
            id_token,
            rsa_key,
            algorithms=[algorithm],
            audience=settings.apple_app_id,
            issuer=APPLE_ISSUER,
        )
    except jwt.InvalidTokenError as e:
        raise InvalidTokenError("Invalid Apple ID token") from e

    # Try to get email, but provide fallback if missing
    # (for deleted users, Hide My Email, etc.)
    email = decoded_token.get("email")
    email_verified = decoded_token.get("email_verified", False)

    # If no email provided, create a unique placeholder based on Apple ID
    # This handles cases where Apple doesn't provide email
    # (deleted users, phone-only Apple IDs)
    if not email:
        apple_sub = decoded_token["sub"]
        email = f"apple.user.{apple_sub}@privaterelay.appleid.com"
        email_verified = True  # We trust Apple's sub verification

    # Keep original validation but with fallback email
    if not email or not email_verified:
        raise InvalidTokenError("Missing email in Apple ID token")

    return AppleIdToken(
        sub=decoded_token["sub"],
        email=email,
        email_verified=email_verified,
    )
