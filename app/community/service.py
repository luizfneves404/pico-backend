from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.community.models import Community, CommunityUser
from app.education.models import Education, EducationLevel
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
    db_session: AsyncSession, *, education: Education
) -> Community:
    """Find or create a community based on education information.

    Args:
        db_session: Database session
        education: Education information to base community on

    Returns:
        Community if education information is available, None otherwise
    """
    # Generate community name and subtitle based on education
    community_name = _generate_community_name(education)
    community_subtitle = _generate_community_subtitle(education)

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

    Raises:
        IntegrityError: If relationship already exists
    """
    try:
        community_user = CommunityUser(user_id=user_id, community_id=community_id)
        db_session.add(community_user)
        await db_session.flush()
    except IntegrityError as e:
        print("i found an error", e)
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
    db_session: AsyncSession, *, user: User
) -> Community | None:
    """Join communities based on user's education information.

    Args:
        db_session: Database session
        user: User to join communities for

    Returns:
        Community the user was added to
    """

    # Process current education
    print("user.current_education", user.current_education)
    if user.current_education:
        community = await find_or_create_education_community(
            db_session, education=user.current_education
        )
        await clear_user_from_all_communities(db_session, user_id=user.id)
        await add_user_to_community_if_not_exists(
            db_session, user_id=user.id, community_id=community.id
        )
    else:
        await clear_user_from_all_communities(db_session, user_id=user.id)
        community = None

    return community


def _generate_community_name(education: Education) -> str:
    """Generate a community name based on education information.

    Args:
        education: Education information

    Returns:
        Generated community name
    """
    if not education.institution:
        return f"Estudantes de {_get_education_level_display_name(education.level)}"

    institution_name = education.institution.name

    return institution_name


def _generate_community_subtitle(education: Education) -> str:
    """Generate a community subtitle based on education information.

    Args:
        education: Education information

    Returns:
        Generated community subtitle
    """
    if not education.course:
        return _get_education_level_display_name(education.level)

    return education.course.name


def _get_education_level_display_name(level: EducationLevel) -> str:
    """Get a display-friendly name for an education level.

    Args:
        level: Education level enum

    Returns:
        Display name for the level
    """
    level_names = {
        EducationLevel.MIDDLE_SCHOOL: "Ensino Fundamental",
        EducationLevel.FIRST_GRADE_HIGH_SCHOOL: "1° Ano do Ensino Médio",
        EducationLevel.SECOND_GRADE_HIGH_SCHOOL: "2° Ano do Ensino Médio",
        EducationLevel.THIRD_GRADE_HIGH_SCHOOL: "3° Ano do Ensino Médio",
        EducationLevel.HIGH_SCHOOL_COMPLETE: "Ensino Médio Completo",
        EducationLevel.COLLEGE: "Ensino Superior",
        EducationLevel.OTHER: "Estudante",
        EducationLevel.UNKNOWN: "Estudante",
    }
    return level_names.get(level, "Estudante")
