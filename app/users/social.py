import logging
from typing import Literal

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.validation import CustomPhoneNumber
from app.users.models import User

logger = logging.getLogger(__name__)

phone_number_adapter: TypeAdapter[CustomPhoneNumber] = TypeAdapter(CustomPhoneNumber)


async def check_contacts(
    db_session: AsyncSession, raw_phone_numbers: list[str]
) -> list[User]:
    """Check which contacts are registered users.

    Args:
        db_session: The database session
        raw_phone_numbers: List of raw phone numbers to check

    Returns:
        List of users that match the phone numbers
    """
    phone_numbers: list[str] = []
    for phone_number in raw_phone_numbers:
        try:
            phone_numbers.append(phone_number_adapter.validate_python(phone_number))
        except ValidationError:
            pass
    logger.debug(
        f"Contacts checked! There were {len(phone_numbers)} valid phone numbers"
    )
    matched_users = (
        await db_session.scalars(
            select(User)
            .where(User.phone_number.in_(phone_numbers))
            .order_by(User.username)
        )
    ).all()
    logger.debug(f"Found {len(matched_users)} matching users after checking contacts")
    return list(matched_users)


async def search_username(db_session: AsyncSession, username: str) -> list[User]:
    """Search for users by username.

    Args:
        db_session: The database session
        username: Username pattern to search for

    Returns:
        List of users matching the search pattern
    """
    logger.debug(f"Searching for username containing '{username}'")
    return list(
        (
            await db_session.scalars(
                select(User)
                .where(User.username.ilike(f"%{username}%"))
                .order_by(User.username)
            )
        ).all()
    )


async def get_ranking(
    db_session: AsyncSession,
    *,
    asking_user_id: int,
    score_type: Literal["xp", "social"],
    institution_id: int | None,
    course_id: int | None,
    education_level_id: int | None,
    subject: str | None = None,
) -> list[User]:
    """Get user ranking based on various filters.

    Args:
        db_session: The database session
        asking_user_id: ID of the user asking for the ranking
        score_type: Type of scoring to use
        institution_id: Filter by institution ID
        course_id: Filter by course ID
        education_level_id: Filter by education level ID
        subject: Subject for percentage-based ranking

    Returns:
        List of ranked user statistics

    Note:
        This function needs to be updated to work with the new education structure
        For now, keeping the basic structure but this will need more work
    """
    # Note: This function needs to be updated to work with the new education structure
    # For now, keeping the basic structure but this will need more work
    stmt = select(User.id)
    if institution_id:
        stmt = stmt.where(User.institution_id == institution_id)
    if course_id:
        stmt = stmt.where(User.course_id == course_id)
    if education_level_id:
        stmt = stmt.where(User.education_level_id == education_level_id)

    users_ids = await db_session.scalars(stmt)
    # Note: quiz_service is not imported, this will need to be fixed
    # if score_type == "xp":
    #     return await quiz_service.get_ranked_users_stats_by_dynamic_score(
    #         users_ids, NUM_RANKED_USERS, asking_user_id
    #     )
    # elif score_type == "social":
    #     return await quiz_service.get_ranked_users_stats_by_percentage(
    #         users_ids, NUM_RANKED_USERS, asking_user_id, subject
    #     )
    # else:
    #     raise ValueError(f"Invalid score type: {score_type}")
    return []  # Placeholder
