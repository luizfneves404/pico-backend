import re
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from geoalchemy2.functions import ST_AsText
from httpx import AsyncClient
from sqlalchemy import String, cast
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.community.models import Community, CommunityUser
from app.config import settings
from app.education.models import EducationLevel, LevelStage
from app.users import external_auth
from app.users.exceptions import (
    InvalidTokenError,
)
from app.users.external_auth import AppleIdToken, GoogleIdToken
from app.users.models import User
from tests.factories import (
    CountryFactory,
    CourseFactory,
    EducationLevelFactory,
    InstitutionFactory,
    UserFactory,
)


class TestUserCreation:
    """Test user creation via different methods."""

    async def test_create_user_password_auth_full_flow(self, client: AsyncClient):
        """Test complete user creation flow with password auth, JWT generation, and user retrieval."""
        user: User = UserFactory.build()
        response = await client.post(
            "/api/users",
            json={
                "name": user.name,
                "password": "defaultpassword",
                "email": user.email,
                "referred_by_username": "",
                "signup_source": "social",
            },
        )
        assert response.status_code == 201
        response_data = response.json()
        user_id = response_data["id"]

        # Verify response data
        assert response_data["name"] == user.name
        # Username should be normalized: lowercase name with spaces replaced by underscores + 4 digits
        expected_username_pattern = rf"^{user.name.lower().replace(' ', '_')}\d{{4}}$"
        assert re.match(expected_username_pattern, response_data["username"])
        assert response_data["email"] == user.email

        # Test JWT token generation
        token_response = await client.post(
            "/api/token/pair",
            data={
                "username": user.email,
                "password": "defaultpassword",
            },
        )
        assert token_response.status_code == 200

        # Test user retrieval with token
        headers = {"Authorization": f"Bearer {token_response.json()['access_token']}"}
        me_response = await client.get("/api/users/me", headers=headers)
        assert me_response.status_code == 200
        me_data = me_response.json()

        assert me_data["id"] == user_id
        assert me_data["name"] == user.name
        assert me_data["username"] == response_data["username"]
        assert me_data["email"] == user.email

    async def test_create_user_with_whitespace_normalization(self, client: AsyncClient):
        """Test that user creation properly handles whitespace in names."""
        user: User = UserFactory.build()
        response = await client.post(
            "/api/users",
            json={
                "name": f"  {user.name}  ",
                "password": "defaultpassword",
                "email": user.email,
                "referred_by_username": "",
            },
        )
        assert response.status_code == 201

        # Verify login works
        token_response = await client.post(
            "/api/token/pair",
            data={
                "username": user.email,
                "password": "defaultpassword",
            },
        )
        assert token_response.status_code == 200

    async def test_create_user_validation_errors(self, client: AsyncClient, user: User):
        """Test various validation errors during user creation."""
        # Empty name
        response = await client.post(
            "/api/users",
            json={
                "name": "",
                "password": "defaultpassword",
                "email": "test@example.com",
                "referred_by_username": "",
            },
        )
        assert response.status_code == 422

        # Email conflict (case insensitive and whitespace handling)
        user2_data: User = UserFactory.build()
        response = await client.post(
            "/api/users",
            json={
                "name": f"  {user2_data.name.upper()}  ",
                "password": "defaultpassword",
                "email": f"  {user.email.upper()}  ",
                "referred_by_username": "",
            },
        )
        assert response.status_code == 409

    async def test_special_characters_handling(self, client: AsyncClient):
        """Test handling of special characters in user input."""
        user_data = {
            "name": "José María González-Smith",
            "password": "defaultpassword",
            "email": "jose.maria@example.com",
            "referred_by_username": "",
        }

        response = await client.post("/api/users", json=user_data)
        assert response.status_code == 201

        # Username should be normalized
        response_data = response.json()
        assert response_data["name"] == "José María González-Smith"
        # Username normalization should handle special characters
        assert "jose" in response_data["username"].lower()


