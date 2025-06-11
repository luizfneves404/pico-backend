import re
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.community.models import Community, CommunityUser
from app.config import settings
from app.education.models import EducationLevel
from app.users import external_auth
from app.users.exceptions import (
    InvalidTokenError,
)
from app.users.external_auth import AppleIdToken, GoogleIdToken
from app.users.models import User
from tests.factories import (
    CollegeFactory,
    CourseFactory,
    SchoolFactory,
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
        headers = {"Authorization": f"Bearer {token_response.json()['access']}"}
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
        print(response.json())
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
        assert "access" in response_data
        assert "refresh" in response_data

        # Verify JWT token contains correct data
        decoded_token = jwt.decode(
            response_data["access"], settings.secret_key, algorithms=["HS256"]
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
            response_data["access"], settings.secret_key, algorithms=["HS256"]
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
            response_data["access"], settings.secret_key, algorithms=["HS256"]
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
        assert "access" in response_data
        assert "refresh" in response_data

        # Verify JWT token
        decoded_token = jwt.decode(
            response_data["access"], settings.secret_key, algorithms=["HS256"]
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
            response_data["access"], settings.secret_key, algorithms=["HS256"]
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
            response_data["access"], settings.secret_key, algorithms=["HS256"]
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
            response_data["access"], settings.secret_key, algorithms=["HS256"]
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
        self, user_client: AsyncClient, session: AsyncSession
    ):
        """Test updating education information."""
        async with session.begin():
            school = await SchoolFactory.create(session=session)
            college = await CollegeFactory.create(session=session)
            course = await CourseFactory.create(session=session)

        # Update current education
        data = {
            "updates": {
                "current_education": {
                    "level": "TGHS",
                    "institution_id": school.id,
                    "course_id": course.id,
                }
            }
        }
        response = await user_client.patch("/api/users/me", json=data)
        print(response.json())
        assert response.status_code == 200
        response_data = response.json()
        assert "current_education" in response_data["updated_fields"]
        assert response_data["user"]["current_education"]["level"] == "TGHS"
        assert response_data["user"]["current_education"]["institution_id"] == school.id
        assert response_data["user"]["current_education"]["course_id"] == course.id

        # Update intended education
        data = {
            "updates": {
                "intended_education": {
                    "level": "COL",
                    "institution_id": college.id,
                    "course_id": course.id,
                }
            }
        }
        response = await user_client.patch("/api/users/me", json=data)
        assert response.status_code == 200
        response_data = response.json()
        assert "intended_education" in response_data["updated_fields"]
        assert response_data["user"]["intended_education"]["level"] == "COL"
        assert (
            response_data["user"]["intended_education"]["institution_id"] == college.id
        )
        assert response_data["user"]["intended_education"]["course_id"] == course.id

        # Clear education fields
        data = {"updates": {"current_education": None}}
        response = await user_client.patch("/api/users/me", json=data)
        assert response.status_code == 200
        response_data = response.json()
        assert "current_education" in response_data["updated_fields"]
        assert response_data["user"]["current_education"] is None

        data = {"updates": {"intended_education": None}}
        response = await user_client.patch("/api/users/me", json=data)
        assert response.status_code == 200
        response_data = response.json()
        assert "intended_education" in response_data["updated_fields"]
        assert response_data["user"]["intended_education"] is None

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
        assert response.json()["total"] == 7
        assert response.json()["page"] == 1
        assert response.json()["size"] == 4

        # Test second page
        new_url = "/api/users/check-contacts?page=2&size=4"
        new_response = await user_client.post(new_url, json=data)
        assert new_response.status_code == 200
        new_results = new_response.json()["items"]
        new_response_ids = [user["id"] for user in new_results]
        assert len(new_response_ids) == 3
        assert new_response.json()["total"] == 7
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
        assert response.json()["total"] == 7
        assert response.json()["page"] == 1
        assert response.json()["size"] == 4

        # Test second page
        new_url = "/api/users/search-username?username=searchuser&page=2&size=4"
        new_response = await user_client.get(new_url)
        assert new_response.status_code == 200
        new_results = new_response.json()["items"]
        new_response_ids = [user["id"] for user in new_results]
        assert len(new_response_ids) == 3
        assert new_response.json()["total"] == 7
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
            users = await UserFactory.create_batch(50, session=session)

        phone_numbers = [str(user.phone_number) for user in users[:30]]
        data = {"phone_numbers": phone_numbers}

        response = await user_client.post(
            "/api/users/check-contacts?page=1&size=20", json=data
        )
        assert response.status_code == 200
        assert len(response.json()["items"]) == 20
        assert response.json()["total"] == 30

    async def test_user_auto_joins_communities_on_education_change(
        self,
        user: User,
        user_client: AsyncClient,
        session: AsyncSession,
        level: EducationLevel,
        expected_community_subtitle: str,
    ) -> None:
        """Test that users automatically join communities based on their education when changed."""
        # Create education resources first
        async with session.begin():
            institution = (
                await SchoolFactory.create(session=session)
                if level_id == 1
                else await CollegeFactory.create(session=session)
            )
            course = await CourseFactory.create(session=session)

        print("institution", institution.name)
        print("course", course.name)

        async with session.begin():
            response = await user_client.patch(
                "/api/users/me",
                json={
                    "updates": {
                        "current_education": {
                            "level": level,
                            "institution_id": institution.id,
                            "course_id": course.id,
                        }
                    },
                },
            )
            assert response.status_code == 200
            assert response.json()["updated_fields"] == ["current_education"]
            assert response.json()["user"]["current_education"]["level"] == level
            assert (
                response.json()["user"]["current_education"]["institution_id"]
                == institution.id
            )

        # Verify community was created and user joined it
        async with session.begin():
            print("searched community", institution.name, expected_community_subtitle)
            print(
                "all communities",
                [
                    (community.name, community.subtitle)
                    for community in await session.scalars(select(Community))
                ],
            )
            result = await session.execute(
                select(Community).where(
                    Community.name == institution.name,
                    Community.subtitle == expected_community_subtitle,
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
