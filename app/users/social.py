import logging
from dataclasses import dataclass
from typing import Literal

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.pagination import PaginationParams, paginate_query
from app.shared.validation import CustomPhoneNumber
from app.users.models import User

logger = logging.getLogger(__name__)

NUM_RANKED_USERS = 100

phone_number_adapter: TypeAdapter[CustomPhoneNumber] = TypeAdapter(CustomPhoneNumber)


async def check_contacts(
    db_session: AsyncSession,
    raw_phone_numbers: list[str],
    pagination: PaginationParams,
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
    stmt = (
        select(User).where(User.phone_number.in_(phone_numbers)).order_by(User.username)
    )
    stmt = paginate_query(stmt, pagination)
    matched_users = list(await db_session.scalars(stmt))
    return list(matched_users)


async def search_username(
    db_session: AsyncSession,
    username: str,
    pagination: PaginationParams,
) -> list[User]:
    """Search for users by username.

    Args:
        db_session: The database session
        username: Username pattern to search for

    Returns:
        List of users matching the search pattern
    """
    logger.debug(f"Searching for username containing '{username}'")
    stmt = (
        select(User).where(User.username.ilike(f"%{username}%")).order_by(User.username)
    )
    stmt = paginate_query(stmt, pagination)
    return list(await db_session.scalars(stmt))


@dataclass(frozen=True, slots=True, kw_only=True)
class UserInRanking:
    id: int
    score: float
    rank: int


async def get_ranking(
    db_session: AsyncSession,
    *,
    asking_user_id: int,
    score_type: Literal["xp", "social"],
    institution_id: int | None,
    stage_id: int | None,
    course_id: int | None,
    education_level_id: int | None,
    subject: str | None,
) -> list[UserInRanking]:
    """Get user ranking based on various filters.

    Args:
        db_session: The database session
        asking_user_id: ID of the user asking for the ranking
        score_type: Type of scoring to use
        institution_id: Filter by institution ID
        stage_id: Filter by stage ID
        course_id: Filter by course ID
        education_level_id: Filter by education level ID

    Returns:
        List of ranked user statistics

    Note:
        This function needs to be updated to work with the new education structure
        For now, keeping the basic structure but this will need more work
    """
    score_column = User.xp_score if score_type == "xp" else User.social_score

    # Create CTE with all ranked users matching filters
    ranked_users_cte = select(
        User.id,
        score_column.label("score"),
        func.rank().over(order_by=score_column.desc()).label("rank"),
    )
    if institution_id:
        ranked_users_cte = ranked_users_cte.where(
            User.current_education.has(institution_id=institution_id)
        )
    if course_id:
        ranked_users_cte = ranked_users_cte.where(
            User.current_education.has(course_id=course_id)
        )
    if stage_id:
        ranked_users_cte = ranked_users_cte.where(
            User.current_education.has(stage_id=stage_id)
        )
    if education_level_id:
        ranked_users_cte = ranked_users_cte.where(
            User.current_education.has(level_id=education_level_id)
        )

    ranked_users_cte = ranked_users_cte.cte("ranked_users")

    # Select top users plus asking user if not in top
    stmt = (
        select(
            ranked_users_cte.c.id,
            ranked_users_cte.c.score,
            ranked_users_cte.c.rank,
        )
        .where(
            (ranked_users_cte.c.rank <= NUM_RANKED_USERS)
            | (ranked_users_cte.c.id == asking_user_id)
        )
        .order_by(ranked_users_cte.c.rank)
    )

    results = await db_session.execute(stmt)
    return [
        UserInRanking(id=result[0], score=result[1], rank=result[2])
        for result in results
    ]