class TestUserFieldValidation:
    """Test user field validation endpoint."""

    async def test_validate_username_success(self, client: AsyncClient):
        """Test successful username validation."""
        response = await client.post(
            "/api/users/validate",
            json={
                "field_name": "username",
                "field_value": "validusername123",
            },
        )
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["is_valid"] is True
        assert response_data["validated_value"] == "validusername123"

    async def test_validate_username_invalid_characters(self, client: AsyncClient):
        """Test username validation with invalid characters."""
        response = await client.post(
            "/api/users/validate",
            json={
                "field_name": "username",
                "field_value": "invalid-username!",
            },
        )
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["is_valid"] is False
        assert response_data["validated_value"] is None

    async def test_validate_username_with_spaces(self, client: AsyncClient):
        """Test username validation with spaces."""
        response = await client.post(
            "/api/users/validate",
            json={
                "field_name": "username",
                "field_value": "invalid username",
            },
        )
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["is_valid"] is False
        assert response_data["validated_value"] is None

    async def test_validate_username_with_uppercase(self, client: AsyncClient):
        """Test username validation with uppercase letters."""
        response = await client.post(
            "/api/users/validate",
            json={
                "field_name": "username",
                "field_value": "ValidUsername",
            },
        )
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["is_valid"] is False
        assert response_data["validated_value"] is None

    async def test_validate_username_already_exists(
        self, client: AsyncClient, user: User
    ):
        """Test username validation when username already exists."""
        response = await client.post(
            "/api/users/validate",
            json={
                "field_name": "username",
                "field_value": user.username,
            },
        )
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["is_valid"] is False
        assert response_data["validated_value"] == user.username

    async def test_validate_email_success(self, client: AsyncClient):
        """Test successful email validation."""
        response = await client.post(
            "/api/users/validate",
            json={
                "field_name": "email",
                "field_value": "newemail@example.com",
            },
        )
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["is_valid"] is True
        assert response_data["validated_value"] == "newemail@example.com"

    async def test_validate_email_with_uppercase(self, client: AsyncClient):
        """Test email validation with uppercase letters (should be normalized)."""
        response = await client.post(
            "/api/users/validate",
            json={
                "field_name": "email",
                "field_value": "NewEmail@EXAMPLE.COM",
            },
        )
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["is_valid"] is True
        assert response_data["validated_value"] == "newemail@example.com"

    async def test_validate_email_with_whitespace(self, client: AsyncClient):
        """Test email validation with whitespace (should be normalized)."""
        response = await client.post(
            "/api/users/validate",
            json={
                "field_name": "email",
                "field_value": "  spaced@example.com  ",
            },
        )
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["is_valid"] is True
        assert response_data["validated_value"] == "spaced@example.com"

    async def test_validate_email_invalid_format(self, client: AsyncClient):
        """Test email validation with invalid format."""
        response = await client.post(
            "/api/users/validate",
            json={
                "field_name": "email",
                "field_value": "invalid-email",
            },
        )
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["is_valid"] is False
        assert response_data["validated_value"] is None

    async def test_validate_email_already_exists(self, client: AsyncClient, user: User):
        """Test email validation when email already exists."""
        response = await client.post(
            "/api/users/validate",
            json={
                "field_name": "email",
                "field_value": user.email,
            },
        )
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["is_valid"] is False
        assert response_data["validated_value"] == user.email

    async def test_validate_phone_number_success(self, client: AsyncClient):
        """Test successful phone number validation."""
        response = await client.post(
            "/api/users/validate",
            json={
                "field_name": "phone_number",
                "field_value": "+5511999887766",
            },
        )
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["is_valid"] is True
        assert response_data["validated_value"] == "tel:+55-11-99988-7766"

    async def test_validate_phone_number_different_format(self, client: AsyncClient):
        """Test phone number validation with different input format."""
        response = await client.post(
            "/api/users/validate",
            json={
                "field_name": "phone_number",
                "field_value": "5511999887766",
            },
        )
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["is_valid"] is True
        assert response_data["validated_value"] == "tel:+55-11-99988-7766"

    async def test_validate_phone_number_with_spaces_and_dashes(
        self, client: AsyncClient
    ):
        """Test phone number validation with spaces and dashes."""
        response = await client.post(
            "/api/users/validate",
            json={
                "field_name": "phone_number",
                "field_value": "+55 11 9998-8776-6",
            },
        )
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["is_valid"] is True
        assert response_data["validated_value"] == "tel:+55-11-99988-7766"

    async def test_validate_phone_number_invalid_format(self, client: AsyncClient):
        """Test phone number validation with invalid format."""
        response = await client.post(
            "/api/users/validate",
            json={
                "field_name": "phone_number",
                "field_value": "invalid-phone",
            },
        )
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["is_valid"] is False
        assert response_data["validated_value"] is None

    async def test_validate_phone_number_too_short(self, client: AsyncClient):
        """Test phone number validation with too short number."""
        response = await client.post(
            "/api/users/validate",
            json={
                "field_name": "phone_number",
                "field_value": "123",
            },
        )
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["is_valid"] is False
        assert response_data["validated_value"] is None

    async def test_validate_phone_number_already_exists(
        self, client: AsyncClient, user: User
    ):
        """Test phone number validation when phone number already exists."""
        response = await client.post(
            "/api/users/validate",
            json={
                "field_name": "phone_number",
                "field_value": str(user.phone_number),
            },
        )
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["is_valid"] is False
        assert response_data["validated_value"] == user.phone_number

    async def test_validate_field_invalid_field_name(self, client: AsyncClient):
        """Test field validation with invalid field name."""
        response = await client.post(
            "/api/users/validate",
            json={
                "field_name": "invalid_field",
                "field_value": "some_value",
            },
        )
        assert response.status_code == 422  # Validation error for invalid field name

    async def test_validate_field_empty_value(self, client: AsyncClient):
        """Test field validation with empty value."""
        response = await client.post(
            "/api/users/validate",
            json={
                "field_name": "username",
                "field_value": "",
            },
        )
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["is_valid"] is False
        assert response_data["validated_value"] is None


