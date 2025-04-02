from sqlalchemy.ext.asyncio import AsyncSession

from app.users.models import User
from app.users.service import verify_password


async def test_create_user(session: AsyncSession, user: User) -> None:
    """Test creating a user with the factory."""
    # Verify the user was created with default values
    assert user.username.startswith("user")
    assert user.email == f"{user.username}@example.com"
    assert user.phone_number.startswith("tel:+55-11-99999-9")
    assert verify_password("defaultpassword", user.hashed_password)
    assert user.is_superuser is False
    assert user.education_level == "TYHS"
    assert user.is_premium is False
    assert user.commitment == 20
    assert user.balance == 0
    assert user.is_bot is False
    assert user.bot_difficulty is None
    assert user.signup_source == "social"
