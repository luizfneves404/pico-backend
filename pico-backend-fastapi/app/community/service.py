import logging
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import delete, func, join, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.community.models import Community, CommunityUser
from app.education.models import Course, Institution, LevelStage
from app.notifications.service import notify_community_user_joined
from app.users.models import User

logger = logging.getLogger(__name__)

NUM_RANKED_USERS = 10


async def get_user_communities(
    db_session: AsyncSession, *, user_id: int
) -> list[Community]:
    stmt = (
        select(Community)
        .where(Community.users.any(id=user_id))
        .options(selectinload(Community.users))
    )

    result = await db_session.scalars(stmt)
    return list(result)


async def find_or_create_education_community(
    db_session: AsyncSession,
    *,
    institution: Institution,
    course: Course | None,
    stage: LevelStage | None,
) -> Community:
    """Find or create a community based on education information.

    Args:
        db_session: Database session
        education: Education information to base community on

    Returns:
        Community if education information is available, None otherwise
    """
    # Generate community name and subtitle based on education
    community_name = _generate_community_name(institution)
    community_subtitle = _generate_community_subtitle(course, stage)

    # Try to find existing community
    result = await db_session.execute(
        select(Community).where(
            Community.name == community_name,
            Community.subtitle == community_subtitle,
        )
    )
    existing_community = result.scalar_one_or_none()

    if existing_community:
        return existing_community

    # Create new community
    new_community = Community(name=community_name, subtitle=community_subtitle)
    db_session.add(new_community)
    await db_session.flush()

    return new_community


async def add_user_to_community_if_not_exists(
    db_session: AsyncSession, *, user: User, community: Community
) -> CommunityUser | None:
    """Add a user to a community.

    Args:
        db_session: Database session
        user: User to add to community
        community: Community to add user to

    Returns:
        Created CommunityUser relationship
    """
    try:
        community_user = CommunityUser(user_id=user.id, community_id=community.id)
        db_session.add(community_user)
        await db_session.flush()
    except IntegrityError as e:
        if "duplicate key value violates unique constraint" in str(e):
            logger.debug(
                f"User {user.id} already in community {community.id}",
            )
            return None
        raise
    else:
        logger.debug(
            f"User {user.id} added to community {community.id}",
        )
        await notify_community_user_joined(
            db_session,
            user=user,
            community=community,
        )

    return community_user


async def clear_user_from_all_communities(
    db_session: AsyncSession, *, user_id: int
) -> None:
    await db_session.execute(
        delete(CommunityUser).where(CommunityUser.user_id == user_id)
    )


async def change_user_education_community(
    db_session: AsyncSession,
    *,
    user: User,
    institution: Institution,
    course: Course | None,
    stage: LevelStage | None,
) -> Community | None:
    """Join communities based on user's education information.

    Args:
        db_session: Database session
        user: User to join communities for

    Returns:
        Community the user was added to if successful, None if the user was already in the community
    """
    community = await find_or_create_education_community(
        db_session,
        institution=institution,
        course=course,
        stage=stage,
    )
    await clear_user_from_all_communities(db_session, user_id=user.id)
    community_user = await add_user_to_community_if_not_exists(
        db_session,
        user=user,
        community=community,
    )
    if community_user:
        return community
    else:
        return None


def _generate_community_name(institution: Institution) -> str:
    """Generate a community name based on education information.

    Args:
        institution: Institution

    Returns:
        Generated community name
    """

    institution_name = institution.name

    return institution_name


def _generate_community_subtitle(
    course: Course | None, stage: LevelStage | None
) -> str:
    """Generate a community subtitle based on education information.

    Args:
        course: Course
        stage: Stage

    Returns:
        Generated community subtitle
    """
    if course:
        return course.name_i18n["en"]  # TODO: needs to adjust to language of user
    if stage:
        return stage.name

    raise ValueError("Either course or stage is required")


@dataclass(frozen=True, slots=True, kw_only=True)
class UserInCommunityRanking:
    id: int
    score: int
    rank: int
    username: str
    name: str


async def get_community_ranking(
    db_session: AsyncSession,
    *,
    asking_user_id: int,
    community_id: int,
    score_type: Literal["xp", "social"],
) -> list[UserInCommunityRanking]:
    """
    Gets the community ranking, ensuring a max of 11 results:
    - The top 10 users by score (ties are cut off after the 10th position).
    - The asking user, if they are not within the top 10.
    """
    score_column = User.xp_score if score_type == "xp" else User.social_score

    ranked_users_cte = (
        select(
            User.id,
            User.username,
            User.name,
            score_column.label("score"),
            func.dense_rank().over(order_by=score_column.desc()).label("rank"),
        )
        .select_from(join(User, CommunityUser, User.id == CommunityUser.user_id))
        .where(CommunityUser.community_id == community_id)
        .cte("ranked_users")
    )

    top_10_query = (
        select(
            ranked_users_cte.c.id,
            ranked_users_cte.c.username,
            ranked_users_cte.c.name,
            ranked_users_cte.c.score,
            ranked_users_cte.c.rank,
        )
        .order_by(ranked_users_cte.c.rank)
        .limit(NUM_RANKED_USERS)
    )

    asking_user_query = select(
        ranked_users_cte.c.id,
        ranked_users_cte.c.username,
        ranked_users_cte.c.name,
        ranked_users_cte.c.score,
        ranked_users_cte.c.rank,
    ).where(ranked_users_cte.c.id == asking_user_id)

    final_union = top_10_query.union(asking_user_query)

    union_subquery = final_union.subquery()

    stmt = select(union_subquery).order_by(union_subquery.c.rank)

    results = await db_session.execute(stmt)

    return [
        UserInCommunityRanking(
            id=row["id"],
            score=row["score"],
            rank=row["rank"],
            username=row["username"],
            name=row["name"],
        )
        for row in results.mappings()
    ]