class TestSocialAuthentication:
    """Test Google and Apple social authentication."""

    @patch("app.users.external_auth.verify_google_id_token")
    async def test_google_auth_new_user(
        self, mock_verify_google: AsyncMock, client: AsyncClient
    ):
        """Test Google authentication with new user creation."""

        mock_user_info = GoogleIdToken(
            sub="google_123",
            email="newuser@gmail.com",
            email_verified=True,
            name="New User",
            picture="https://example.com/pic.jpg",
        )
        mock_verify_google.return_value = mock_user_info

        response = await client.post(
            "/api/token/social/google",
            json={
                "id_token": "fake_google_token",
                "signup_source": "social",
                "referred_by_username": "",
            },
        )
        assert response.status_code == 200
        response_data = response.json()
        assert "access_token" in response_data
        assert "refresh_token" in response_data

        # Verify JWT token contains correct data
        decoded_token = jwt.decode(
            response_data["access_token"], settings.secret_key, algorithms=["HS256"]
        )
        assert decoded_token["auth_provider"] == "google"
        assert decoded_token["email"] == "newuser@gmail.com"

        mock_verify_google.assert_called_once_with("fake_google_token")

    @patch("app.users.external_auth.verify_google_id_token")
    async def test_google_auth_existing_user_with_google_id(
        self, mock_verify_google: AsyncMock, client: AsyncClient, session: AsyncSession
    ):
        """Test Google authentication with existing user that already has Google ID."""
        from app.users.external_auth import GoogleIdToken

        # Create a user with Google ID
        async with session.begin():
            existing_user = await UserFactory.create(
                session=session,
                email="existing@gmail.com",
                google_id="google_123",
                hashed_password=None,
            )

        mock_user_info = GoogleIdToken(
            sub="google_123",
            email="existing@gmail.com",
            email_verified=True,
            name="Existing User",
            picture="https://example.com/pic.jpg",
        )
        mock_verify_google.return_value = mock_user_info

        response = await client.post(
            "/api/token/social/google",
            json={
                "id_token": "fake_google_token",
                "signup_source": "social",
                "referred_by_username": "",
            },
        )
        assert response.status_code == 200
        response_data = response.json()

        # Verify JWT token
        decoded_token = jwt.decode(
            response_data["access_token"], settings.secret_key, algorithms=["HS256"]
        )
        assert decoded_token["user_id"] == existing_user.id
        assert decoded_token["auth_provider"] == "google"

    @patch("app.users.external_auth.verify_google_id_token")
    async def test_google_auth_account_linking_verified_email(
        self, mock_verify_google: AsyncMock, client: AsyncClient, session: AsyncSession
    ):
        """Test Google auth linking to existing account when email is verified."""
        # Create a user with password but no Google ID
        async with session.begin():
            existing_user = await UserFactory.create(
                session=session,
                email="existing@gmail.com",
                hashed_password="hashed_password",
                google_id=None,
            )

        mock_user_info = GoogleIdToken(
            sub="google_123",
            email="existing@gmail.com",
            email_verified=True,
            name="Existing User",
            picture="https://example.com/pic.jpg",
        )
        mock_verify_google.return_value = mock_user_info

        response = await client.post(
            "/api/token/social/google",
            json={
                "id_token": "fake_google_token",
                "signup_source": "social",
                "referred_by_username": "",
            },
        )
        assert response.status_code == 200
        response_data = response.json()

        # Verify JWT token
        decoded_token = jwt.decode(
            response_data["access_token"], settings.secret_key, algorithms=["HS256"]
        )
        assert decoded_token["user_id"] == existing_user.id
        assert decoded_token["auth_provider"] == "google"

        # Verify Google ID was linked to existing account
        async with session.begin():
            await session.refresh(existing_user)
            assert existing_user.google_id == "google_123"

    @patch("app.users.external_auth.verify_google_id_token")
    async def test_google_auth_account_exists_unverified_email(
        self, mock_verify_google: AsyncMock, client: AsyncClient, session: AsyncSession
    ):
        """Test Google auth when account exists with unverified email."""

        # Create a user with password
        async with session.begin():
            await UserFactory.create(
                session=session,
                email="existing@gmail.com",
                hashed_password="hashed_password",
                google_id=None,
            )

        mock_user_info = GoogleIdToken(
            sub="google_123",
            email="existing@gmail.com",
            email_verified=False,  # Email is NOT verified
            name="Existing User",
            picture="https://example.com/pic.jpg",
        )
        mock_verify_google.return_value = mock_user_info

        response = await client.post(
            "/api/token/social/google",
            json={
                "id_token": "fake_google_token",
                "signup_source": "social",
                "referred_by_username": "",
            },
        )
        assert response.status_code == 409
        assert (
            "Account already exists. Please log in using email and password."
            in response.json()["detail"]
        )

    @patch("app.users.external_auth.verify_google_id_token")
    async def test_google_auth_invalid_token(
        self, mock_verify_google: AsyncMock, client: AsyncClient
    ):
        """Test Google authentication with invalid token."""
        mock_verify_google.side_effect = InvalidTokenError("Invalid token")

        response = await client.post(
            "/api/token/social/google",
            json={
                "id_token": "invalid_token",
                "signup_source": "social",
                "referred_by_username": "",
            },
        )
        assert response.status_code == 401
        assert "Invalid ID token" in response.json()["detail"]

    @patch("app.users.external_auth.verify_apple_id_token")
    async def test_apple_auth_new_user(
        self, mock_verify_apple: AsyncMock, client: AsyncClient
    ):
        """Test Apple authentication with new user creation."""

        mock_user_info = AppleIdToken(
            sub="apple_123",
            email="newuser@icloud.com",
            email_verified=True,
        )
        mock_verify_apple.return_value = mock_user_info

        response = await client.post(
            "/api/token/social/apple",
            json={
                "id_token": "fake_apple_token",
                "signup_source": "social",
                "referred_by_username": "",
                "name": "User Hey",
            },
        )
        assert response.status_code == 200
        response_data = response.json()
        assert "access_token" in response_data
        assert "refresh_token" in response_data

        # Verify JWT token
        decoded_token = jwt.decode(
            response_data["access_token"], settings.secret_key, algorithms=["HS256"]
        )
        assert decoded_token["auth_provider"] == "apple"
        assert decoded_token["email"] == "newuser@icloud.com"

    @patch("app.users.external_auth.verify_apple_id_token")
    async def test_apple_auth_existing_user_with_apple_id(
        self, mock_verify_apple: AsyncMock, client: AsyncClient, session: AsyncSession
    ):
        """Test Apple authentication with existing user that already has Apple ID."""

        # Create a user with Apple ID
        async with session.begin():
            existing_user = await UserFactory.create(
                session=session,
                email="existing@icloud.com",
                apple_id="apple_123",
                hashed_password=None,
            )

        mock_user_info = AppleIdToken(
            sub="apple_123",
            email="existing@icloud.com",
            email_verified=True,
        )
        mock_verify_apple.return_value = mock_user_info

        response = await client.post(
            "/api/token/social/apple",
            json={
                "id_token": "fake_apple_token",
                "signup_source": "social",
                "referred_by_username": "",
                "name": "User Hey",
            },
        )
        assert response.status_code == 200
        response_data = response.json()

        # Verify JWT token
        decoded_token = jwt.decode(
            response_data["access_token"], settings.secret_key, algorithms=["HS256"]
        )
        assert decoded_token["user_id"] == existing_user.id
        assert decoded_token["auth_provider"] == "apple"

    @patch("app.users.external_auth.verify_apple_id_token")
    async def test_apple_auth_account_linking_verified_email(
        self, mock_verify_apple: AsyncMock, client: AsyncClient, session: AsyncSession
    ):
        """Test Apple auth linking to existing account when email is verified."""

        # Create a user with password but no Apple ID
        async with session.begin():
            existing_user = await UserFactory.create(
                session=session,
                email="existing@icloud.com",
                hashed_password="hashed_password",
                apple_id=None,
            )

        mock_user_info = AppleIdToken(
            sub="apple_123",
            email="existing@icloud.com",
            email_verified=True,
        )
        mock_verify_apple.return_value = mock_user_info

        response = await client.post(
            "/api/token/social/apple",
            json={
                "id_token": "fake_apple_token",
                "signup_source": "social",
                "referred_by_username": "",
                "name": "User Hey",
            },
        )
        assert response.status_code == 200
        response_data = response.json()

        # Verify JWT token
        decoded_token = jwt.decode(
            response_data["access_token"], settings.secret_key, algorithms=["HS256"]
        )
        assert decoded_token["user_id"] == existing_user.id
        assert decoded_token["auth_provider"] == "apple"

        # NOTE: The current implementation only updates the email field (redundantly)
        # but doesn't link the Apple ID. This might be a bug in the implementation.
        # The email remains the same since it was already matching
        async with session.begin():
            await session.refresh(existing_user)
            assert existing_user.email == "existing@icloud.com"
            assert existing_user.apple_id == "apple_123"

    @patch("app.users.external_auth.verify_apple_id_token")
    async def test_apple_auth_account_exists_unverified_email(
        self, mock_verify_apple: AsyncMock, client: AsyncClient, session: AsyncSession
    ):
        """Test Apple auth when account exists with unverified email."""

        # Create a user with password
        async with session.begin():
            await UserFactory.create(
                session=session,
                email="existing@icloud.com",
                hashed_password="hashed_password",
                apple_id=None,
            )

        mock_user_info = AppleIdToken(
            sub="apple_123",
            email="existing@icloud.com",
            email_verified=False,  # Email is NOT verified
        )
        mock_verify_apple.return_value = mock_user_info

        response = await client.post(
            "/api/token/social/apple",
            json={
                "id_token": "fake_apple_token",
                "signup_source": "social",
                "referred_by_username": "",
                "name": "User Hey",
            },
        )
        assert response.status_code == 409
        assert (
            "Account already exists. Please log in using email and password."
            in response.json()["detail"]
        )

    @patch("app.users.external_auth.verify_apple_id_token")
    async def test_apple_auth_empty_email(
        self, mock_verify_apple: AsyncMock, client: AsyncClient
    ):
        """Test Apple authentication when empty email is provided."""

        mock_user_info = AppleIdToken(
            sub="apple_123",
            email="",  # Empty email
            email_verified=False,
        )
        mock_verify_apple.return_value = mock_user_info

        response = await client.post(
            "/api/token/social/apple",
            json={
                "id_token": "fake_apple_token",
                "signup_source": "social",
                "referred_by_username": "",
                "name": "User Hey",
            },
        )
        assert response.status_code == 200
        response_data = response.json()

        # User should be created even with empty email
        decoded_token = jwt.decode(
            response_data["access_token"], settings.secret_key, algorithms=["HS256"]
        )
        assert decoded_token["auth_provider"] == "apple"

    @patch("app.users.external_auth._get_jwks")
    async def test_google_token_verification_with_external_call(
        self, mock_get_jwks: AsyncMock
    ):
        """Test actual Google token verification logic (mocked external call)."""
        # Mock the JWKS response
        mock_get_jwks.return_value = {
            "keys": [
                {
                    "kid": "test_kid",
                    "n": "test_n",
                    "e": "AQAB",
                    "kty": "RSA",
                    "use": "sig",
                    "alg": "RS256",
                }
            ]
        }

        # Mock JWT operations
        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

        mock_public_key = Mock(spec=RSAPublicKey)

        with patch(
            "app.users.external_auth.jwt.get_unverified_header"
        ) as mock_get_header:
            with patch(
                "app.users.external_auth.RSAAlgorithm.from_jwk"
            ) as mock_from_jwk:
                with patch("app.users.external_auth.jwt.decode") as mock_jwt_decode:
                    mock_get_header.return_value = {"kid": "test_kid"}
                    mock_from_jwk.return_value = mock_public_key
                    mock_jwt_decode.return_value = {
                        "sub": "google_123",
                        "email": "test@gmail.com",
                        "email_verified": True,
                        "name": "Test User",
                    }

                    result = await external_auth.verify_google_id_token("fake_token")

                    assert result.sub == "google_123"
                    assert result.email == "test@gmail.com"
                    assert result.name == "Test User"
                    mock_jwt_decode.assert_called_once()

    @patch("app.users.external_auth.httpx.AsyncClient")
    async def test_apple_token_verification_with_external_call(
        self, mock_httpx_client: MagicMock
    ):
        """Test actual Apple token verification logic (mocked external call)."""
        # Mock the JWKS response
        jwks_data = {
            "keys": [
                {
                    "kid": "test_kid",
                    "n": "test_n",
                    "e": "AQAB",
                    "kty": "RSA",
                    "use": "sig",
                    "alg": "RS256",
                }
            ]
        }

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json = Mock(return_value=jwks_data)

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_httpx_client.return_value.__aenter__.return_value = mock_client_instance
        mock_httpx_client.return_value.__aexit__.return_value = None

        mock_public_key = Mock(spec=RSAPublicKey)

        with patch(
            "app.users.external_auth.jwt.get_unverified_header"
        ) as mock_get_header:
            with patch(
                "app.users.external_auth.RSAAlgorithm.from_jwk"
            ) as mock_from_jwk:
                with patch("app.users.external_auth.jwt.decode") as mock_jwt_decode:
                    mock_get_header.return_value = {"kid": "test_kid"}
                    mock_from_jwk.return_value = mock_public_key
                    mock_jwt_decode.return_value = {
                        "sub": "apple_123",
                        "email": "test@icloud.com",
                        "email_verified": True,
                    }

                    result = await external_auth.verify_apple_id_token("fake_token")

                    assert result.sub == "apple_123"
                    assert result.email == "test@icloud.com"
                    mock_jwt_decode.assert_called_once()

    async def test_malformed_token_handling(self, client: AsyncClient):
        """Test handling of malformed authentication tokens via endpoints."""
        # Test with invalid JWT
        headers = {"Authorization": "Bearer invalid_jwt_token"}
        response = await client.get("/api/users/me", headers=headers)
        assert response.status_code == 401

        # Test with missing Bearer prefix
        headers = {"Authorization": "invalid_jwt_token"}
        response = await client.get("/api/users/me", headers=headers)
        assert response.status_code == 401

        # Test with no authorization header
        response = await client.get("/api/users/me")
        assert response.status_code == 401


