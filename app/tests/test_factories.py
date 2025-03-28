from sqlalchemy.ext.asyncio import AsyncSession
from users.service import verify_password


async def test_create_user(session: AsyncSession, user) -> None:
    """Test creating a user with the factory."""
    # Verify the user was created with default values
    assert user.username.startswith("user")
    assert user.email == f"{user.username}@example.com"
    assert user.phone_number.startswith("+5511999999")
    assert verify_password("defaultpassword", user.hashed_password)
    assert user.is_superuser is False
    assert user.education_level == "TYHS"
    assert user.is_premium is False
    assert user.commitment == 20
    assert user.balance == 0
    assert user.is_bot is False
    assert user.bot_difficulty is None
    assert user.signup_source == "social"
