import asyncio

from database import db_manager
from pydantic import SecretStr
from users.models import EducationLevel, User
from users.schemas import PhoneNumber, UserIn
from users.service import get_password_hash, get_user

from app.config import settings


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
    async with db_manager.connect_db(settings.database_url):
        async with db_manager.session() as session, session.begin():
            # Check if user already exists
            existing_user = await get_user(session, username=username)
            if existing_user:
                print(f"User {username} already exists")
                return None

            # Create new user
            user_data = UserIn(
                username=username,
                email=email,
                phone_number=PhoneNumber(phone_number),
                password=SecretStr(password),
                chosen_college="",
                chosen_course="",
                education_level=EducationLevel.UNKNOWN,
                commitment=20,
                referred_by_username="",
            )

            hashed_password = get_password_hash(user_data.password.get_secret_value())
            db_user = User(
                username=str(user_data.username),
                email=str(user_data.email),
                phone_number=str(user_data.phone_number),
                hashed_password=str(hashed_password),
                is_superuser=True,
                education_level=EducationLevel.UNKNOWN,
                commitment=20,
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