class TestUserRetrieval:
    """Test user retrieval operations."""

    async def test_retrieve_current_user(self, user_client: AsyncClient, user: User):
        """Test retrieving current user information."""
        response = await user_client.get("/api/users/me")
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["id"] == user.id
        assert response_data["name"] == user.name
        assert response_data["username"] == user.username
        assert response_data["phone_number"] == user.phone_number
        assert response_data["email"] == user.email
        assert response_data["xp_score"] == 0
        assert response_data["social_score"] == 0

    async def test_retrieve_other_user(
        self, user_client: AsyncClient, user: User, session: AsyncSession
    ):
        """Test retrieving other user's public information."""
        async with session.begin():
            user2: User = await UserFactory.create(session=session)

        response = await user_client.get(f"/api/users/other/{user2.id}")
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["id"] == user2.id
        assert response_data["name"] == user2.name
        assert response_data["username"] == user2.username
        assert response_data["phone_number"] == user2.phone_number
        assert response_data["email"] == user2.email
        assert response_data["xp_score"] == 0
        assert response_data["social_score"] == 0

    async def test_retrieve_sentinel_users(
        self, session: AsyncSession, user_client: AsyncClient
    ):
        """Test retrieving system users."""
        response = await user_client.get("/api/users/sentinel")
        assert response.status_code == 200
        response_data = response.json()
        response_ids = [user["id"] for user in response_data]
        response_usernames = [user["username"] for user in response_data]

        assert len(response_ids) == 1
        async with session.begin():
            deleted_user = (
                await session.execute(select(User).where(User.username == "deleted"))
            ).scalar_one()

        assert deleted_user.id in response_ids
        assert deleted_user.username in response_usernames


