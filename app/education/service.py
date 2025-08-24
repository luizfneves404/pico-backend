from geoalchemy2 import WKTElement
from geoalchemy2.functions import ST_Distance
from geoalchemy2.types import Geography
from sqlalchemy import ColumnElement, case, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload, with_loader_criteria

from app.countries.models import Country
from app.countries.service import CountryNotFound, get_country
from app.education.models import (
    AdministrativeCategory,
    Course,
    EducationInfo,
    EducationLevel,
    Institution,
    InstitutionType,
    LevelStage,
)

MAX_DISTANCE_INSTITUTION_SEARCH = 10_000
MAX_INSTITUTIONS_SEARCH_LIMIT = 50


class InstitutionNotFoundError(Exception):
    pass


class CourseNotFoundError(Exception):
    pass


class StageNotFoundError(Exception):
    pass


class LevelNotFoundError(Exception):
    pass


class InvalidInstitutionTypeError(Exception):
    pass


class CountryNotFoundError(Exception):
    pass


async def list_institutions(db_session: AsyncSession) -> list[Institution]:
    """List all institutions.

    Args:
        db_session: The database session

    Returns:
        List of all institutions
    """
    result = await db_session.scalars(select(Institution))
    return list(result)


async def get_institution(db_session: AsyncSession, institution_id: int) -> Institution:
    """Get an institution by ID.

    Args:
        db_session: The database session
        institution_id: ID of the institution to get

    Returns:
        The found institution

    Raises:
        InstitutionNotFoundError: If no institution is found with the given ID
    """
    institution = await db_session.scalar(
        select(Institution)
        .where(Institution.id == institution_id)
        .options(selectinload(Institution.country))
    )
    if not institution:
        raise InstitutionNotFoundError
    return institution


async def search_institutions(
    db: AsyncSession,
    *,
    name: str | None,
    education_level_id: int | None,
    latitude: float | None,
    longitude: float | None,
) -> list[Institution]:
    filters: list[ColumnElement[bool]] = []
    if name:
        filters.append(Institution.name.ilike(f"%{name}%"))
    if education_level_id:
        filters.append(Institution.level_id == education_level_id)

    user_geom = (
        WKTElement(f"POINT({longitude} {latitude})", srid=4326)
        if latitude is not None and longitude is not None
        else None
    )

    stmt = select(Institution)

    if user_geom:
        null_last = case((Institution.location.is_(None), 1), else_=0)

        stmt = stmt.order_by(
            null_last,
            ST_Distance(Institution.location, user_geom, type_=Geography),
        )
    else:
        stmt = stmt.order_by(Institution.name)  # or whatever default you prefer

    stmt = (
        stmt.where(*filters)
        .limit(MAX_INSTITUTIONS_SEARCH_LIMIT)
        .options(selectinload(Institution.country))
    )

    result = await db.execute(stmt)
    return list(result.scalars())


async def create_institution(
    db_session: AsyncSession,
    *,
    name: str,
    institution_type: str,
    user_submitted: bool,
    country_code: str,
    level_id: int,
) -> Institution:
    """Create a new institution.

    Args:
        db_session: The database session
        name: The name of the institution to create
        institution_type: The type of the institution to create
        user_submitted: Whether the institution is user-submitted

    Returns:
        The created institution
    """
    try:
        country = await get_country(db_session, country_code)
    except CountryNotFound:
        raise CountryNotFoundError(f"Country with code {country_code} not found")
    institution = Institution(
        name=name,
        institution_type=InstitutionType(institution_type),
        user_submitted=user_submitted,
        country=country,
        level_id=level_id,
        administrative_category=AdministrativeCategory.UNKNOWN,
    )
    db_session.add(institution)
    try:
        await db_session.flush()
    except IntegrityError as e:
        if "level_id" in str(e):
            raise LevelNotFoundError(e)
        elif "institution_type" in str(e):
            raise InvalidInstitutionTypeError(e)
        raise e
    await db_session.refresh(institution, ["country"])
    return institution


async def list_courses(
    db_session: AsyncSession, *, level_id: int | None
) -> list[Course]:
    """List all courses, limiting courses to the given level.

    Args:
        db_session: The database session
        level_id: The level id to limit the courses to

    Returns:
        List of all courses
    """

    filters: list[ColumnElement[bool]] = []
    if level_id:
        filters.append(Course.level_id == level_id)

    result = await db_session.scalars(select(Course).where(*filters))
    return list(result)


async def create_course(
    db_session: AsyncSession,
    *,
    name_i18n: dict[str, str],
    user_submitted: bool,
    level_id: int,
) -> Course:
    """Create a new course.

    Args:
        db_session: The database session
        name: Name of the course to create
        user_submitted: Whether the course is user-submitted
        level_id: The education level ID for the course

    Returns:
        The created course
    """
    course = Course(
        name_i18n=name_i18n, user_submitted=user_submitted, level_id=level_id
    )
    db_session.add(course)
    await db_session.flush()
    await db_session.refresh(course)
    return course


async def get_course(db_session: AsyncSession, id: int) -> Course:
    """Get a course by ID.

    Args:
        db_session: The database session
        id: ID of the course to get

    Returns:
        The found course

    Raises:
        CourseNotFoundError: If no course is found with the given ID
    """
    course = await db_session.get(Course, id)
    if not course:
        raise CourseNotFoundError
    return course


async def build_education(
    db_session: AsyncSession,
    *,
    level_id: int,
    stage_id: int | None,
    institution_id: int | None,
    course_id: int | None,
) -> EducationInfo:
    """Create a new education record without flushing the session.

    Args:
        db_session: The database session
        level_id: The education level id
        stage_id: ID of the stage
        institution_id: ID of the institution
        course_id: ID of the course

    Returns:
        The created education record
    """
    education = EducationInfo(
        level_id=level_id,
        stage_id=stage_id,
        institution_id=institution_id,
        course_id=course_id,
    )
    db_session.add(education)
    return education


async def list_levels(
    db_session: AsyncSession, *, country_code: str | None
) -> list[EducationLevel]:
    stmt = select(EducationLevel).options(
        joinedload(EducationLevel.stages).joinedload(LevelStage.country),
        selectinload(EducationLevel.courses),
    )

    if country_code:
        stmt = stmt.options(
            with_loader_criteria(
                LevelStage, LevelStage.country.has(Country.code == country_code)
            )
        )

    result = await db_session.execute(stmt)
    return list(result.scalars().unique())
