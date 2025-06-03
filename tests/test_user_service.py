import re
import unittest.mock as mock
from unittest.mock import patch

import pytest
from arq import Worker
from sqlalchemy.ext.asyncio import AsyncSession

from app.users import service as user_service
from app.users.constants import WELCOME_EMAIL_SUBJECT
from app.users.models import SignupSource, UserProfile
from app.users.service import (
    EmailAlreadyExists,
    ReferredByNotFoundError,
    UsernameAlreadyExists,
    create_user_by_password,
)
from tests.conftest import DummySESClient
from tests.factories import UserFactory


class TestCreateUserByPassword:
    """Test suite for the create_user_by_password function."""

    async def test_create_user_success(
        self,
        session: AsyncSession,
        dummy_ses_client: DummySESClient,
        arq_worker: Worker,
    ) -> None:
        """Test successful user creation with all required fields."""
        # Arrange
        name = "João Silva"
        password = "secure_password123"
        email = "joao.silva@example.com"
        signup_source = SignupSource.SOCIAL

        # Act
        async with session.begin():
            user = await create_user_by_password(
                session,
                name=name,
                password=password,
                email=email,
                referred_by_username=None,
                signup_source=signup_source,
            )

        # Process email queue
        await arq_worker.async_run()

        # Assert
        assert user.name == name
        assert user.email == email
        assert user.signup_source == signup_source
        assert user.referred_by_id is None

        # Username should be normalized version of name + 4 digits
        expected_username_pattern = r"^joao_silva\d{4}$"
        assert re.match(expected_username_pattern, user.username)

        # Password should be hashed
        assert user.hashed_password != password
        assert user_service.verify_password(password, user.hashed_password)

        # User should have a profile
        assert user.profile is not None
        assert isinstance(user.profile, UserProfile)

        # Welcome email should be sent
        assert len(dummy_ses_client.sent_emails) == 1
        sent_email = dummy_ses_client.sent_emails[0]
        assert sent_email["Destination"]["ToAddresses"] == [email]  # type: ignore
        assert sent_email["Message"]["Subject"]["Data"] == WELCOME_EMAIL_SUBJECT  # type: ignore

    async def test_create_user_with_referral(
        self,
        session: AsyncSession,
        dummy_ses_client: DummySESClient,
        arq_worker: Worker,
    ) -> None:
        """Test user creation with valid referral."""
        # Arrange
        async with session.begin():
            referring_user = await UserFactory.create(session=session)
        name = "Maria Santos"
        password = "password123"
        email = "maria.santos@example.com"

        # Act
        async with session.begin():
            user = await create_user_by_password(
                session,
                name=name,
                password=password,
                email=email,
                referred_by_username=referring_user.username,
                signup_source=SignupSource.REFERRAL,
            )

        # Process email queue
        await arq_worker.async_run()

        # Assert
        assert user.referred_by_id == referring_user.id
        assert user.signup_source == SignupSource.REFERRAL

    async def test_create_user_invalid_referral(self, session: AsyncSession) -> None:
        """Test user creation fails with invalid referral username."""
        # Arrange
        name = "Pedro Costa"
        password = "password123"
        email = "pedro.costa@example.com"
        invalid_username = "nonexistent_user"

        # Act & Assert
        async with session.begin():
            with pytest.raises(ReferredByNotFoundError):
                await create_user_by_password(
                    session,
                    name=name,
                    password=password,
                    email=email,
                    referred_by_username=invalid_username,
                    signup_source=SignupSource.REFERRAL,
                )

    async def test_create_user_duplicate_email(self, session: AsyncSession) -> None:
        """Test user creation fails with duplicate email."""
        # Arrange
        async with session.begin():
            existing_user = await UserFactory.create(session=session)
        name = "Ana Lima"
        password = "password123"

        # Act & Assert
        async with session.begin():
            with pytest.raises(EmailAlreadyExists):
                await create_user_by_password(
                    session,
                    name=name,
                    password=password,
                    email=existing_user.email,  # Using existing email
                    referred_by_username=None,
                    signup_source=SignupSource.SOCIAL,
                )

    @patch("app.users.service.random.randint")
    async def test_create_user_duplicate_username(
        self,
        mock_randint: mock.Mock,
        session: AsyncSession,
    ) -> None:
        """Test user creation fails with duplicate username."""
        # Arrange
        mock_randint.return_value = 1234  # Fixed random number

        # Create a user with a username that will conflict
        async with session.begin():
            existing_user = await UserFactory.create(session=session)
            existing_user.username = "test_user1234"
            await session.flush()

        name = "Test User"  # This normalizes to "test_user"
        password = "password123"
        email = "test.user@example.com"

        # Act & Assert - Should raise UsernameAlreadyExists due to collision
        async with session.begin():
            with pytest.raises(UsernameAlreadyExists):
                await create_user_by_password(
                    session,
                    name=name,
                    password=password,
                    email=email,
                    referred_by_username=None,
                    signup_source=SignupSource.SOCIAL,
                )

    @pytest.mark.parametrize(
        "name,expected_username_base",
        [
            ("João da Silva", "joao_da_silva"),  # Accent removal
            ("Maria José", "maria_jose"),  # Space to underscore
            ("Pedro@123", "pedro123"),  # Special character removal
            ("Ana_Maria", "ana_maria"),  # Underscore preservation
            ("CARLOS", "carlos"),  # Lowercase conversion
            (
                "  Spaces  ",
                "__spaces__",
            ),  # Whitespace handling (spaces become underscores)
            ("José-António", "joseantonio"),  # Hyphen removed, accents removed
        ],
    )
    async def test_username_normalization(
        self,
        session: AsyncSession,
        dummy_ses_client: DummySESClient,
        arq_worker: Worker,
        name: str,
        expected_username_base: str,
    ) -> None:
        """Test that usernames are properly normalized from various name formats."""
        # Arrange
        password = "password123"
        email = f"{expected_username_base}@example.com"

        # Act
        async with session.begin():
            user = await create_user_by_password(
                session,
                name=name,
                password=password,
                email=email,
                referred_by_username=None,
                signup_source=SignupSource.SOCIAL,
            )

        # Process email queue
        await arq_worker.async_run()

        # Assert
        expected_pattern = rf"^{re.escape(expected_username_base)}\d{{4}}$"
        assert re.match(expected_pattern, user.username)

    async def test_create_user_different_signup_sources(
        self,
        session: AsyncSession,
        dummy_ses_client: DummySESClient,
        arq_worker: Worker,
    ) -> None:
        """Test user creation with different signup sources."""
        test_cases = [
            SignupSource.SOCIAL,
            SignupSource.REFERRAL,
            SignupSource.INTERNET,
            SignupSource.TEACHER,
            SignupSource.EVENT,
            SignupSource.OTHER,
        ]

        for signup_source in test_cases:
            # Arrange
            name = f"User {signup_source.value}"
            password = "password123"
            email = f"user_{signup_source.value}@example.com"

            # Act
            async with session.begin():
                user = await create_user_by_password(
                    session,
                    name=name,
                    password=password,
                    email=email,
                    referred_by_username=None,
                    signup_source=signup_source,
                )

            # Assert
            assert user.signup_source == signup_source

        # Process email queue for all users
        await arq_worker.async_run()

    async def test_create_user_profile_creation(
        self,
        session: AsyncSession,
        dummy_ses_client: DummySESClient,
        arq_worker: Worker,
    ) -> None:
        """Test that UserProfile is created along with User."""
        # Arrange
        name = "Profile Test User"
        password = "password123"
        email = "profile.test@example.com"

        # Act
        async with session.begin():
            user = await create_user_by_password(
                session,
                name=name,
                password=password,
                email=email,
                referred_by_username=None,
                signup_source=SignupSource.SOCIAL,
            )

        # Process email queue
        await arq_worker.async_run()

        # Assert
        assert user.profile is not None
        assert isinstance(user.profile, UserProfile)
        assert user.profile.user_id == user.id

    async def test_create_user_database_persistence(
        self,
        session: AsyncSession,
        dummy_ses_client: DummySESClient,
        arq_worker: Worker,
    ) -> None:
        """Test that created user persists in database correctly."""
        # Arrange
        name = "Persistence Test"
        password = "password123"
        email = "persistence@example.com"

        # Act
        async with session.begin():
            user = await create_user_by_password(
                session,
                name=name,
                password=password,
                email=email,
                referred_by_username=None,
                signup_source=SignupSource.SOCIAL,
            )

        # Process email queue
        await arq_worker.async_run()

        # Assert - Fetch user from database
        async with session.begin():
            found_user = await user_service.get_user(session, id=user.id)
            assert found_user is not None
            assert found_user.name == name
            assert found_user.email == email
            assert found_user.username == user.username

    async def test_create_user_welcome_email_content(
        self,
        session: AsyncSession,
        dummy_ses_client: DummySESClient,
        arq_worker: Worker,
    ) -> None:
        """Test that welcome email contains correct content."""
        # Arrange
        name = "Welcome Email Test"
        password = "password123"
        email = "welcome@example.com"

        # Act
        async with session.begin():
            user = await create_user_by_password(
                session,
                name=name,
                password=password,
                email=email,
                referred_by_username=None,
                signup_source=SignupSource.SOCIAL,
            )

        # Process email queue
        await arq_worker.async_run()

        # Assert
        assert len(dummy_ses_client.sent_emails) == 1
        sent_email = dummy_ses_client.sent_emails[0]

        # Check email structure
        assert sent_email["Destination"]["ToAddresses"] == [email]  # type: ignore
        assert sent_email["Message"]["Subject"]["Data"] == WELCOME_EMAIL_SUBJECT  # type: ignore

        # Check that username is included in the email body
        email_body = sent_email["Message"]["Body"]["Html"]["Data"]  # type: ignore
        assert user.username in email_body

    async def test_create_user_referrals_refresh(
        self,
        session: AsyncSession,
        dummy_ses_client: DummySESClient,
        arq_worker: Worker,
    ) -> None:
        """Test that user referrals and profile are properly refreshed after creation."""
        # Arrange
        name = "Refresh Test"
        password = "password123"
        email = "refresh@example.com"

        # Act
        async with session.begin():
            user = await create_user_by_password(
                session,
                name=name,
                password=password,
                email=email,
                referred_by_username=None,
                signup_source=SignupSource.SOCIAL,
            )

        # Process email queue
        await arq_worker.async_run()

        # Assert - These attributes should be accessible after refresh
        assert hasattr(user, "referrals")
        assert hasattr(user, "profile")
        assert user.profile is not None

    async def test_create_user_default_values(
        self,
        session: AsyncSession,
        dummy_ses_client: DummySESClient,
        arq_worker: Worker,
    ) -> None:
        """Test that users are created with correct default values."""
        # Arrange
        name = "Default Values Test"
        password = "password123"
        email = "defaults@example.com"

        # Act
        async with session.begin():
            user = await create_user_by_password(
                session,
                name=name,
                password=password,
                email=email,
                referred_by_username=None,
                signup_source=SignupSource.SOCIAL,
            )

        # Process email queue
        await arq_worker.async_run()

        # Assert default values
        assert user.is_superuser is False
        assert user.is_premium is False
        assert user.is_bot is False
        assert user.bot_difficulty is None
        assert user.phone_number == ""
        assert user.google_id == ""
        assert user.apple_id == ""
        assert user.current_education_id is None
        assert user.intended_education_id is None

    async def test_create_user_profile_default_values(
        self,
        session: AsyncSession,
        dummy_ses_client: DummySESClient,
        arq_worker: Worker,
    ) -> None:
        """Test that UserProfile is created with correct default values."""
        # Arrange
        name = "Profile Defaults Test"
        password = "password123"
        email = "profile.defaults@example.com"

        # Act
        async with session.begin():
            user = await create_user_by_password(
                session,
                name=name,
                password=password,
                email=email,
                referred_by_username=None,
                signup_source=SignupSource.SOCIAL,
            )

        # Process email queue
        await arq_worker.async_run()

        # Assert profile default values
        assert user.profile.social_score == 0
        assert user.profile.xp_score == 0
        assert user.profile.user_id == user.id
