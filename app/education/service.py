from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.education.models import (
    College,
    Course,
    Education,
    EducationLevel,
    Institution,
    School,
)


class SchoolNotFoundError(Exception):
    pass


class InstitutionNotFoundError(Exception):
    pass


class CourseNotFoundError(Exception):
    pass


class EducationNotFoundError(Exception):
    pass


async def list_schools(db_session: AsyncSession) -> list[School]:
    """List all schools.

    Args:
        db_session: The database session

    Returns:
        List of all schools
    """
    result = await db_session.scalars(select(School))
    return list(result.all())


async def create_school(
    db_session: AsyncSession,
    *,
    name: str,
    inep_code: str,
    user_submitted: bool,
) -> School:
    """Create a new school.

    Args:
        db_session: The database session
        name: Name of the school to create
        inep_code: INEP code for the school

    Returns:
        The created school
    """
    school = School(
        name=name,
        inep_code=inep_code,
        institution_type="school",
        user_submitted=user_submitted,
    )
    db_session.add(school)
    await db_session.flush()
    await db_session.refresh(school)
    return school


async def list_schools_ranking(db_session: AsyncSession) -> list[School]:
    """List schools ordered by score.

    Args:
        db_session: The database session

    Returns:
        List of schools ordered by score descending
    """
    # TODO: Add score attribute to School model
    result = await db_session.scalars(select(School).order_by(School.name))
    return list(result.all())


async def get_school(db_session: AsyncSession, school_id: int) -> School:
    """Get a school by ID.

    Args:
        db_session: The database session
        school_id: ID of the school to get

    Returns:
        The found school

    Raises:
        SchoolNotFoundError: If no school is found with the given ID
    """
    school = await db_session.get(School, school_id)
    if not school:
        raise SchoolNotFoundError
    return school


async def list_institutions(db_session: AsyncSession) -> list[Institution]:
    """List all institutions.

    Args:
        db_session: The database session

    Returns:
        List of all institutions
    """
    result = await db_session.scalars(select(Institution))
    return list(result.all())


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
    institution = await db_session.get(Institution, institution_id)
    if not institution:
        raise InstitutionNotFoundError
    return institution


async def list_colleges(db_session: AsyncSession) -> list[College]:
    """List all colleges.

    Args:
        db_session: The database session

    Returns:
        List of all colleges
    """
    result = await db_session.scalars(
        select(College).options(selectinload(College.courses))
    )
    return list(result.all())


async def create_college(
    db_session: AsyncSession, *, name: str, user_submitted: bool
) -> College:
    """Create a new college.

    Args:
        db_session: The database session
        name: Name of the college to create

    Returns:
        The created college
    """
    college = College(
        name=name, institution_type="college", user_submitted=user_submitted
    )
    db_session.add(college)
    await db_session.flush()
    await db_session.refresh(college)
    return college


async def get_college(db_session: AsyncSession, college_id: int) -> College:
    """Get a college by ID.

    Args:
        db_session: The database session
        college_id: ID of the college to get

    Returns:
        The found college

    Raises:
        InstitutionNotFoundError: If no college is found with the given ID
    """
    college = await db_session.get(College, college_id)
    if not college:
        raise InstitutionNotFoundError
    return college


async def list_courses(db_session: AsyncSession) -> list[Course]:
    """List all courses.

    Args:
        db_session: The database session

    Returns:
        List of all courses
    """
    result = await db_session.scalars(select(Course))
    return list(result.all())


async def create_course(
    db_session: AsyncSession, *, name: str, user_submitted: bool
) -> Course:
    """Create a new course.

    Args:
        db_session: The database session
        name: Name of the course to create

    Returns:
        The created course
    """
    course = Course(name=name, user_submitted=user_submitted)
    db_session.add(course)
    await db_session.flush()
    await db_session.refresh(course)
    return course


async def get_course(db_session: AsyncSession, course_id: int) -> Course:
    """Get a course by ID.

    Args:
        db_session: The database session
        course_id: ID of the course to get

    Returns:
        The found course

    Raises:
        CourseNotFoundError: If no course is found with the given ID
    """
    course = await db_session.get(Course, course_id)
    if not course:
        raise CourseNotFoundError
    return course


async def create_education(
    db_session: AsyncSession,
    *,
    level: EducationLevel = EducationLevel.UNKNOWN,
    institution_id: int | None = None,
    course_id: int | None = None,
) -> Education:
    """Create a new education record.

    Args:
        db_session: The database session
        level: The education level
        institution_id: ID of the institution
        course_id: ID of the course

    Returns:
        The created education record
    """
    education = Education(
        level=level,
        institution_id=institution_id,
        course_id=course_id,
    )
    db_session.add(education)
    await db_session.flush()
    await db_session.refresh(education)
    return education


async def update_education(
    db_session: AsyncSession,
    education: Education,
    *,
    level: EducationLevel | None = None,
    institution_id: int | None = None,
    course_id: int | None = None,
) -> Education:
    """Update an education record.

    Args:
        db_session: The database session
        education: The education record to update
        level: The new education level
        institution_id: The new institution ID
        course_id: The new course ID

    Returns:
        The updated education record
    """
    if level is not None:
        education.level = level
    if institution_id is not None:
        education.institution_id = institution_id
    if course_id is not None:
        education.course_id = course_id

    await db_session.flush()
    await db_session.refresh(education)
    return education


async def get_education(db_session: AsyncSession, education_id: int) -> Education:
    """Get an education record by ID.

    Args:
        db_session: The database session
        education_id: ID of the education record to get

    Returns:
        The found education record

    Raises:
        EducationNotFoundError: If no education record is found with the given ID
    """
    education = await db_session.get(Education, education_id)
    if not education:
        raise EducationNotFoundError
    return education
