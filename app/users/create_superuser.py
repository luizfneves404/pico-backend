import asyncio

from pydantic import SecretStr

from app.config import settings
from app.database import db_manager
from app.users.models import User
from app.users.schemas import SignupSource, UserIn
from app.users.service import get_password_hash, get_user


async def create_superuser(
    username: str,
    email: str,
    phone_number: str,
    password: str,
) -> User | None:
    """Create a superuser in the database.

    Args:
        username: The username for the superuser
        email: The email for the superuser
        phone_number: The phone number for the superuser
        password: The password for the superuser

    Returns:
        The created User object if successful, None if user already exists
    """
    async with db_manager.use_db(settings.database_url):
        async with db_manager.session_with_transaction() as session:
            # Check if user already exists
            existing_user = await get_user(session, username=username)
            if existing_user:
                print(f"User {username} already exists")
                return None

            # Create new user
            user_data = UserIn(
                username=username,
                email=email,
                phone_number=phone_number,
                password=SecretStr(password),
                referred_by_username="",
                signup_source=SignupSource.OTHER,  # Mark as admin-created
            )

            hashed_password = get_password_hash(user_data.password.get_secret_value())
            db_user = User(
                username=str(user_data.username),
                email=str(user_data.email),
                phone_number=str(user_data.phone_number),
                hashed_password=str(hashed_password),
                is_superuser=True,
            )

            session.add(db_user)
            await session.flush()

            print(f"Superuser {username} created successfully")
            return db_user


async def main():
    """Main function to create a superuser."""
    username = input("Enter username: ")
    email = input("Enter email: ")
    phone_number = input("Enter phone number: ")
    password = input("Enter password: ")

    user = await create_superuser(username, email, phone_number, password)
    if user:
        print(f"Superuser created successfully with ID: {user.id}")


if __name__ == "__main__":
    asyncio.run(main())
