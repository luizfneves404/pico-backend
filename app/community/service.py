from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.community.models import Community, CommunityUser
from app.education.models import Course, Institution, LevelStage
from app.users.models import User


async def get_user_communities(
    db_session: AsyncSession, *, user_id: int
) -> list[Community]:
    communities = (
        (
            await db_session.execute(
                select(Community)
                .join(CommunityUser)
                .where(CommunityUser.user_id == user_id)
            )
        )
        .scalars()
        .all()
    )
    return list(communities)


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
    db_session: AsyncSession, *, user_id: int, community_id: int
) -> CommunityUser | None:
    """Add a user to a community.

    Args:
        db_session: Database session
        user_id: ID of the user to add
        community_id: ID of the community to add user to

    Returns:
        Created CommunityUser relationship
    """
    try:
        community_user = CommunityUser(user_id=user_id, community_id=community_id)
        db_session.add(community_user)
        await db_session.flush()
    except IntegrityError as e:
        if "duplicate key value violates unique constraint" in str(e):
            return None
        raise

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
        user_id=user.id,
        community_id=community.id,
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
        return str(course.name)
    if stage:
        return stage.name

    raise ValueError("Either course or stage is required")
