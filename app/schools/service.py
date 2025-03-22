from schools.models import School
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class SchoolNotFoundError(Exception):
    pass


async def list_schools(db_session: AsyncSession):
    """List all schools.

    Args:
        db_session (AsyncSession): The database session

    Returns:
        list[School]: List of all schools
    """
    result = await db_session.scalars(select(School))
    return list(result.all())


async def create_school(db_session: AsyncSession, name: str):
    """Create a new school.

    Args:
        db_session (AsyncSession): The database session
        name (str): Name of the school to create

    Returns:
        School: The created school
    """
    school = School(name=name)
    db_session.add(school)
    await db_session.flush()
    await db_session.refresh(school)
    return school


async def list_schools_ranking(db_session: AsyncSession):
    """List schools ordered by score.

    Args:
        db_session (AsyncSession): The database session

    Returns:
        list[School]: List of schools ordered by score descending
    """
    result = await db_session.scalars(select(School).order_by(School.score.desc()))
    return list(result.all())


async def get_school(db_session: AsyncSession, school_id: int):
    """Get a school by ID.

    Args:
        db_session (AsyncSession): The database session
        school_id (int): ID of the school to get

    Returns:
        School: The found school

    Raises:
        SchoolNotFoundError: If no school is found with the given ID
    """
    school = await db_session.get(School, school_id)
    if not school:
        raise SchoolNotFoundError
    return school
