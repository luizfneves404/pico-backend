import contextlib
import logging
from dataclasses import dataclass
from typing import Literal

from pydantic import ValidationError
from sqlalchemy import func, join, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.education.models import EducationInfo
from app.pagination import PaginationParams, paginate_query
from app.shared.validation import phone_number_adapter
from app.users.constants import SENTINEL_USERNAMES
from app.users.models import User

logger = logging.getLogger(__name__)

NUM_RANKED_USERS = 10


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
        with contextlib.suppress(ValidationError):
            phone_numbers.append(phone_number_adapter.validate_python(phone_number))
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


@dataclass
class CurrentEducationForRanking:
    level_id: int
    institution_id: int
    course_id: int
    stage_id: int


@dataclass(frozen=True, slots=True, kw_only=True)
class UserInRanking:
    id: int
    score: int
    rank: int
    current_education: CurrentEducationForRanking | None
    username: str


async def get_ranking(
    db_session: AsyncSession,
    *,
    asking_user_id: int,
    score_type: Literal["xp", "social"],
    institution_id: int | None,
    stage_id: int | None,
    course_id: int | None,
    education_level_id: int | None,
) -> list[UserInRanking]:
    """
    Get user ranking based on various filters, returning a maximum of
    NUM_RANKED_USERS + 1 (the asking user).
    """
    score_column = User.xp_score if score_type == "xp" else User.social_score

    ranked_users_cte_stmt = select(
        User.id,
        User.username,
        score_column.label("score"),
        func.dense_rank().over(order_by=score_column.desc()).label("rank"),
        EducationInfo.level_id,
        EducationInfo.institution_id,
        EducationInfo.course_id,
        EducationInfo.stage_id,
    ).select_from(
        join(
            User,
            EducationInfo,
            User.current_education_id == EducationInfo.id,
            isouter=True,
        )
    )
    ranked_users_cte_stmt = ranked_users_cte_stmt.where(
        ~User.username.in_(SENTINEL_USERNAMES)
    )

    if institution_id:
        ranked_users_cte_stmt = ranked_users_cte_stmt.where(
            EducationInfo.institution_id == institution_id
        )
    if course_id:
        ranked_users_cte_stmt = ranked_users_cte_stmt.where(
            EducationInfo.course_id == course_id
        )
    if stage_id:
        ranked_users_cte_stmt = ranked_users_cte_stmt.where(
            EducationInfo.stage_id == stage_id
        )
    if education_level_id:
        ranked_users_cte_stmt = ranked_users_cte_stmt.where(
            EducationInfo.level_id == education_level_id
        )

    ranked_users_cte = ranked_users_cte_stmt.cte("ranked_users")

    top_users_query = (
        select(ranked_users_cte)
        .order_by(ranked_users_cte.c.rank)
        .limit(NUM_RANKED_USERS)
    )

    asking_user_query = select(ranked_users_cte).where(
        ranked_users_cte.c.id == asking_user_id
    )

    final_union = top_users_query.union(asking_user_query)
    union_subquery = final_union.subquery()

    stmt = select(union_subquery).order_by(union_subquery.c.rank)

    results = await db_session.execute(
        select(func.distinct(EducationInfo.institution_id)).order_by(
            EducationInfo.institution_id
        )
    )
    print(results.all())
    results = await db_session.execute(
        select(func.count(EducationInfo.id)).where(
            EducationInfo.institution_id == institution_id
        )
    )
    print(results.all())

    results = await db_session.execute(stmt)

    return [
        UserInRanking(
            id=row.id,
            score=row.score,
            rank=row.rank,
            current_education=CurrentEducationForRanking(
                level_id=row.level_id,
                institution_id=row.institution_id,
                course_id=row.course_id,
                stage_id=row.stage_id,
            )
            if row.level_id is not None
            else None,
            username=row.username,
        )
        for row in results
    ]