class TestUserUpdates:
    """Test user update operations."""

    async def test_update_basic_fields(self, user_client: AsyncClient, user: User):
        """Test updating basic user fields that don't require password."""
        # Note: Currently all updates seem to require password, but testing the pattern
        data = {"updates": {"name": "new name"}, "current_password": "defaultpassword"}
        response = await user_client.patch("/api/users/me", json=data)
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["user"]["name"] == "new name"
        assert "name" in response_data["updated_fields"]

    async def test_update_sensitive_fields(self, user_client: AsyncClient, user: User):
        """Test updating sensitive fields that require password verification."""
        # Username update
        data = {
            "updates": {"username": "newname"},
            "current_password": "defaultpassword",
        }
        response = await user_client.patch("/api/users/me", json=data)
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["user"]["username"] == "newname"
        assert "username" in response_data["updated_fields"]

        # Password update
        data = {
            "updates": {"password": "newpassword605"},
            "current_password": "defaultpassword",
        }
        response = await user_client.patch("/api/users/me", json=data)
        assert response.status_code == 200
        response_data = response.json()
        assert "password" in response_data["updated_fields"]

        # Verify new password works
        token_response = await user_client.post(
            "/api/token/pair",
            data={
                "username": user.email,
                "password": "newpassword605",
            },
        )
        assert token_response.status_code == 200

        # Phone number update
        data = {
            "updates": {"phone_number": "21999202390"},
            "current_password": "newpassword605",
        }
        response = await user_client.patch("/api/users/me", json=data)
        assert response.status_code == 200
        response_data = response.json()
        assert "phone_number" in response_data["updated_fields"]
        assert response_data["user"]["phone_number"] == "tel:+55-21-99920-2390"

        # Email update
        data = {
            "updates": {"email": "test@example.com"},
            "current_password": "newpassword605",
        }
        response = await user_client.patch("/api/users/me", json=data)
        assert response.status_code == 200
        response_data = response.json()
        assert "email" in response_data["updated_fields"]
        assert response_data["user"]["email"] == "test@example.com"

    async def test_update_conflicts_and_validation(
        self, user_client: AsyncClient, session: AsyncSession
    ):
        """Test validation errors and conflicts during updates."""
        async with session.begin():
            existing_user = await UserFactory.create(session=session)

        # Username already exists
        data = {
            "updates": {"username": existing_user.username},
            "current_password": "defaultpassword",
        }
        response = await user_client.patch("/api/users/me", json=data)
        assert response.status_code == 409

        # Username conflict with case insensitive and whitespace
        data = {
            "updates": {"username": f"  {existing_user.username.upper()}  "},
            "current_password": "defaultpassword",
        }
        response = await user_client.patch("/api/users/me", json=data)
        assert response.status_code == 422

        # Email already exists
        data = {
            "updates": {"email": f"  {existing_user.email.upper()}  "},
            "current_password": "defaultpassword",
        }
        response = await user_client.patch("/api/users/me", json=data)
        assert response.status_code == 409

        # Invalid phone number
        data = {
            "updates": {"phone_number": "invalid"},
            "current_password": "defaultpassword",
        }
        response = await user_client.patch("/api/users/me", json=data)
        assert response.status_code == 422

        # Invalid email
        data = {
            "updates": {"email": "invalid"},
            "current_password": "defaultpassword",
        }
        response = await user_client.patch("/api/users/me", json=data)
        assert response.status_code == 422

    async def test_update_education(
        self,
        user_client: AsyncClient,
        session: AsyncSession,
        education_level: EducationLevel,
        level_stage: LevelStage,
    ):
        """Test updating education information."""
        async with session.begin():
            institution = await InstitutionFactory.create(session=session)
            course = await CourseFactory.create(session=session)

        # Update current education
        data = {
            "updates": {
                "current_education": {
                    "level_id": education_level.id,
                    "stage_id": level_stage.id,
                    "institution_id": institution.id,
                    "course_id": course.id,
                }
            }
        }
        response = await user_client.patch("/api/users/me", json=data)
        assert response.status_code == 200
        response_data = response.json()
        assert "current_education" in response_data["updated_fields"]
        assert (
            response_data["user"]["current_education"]["level_id"] == education_level.id
        )
        assert response_data["user"]["current_education"]["stage_id"] == level_stage.id
        assert (
            response_data["user"]["current_education"]["institution_id"]
            == institution.id
        )
        assert response_data["user"]["current_education"]["course_id"] == course.id

        # Update intended education
        data = {
            "updates": {
                "intended_education": {
                    "level_id": education_level.id,
                    "stage_id": level_stage.id,
                    "institution_id": institution.id,
                    "course_id": course.id,
                }
            }
        }
        response = await user_client.patch("/api/users/me", json=data)
        assert response.status_code == 200
        response_data = response.json()
        assert "intended_education" in response_data["updated_fields"]
        assert (
            response_data["user"]["intended_education"]["level_id"]
            == education_level.id
        )
        assert response_data["user"]["intended_education"]["stage_id"] == level_stage.id
        assert (
            response_data["user"]["intended_education"]["institution_id"]
            == institution.id
        )
        assert response_data["user"]["intended_education"]["course_id"] == course.id

    async def test_unified_update_operations(self, user_client: AsyncClient):
        """Test the unified update endpoint with various scenarios."""
        # Multiple fields update
        data = {
            "updates": {"username": "newusername", "email": "new@example.com"},
            "current_password": "defaultpassword",
        }
        response = await user_client.patch("/api/users/me", json=data)
        assert response.status_code == 200
        response_data = response.json()
        assert "username" in response_data["updated_fields"]
        assert "email" in response_data["updated_fields"]
        assert response_data["user"]["username"] == "newusername"
        assert response_data["user"]["email"] == "new@example.com"

        # Sensitive field without password
        data = {"updates": {"username": "anothername"}}
        response = await user_client.patch("/api/users/me", json=data)
        assert response.status_code == 400
        assert "password is required" in response.json()["detail"].lower()

        # No changes
        data: dict[str, Any] = {"updates": {}}
        response = await user_client.patch("/api/users/me", json=data)
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["updated_fields"] == []

        # Wrong password
        data = {
            "updates": {"username": "wrongpass"},
            "current_password": "wrongpassword",
        }
        response = await user_client.patch("/api/users/me", json=data)
        assert response.status_code == 401

    async def test_update_location(
        self, user_client: AsyncClient, user: User, session: AsyncSession
    ):
        """Test updating user location."""
        data = {
            "updates": {
                "location": {"latitude": 12.34567890, "longitude": 12.34567890}
            },
        }
        response = await user_client.patch("/api/users/me", json=data)
        assert response.status_code == 200
        response_data = response.json()
        assert "location" in response_data["updated_fields"]
        # check if actually updated in the database
        async with session.begin():
            location_wkt = (
                await session.execute(
                    select(cast(ST_AsText(User.location), String)).where(
                        User.id == user.id
                    )
                )
            ).scalar_one()
            assert location_wkt == "POINT(12.3456789 12.3456789)"


class TestUserDeletion:
    """Test user deletion operations."""

    async def test_delete_user_success(self, user_client: AsyncClient):
        """Test successful user deletion with correct password."""
        data = {"current_password": "defaultpassword"}
        response = await user_client.request(
            "DELETE",
            "/api/users/me",
            json=data,
        )
        assert response.status_code == 204

        # Verify user is deleted
        response = await user_client.get("/api/users/me")
        assert response.status_code == 401

    async def test_delete_user_wrong_password(self, user_client: AsyncClient):
        """Test user deletion with incorrect password."""
        data = {"current_password": "wrongpassword"}
        response = await user_client.request(
            "DELETE",
            "/api/users/me",
            json=data,
        )
        assert response.status_code == 401

        # Verify user still exists
        response = await user_client.get("/api/users/me")
        assert response.status_code == 200


class TestSocialFeatures:
    """Test social features like contact checking and username search."""

    async def test_check_contacts_with_pagination(
        self,
        user_client: AsyncClient,
        session: AsyncSession,
    ):
        """Test contact checking functionality with pagination."""
        async with session.begin():
            users = await UserFactory.create_batch(7, session=session)
            # Create users that shouldn't match the search
            search_users: list[User] = []
            for i in range(1, 8):
                user = await UserFactory.create(
                    username=f"searchuser{i}", session=session
                )
                search_users.append(user)

        # Test first page
        url = "/api/users/check-contacts?page=1&size=4"
        phone_numbers = [str(user.phone_number) for user in users] + ["+551123111111"]
        data = {"phone_numbers": phone_numbers}
        response = await user_client.post(url, json=data)
        assert response.status_code == 200
        results = response.json()["items"]
        response_ids = [user["id"] for user in results]
        assert len(response_ids) == 4
        assert response.json()["page"] == 1
        assert response.json()["size"] == 4

        # Test second page
        new_url = "/api/users/check-contacts?page=2&size=4"
        new_response = await user_client.post(new_url, json=data)
        assert new_response.status_code == 200
        new_results = new_response.json()["items"]
        new_response_ids = [user["id"] for user in new_results]
        assert len(new_response_ids) == 3
        assert new_response.json()["page"] == 2
        assert new_response.json()["size"] == 4

        # Verify all created users are found
        response_ids.extend(new_response_ids)
        for user in users:
            assert user.id in response_ids

        # Verify search users are not included
        for search_user in search_users:
            assert search_user.id not in response_ids

        # Verify phone numbers are correct
        response_phone_numbers = [
            user["phone_number"] for user in results + new_results
        ]
        for user in users:
            assert user.phone_number in response_phone_numbers
        assert "tel:+55-11-2311-1111" not in response_phone_numbers

    async def test_search_username_with_pagination(
        self, user_client: AsyncClient, session: AsyncSession
    ):
        """Test username search functionality with pagination."""
        async with session.begin():
            users = await UserFactory.create_batch(7, session=session)
            search_users: list[User] = []
            for i in range(1, 8):
                user = await UserFactory.create(
                    username=f"searchuser{i}", session=session
                )
                search_users.append(user)

        # Test first page
        url = "/api/users/search-username?username=searchuser&page=1&size=4"
        response = await user_client.get(url)
        assert response.status_code == 200
        results = response.json()["items"]
        response_ids = [user["id"] for user in results]
        assert len(response_ids) == 4
        assert response.json()["page"] == 1
        assert response.json()["size"] == 4

        # Test second page
        new_url = "/api/users/search-username?username=searchuser&page=2&size=4"
        new_response = await user_client.get(new_url)
        assert new_response.status_code == 200
        new_results = new_response.json()["items"]
        new_response_ids = [user["id"] for user in new_results]
        assert len(new_response_ids) == 3
        assert new_response.json()["page"] == 2
        assert new_response.json()["size"] == 4

        # Verify all search users are found
        response_ids.extend(new_response_ids)
        for search_user in search_users:
            assert search_user.id in response_ids

        # Verify regular users are not included
        for user in users:
            assert user.id not in response_ids

        # Verify current authenticated user is not included in results
        current_user = await user_client.get("/api/users/me")
        current_user_data = current_user.json()
        assert current_user_data["id"] not in response_ids

    async def test_large_batch_operations(
        self, user_client: AsyncClient, session: AsyncSession
    ):
        """Test operations with large amounts of data via endpoints."""
        # Create many users for contact checking
        async with session.begin():
            country = await CountryFactory.create(session=session)
            users = await UserFactory.create_batch(50, session=session, country=country)

        phone_numbers = [str(user.phone_number) for user in users[:30]]
        data = {"phone_numbers": phone_numbers}

        response = await user_client.post(
            "/api/users/check-contacts?page=1&size=20", json=data
        )
        assert response.status_code == 200
        assert len(response.json()["items"]) == 20

    async def test_user_auto_joins_communities_on_education_change(
        self,
        user: User,
        user_client: AsyncClient,
        session: AsyncSession,
        education_level: EducationLevel,
        level_stage: LevelStage,
    ) -> None:
        """Test that users automatically join communities based on their education when changed."""
        # Create education resources first
        async with session.begin():
            institution = await InstitutionFactory.create(session=session)
            course = await CourseFactory.create(session=session)

        async with session.begin():
            response = await user_client.patch(
                "/api/users/me",
                json={
                    "updates": {
                        "current_education": {
                            "level_id": education_level.id,
                            "stage_id": level_stage.id,
                            "institution_id": institution.id,
                            "course_id": course.id,
                        }
                    },
                },
            )
            assert response.status_code == 200
            assert response.json()["updated_fields"] == ["current_education"]
            assert (
                response.json()["user"]["current_education"]["level_id"]
                == education_level.id
            )
            assert (
                response.json()["user"]["current_education"]["stage_id"]
                == level_stage.id
            )
            assert (
                response.json()["user"]["current_education"]["institution_id"]
                == institution.id
            )

        # Verify community was created and user joined it
        async with session.begin():
            result = await session.execute(
                select(Community).where(
                    Community.name == institution.name,
                    Community.subtitle == course.name_i18n["en"],
                )
            )
            community = result.scalar_one_or_none()
            assert community is not None

            # Verify user is in the community
            result = await session.execute(
                select(CommunityUser).where(
                    CommunityUser.user_id == user.id,
                    CommunityUser.community_id == community.id,
                )
            )
            community_user = result.scalar_one_or_none()
            assert community_user is not None


class TestUserRankingAPI:
    """Test general user ranking API endpoints."""

    async def test_get_user_ranking_xp_score_basic(
        self, user_client: AsyncClient, user: User, session: AsyncSession
    ):
        """Test getting user ranking with XP scores."""
        async with session.begin():
            # Create users with different XP scores
            user_high = await UserFactory.create(
                session=session, xp_score=1000, username="highxp"
            )
            user_mid = await UserFactory.create(
                session=session, xp_score=500, username="midxp"
            )
            user_low = await UserFactory.create(
                session=session, xp_score=100, username="lowxp"
            )

        response = await user_client.get("/api/users/ranking?score_type=xp")
        assert response.status_code == 200

        ranking = response.json()
        assert len(ranking) == 4

        # Verify ranking order (highest to lowest)
        assert ranking[0]["id"] == user_high.id
        assert ranking[0]["score"] == 1000
        assert ranking[0]["rank"] == 1
        assert ranking[0]["username"] == "highxp"

        assert ranking[1]["id"] == user_mid.id
        assert ranking[1]["score"] == 500
        assert ranking[1]["rank"] == 2

        assert ranking[2]["id"] == user_low.id
        assert ranking[2]["score"] == 100
        assert ranking[2]["rank"] == 3

        # Original user should be last with 0 score
        assert ranking[3]["id"] == user.id
        assert ranking[3]["score"] == 0
        assert ranking[3]["rank"] == 4

    async def test_get_user_ranking_social_score_basic(
        self, user_client: AsyncClient, user: User, session: AsyncSession
    ):
        """Test getting user ranking with social scores."""
        async with session.begin():
            # Create users with different social scores
            user_social_high = await UserFactory.create(
                session=session, social_score=800, username="highsocial"
            )
            user_social_mid = await UserFactory.create(
                session=session, social_score=400, username="midsocial"
            )

        response = await user_client.get("/api/users/ranking?score_type=social")
        assert response.status_code == 200

        ranking = response.json()
        assert len(ranking) == 3

        # Verify ranking order for social scores
        assert ranking[0]["id"] == user_social_high.id
        assert ranking[0]["score"] == 800
        assert ranking[0]["rank"] == 1

        assert ranking[1]["id"] == user_social_mid.id
        assert ranking[1]["score"] == 400
        assert ranking[1]["rank"] == 2

        assert ranking[2]["id"] == user.id
        assert ranking[2]["score"] == 0
        assert ranking[2]["rank"] == 3

    async def test_get_user_ranking_filter_by_institution(
        self,
        user_client: AsyncClient,
        user: User,
        session: AsyncSession,
        education_level: EducationLevel,
    ):
        """Test filtering ranking by institution."""
        async with session.begin():
            institution1 = await InstitutionFactory.create(
                session=session, name="University A"
            )
            institution2 = await InstitutionFactory.create(
                session=session, name="University B"
            )

            user_inst1 = await UserFactory.create(
                session=session,
                xp_score=800,
                username="inst1user",
            )
            assert user_inst1.current_education is not None

            user_inst1.current_education.institution = institution1
            user_inst2 = await UserFactory.create(
                session=session,
                xp_score=900,
                username="inst2user",
            )
            assert user_inst2.current_education is not None
            user_inst2.current_education.institution = institution2

            assert user.current_education is not None
            user.current_education.institution = institution1

        # Filter by institution1 - should only include users from that institution
        response = await user_client.get(
            f"/api/users/ranking?score_type=xp&institution_id={institution1.id}"
        )
        assert response.status_code == 200

        ranking = response.json()
        assert len(ranking) == 2  # user_inst1 and asking user

        # Should only include users from institution1
        user_ids = {r["id"] for r in ranking}
        assert user_inst1.id in user_ids
        assert user.id in user_ids
        assert user_inst2.id not in user_ids

    async def test_get_user_ranking_filter_by_course(
        self,
        user_client: AsyncClient,
        user: User,
        session: AsyncSession,
        education_level: EducationLevel,
    ):
        """Test filtering ranking by course."""
        async with session.begin():
            course1 = await CourseFactory.create(
                session=session, name_i18n={"en": "Computer Science"}
            )
            course2 = await CourseFactory.create(
                session=session, name_i18n={"en": "Mathematics"}
            )

            # Create users with different courses
            user_cs = await UserFactory.create(
                session=session, xp_score=700, username="csuser"
            )
            assert user_cs.current_education is not None
            user_cs.current_education.course = course1

            user_math = await UserFactory.create(
                session=session,
                xp_score=800,
                username="mathuser",
            )
            assert user_math.current_education is not None
            user_math.current_education.course = course2

            assert user.current_education is not None
            user.current_education.course = course1

        # Filter by Computer Science course
        response = await user_client.get(
            f"/api/users/ranking?score_type=xp&course_id={course1.id}"
        )
        assert response.status_code == 200

        ranking = response.json()

        # Should only include users from CS course + asking user
        user_ids = {r["id"] for r in ranking}
        assert user_cs.id in user_ids
        assert user.id in user_ids
        assert user_math.id not in user_ids

    async def test_get_user_ranking_filter_by_education_level(
        self, user_client: AsyncClient, user: User, session: AsyncSession
    ):
        """Test filtering ranking by education level."""
        async with session.begin():
            level1 = await EducationLevelFactory.create(
                session=session, name_i18n={"en": "Bachelor"}
            )
            level2 = await EducationLevelFactory.create(
                session=session, name_i18n={"en": "Master"}
            )

            # Create users with different education levels
            user_bachelor = await UserFactory.create(
                session=session,
                xp_score=600,
                username="bachelor",
            )
            assert user_bachelor.current_education is not None
            user_bachelor.current_education.level = level1

            user_master = await UserFactory.create(
                session=session, xp_score=700, username="master"
            )
            assert user_master.current_education is not None
            user_master.current_education.level = level2

        # Filter by Bachelor level
        response = await user_client.get(
            f"/api/users/ranking?score_type=xp&education_level_id={level1.id}"
        )
        assert response.status_code == 200

        ranking = response.json()

        # Should only include users from Bachelor level + asking user
        user_ids = {r["id"] for r in ranking}
        assert user_bachelor.id in user_ids
        assert user_master.id not in user_ids

    async def test_get_user_ranking_asking_user_included_outside_top_10(
        self, user_client: AsyncClient, user: User, session: AsyncSession
    ):
        """Test that asking user is included in ranking even if outside top 10."""
        async with session.begin():
            country = await CountryFactory.create(session=session)

            # Create 12 users with higher XP scores than the asking user
            await UserFactory.create_batch(
                12, session=session, xp_score=1000, country=country
            )

        response = await user_client.get("/api/users/ranking?score_type=xp")
        assert response.status_code == 200

        ranking = response.json()
        # Should include top 10 + asking user (who is rank 13)
        assert len(ranking) == 11

        # First 10 should be the high scorers
        for i in range(10):
            assert ranking[i]["score"] == 1000
            assert ranking[i]["rank"] == 1  # They all have the same score, so same rank

        # Last entry should be the asking user
        assert ranking[10]["id"] == user.id
        assert ranking[10]["score"] == 0
        assert ranking[10]["rank"] == 2

    async def test_get_user_ranking_invalid_score_type(self, user_client: AsyncClient):
        """Test ranking with invalid score type."""
        response = await user_client.get("/api/users/ranking?score_type=invalid")
        assert response.status_code == 422

    async def test_get_user_ranking_missing_score_type(self, user_client: AsyncClient):
        """Test ranking without score_type parameter."""
        response = await user_client.get("/api/users/ranking")
        assert response.status_code == 422

    async def test_get_user_ranking_authorization_required(self, client: AsyncClient):
        """Test that authorization is required for user ranking endpoint."""
        response = await client.get("/api/users/ranking?score_type=xp")
        assert response.status_code == 401

    async def test_get_user_ranking_with_tied_scores(
        self, user_client: AsyncClient, user: User, session: AsyncSession
    ):
        """Test ranking behavior with tied scores."""
        async with session.begin():
            # Create users with tied scores
            await UserFactory.create(session=session, xp_score=500, username="tied1")
            await UserFactory.create(session=session, xp_score=500, username="tied2")
            await UserFactory.create(session=session, xp_score=300, username="unique")

        response = await user_client.get("/api/users/ranking?score_type=xp")
        assert response.status_code == 200

        ranking = response.json()
        assert len(ranking) == 4

        # Both tied users should have rank 1
        tied_users = [r for r in ranking if r["score"] == 500]
        assert len(tied_users) == 2
        for tied_user in tied_users:
            assert tied_user["rank"] == 1

        # User with 300 score should have rank 2
        unique_user = next(r for r in ranking if r["score"] == 300)
        assert unique_user["rank"] == 2

    async def test_get_user_ranking_response_schema(
        self, user_client: AsyncClient, user: User, session: AsyncSession
    ):
        """Test that ranking response matches expected schema."""
        response = await user_client.get("/api/users/ranking?score_type=xp")
        assert response.status_code == 200
        ranking = response.json()

        assert len(ranking) >= 1
        user_rank = ranking[-1]  # Asking user should be last if they have 0 score

        # Verify all required fields are present and correct types
        assert isinstance(user_rank["id"], int)
        assert isinstance(user_rank["username"], str)
        assert isinstance(user_rank["rank"], int)
        assert isinstance(user_rank["score"], int)
        assert user_rank["id"] == user.id
        assert user_rank["username"] == user.username

        # current_education can be null or an object
        if user_rank["current_education"] is not None:
            education = user_rank["current_education"]
            assert isinstance(education["level_id"], int)
            assert isinstance(education["institution_id"], int)
            assert isinstance(education["course_id"], int)
            # stage_id can be null
            if education["stage_id"] is not None:
                assert isinstance(education["stage_id"], int)

    async def test_get_user_ranking_multiple_filters_combined(
        self,
        user_client: AsyncClient,
        user: User,
        session: AsyncSession,
        education_level: EducationLevel,
    ):
        """Test ranking with multiple filters applied simultaneously."""
        async with session.begin():
            institution = await InstitutionFactory.create(session=session)
            course1 = await CourseFactory.create(session=session)
            course2 = await CourseFactory.create(session=session)

            # Create user matching all filters
            user_match = await UserFactory.create(
                session=session, xp_score=800, username="match"
            )
            assert user_match.current_education is not None
            user_match.current_education.level = education_level
            user_match.current_education.institution = institution
            user_match.current_education.course = course1

            # Create user matching only some filters
            user_partial = await UserFactory.create(
                session=session,
                xp_score=900,
                username="partial",
            )
            assert user_partial.current_education is not None
            user_partial.current_education.level = education_level
            user_partial.current_education.institution = institution
            user_partial.current_education.course = course2

        # Apply multiple filters
        response = await user_client.get(
            f"/api/users/ranking?score_type=xp&institution_id={institution.id}&course_id={course1.id}&education_level_id={education_level.id}"
        )
        assert response.status_code == 200

        ranking = response.json()

        # Should only include users matching all filters + asking user
        user_ids = {r["id"] for r in ranking}
        assert user_match.id in user_ids
        assert user_partial.id not in user_ids  # Doesn't match course filter
