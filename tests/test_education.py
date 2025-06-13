"""
Tests for the education system (institutions, courses).

This file contains tests for the education API endpoints:
- Schools and colleges (both are institutions with different types)
- Courses
"""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.education.models import EducationLevel
from app.education.service import create_course, create_institution


# School tests
async def test_list_schools(
    client: AsyncClient, session: AsyncSession, education_level: EducationLevel
) -> None:
    """Test listing schools using the education API."""
    # Create two schools using the service layer

    async with session.begin():
        await create_institution(
            session,
            institution_type="school",
            country_code="BR",
            name="School 1",
            user_submitted=False,
            level_id=education_level.id,
        )
        await create_institution(
            session,
            institution_type="school",
            country_code="BR",
            name="School 2",
            user_submitted=False,
            level_id=education_level.id,
        )

    # Get list of schools using the endpoint
    response = await client.get("/api/education/schools")
    assert response.status_code == 200
    schools = response.json()
    assert len(schools) >= 2

    # Find our created schools
    school_names = [school["name"] for school in schools]
    assert "School 1" in school_names
    assert "School 2" in school_names


async def test_get_school_detail(
    client: AsyncClient, session: AsyncSession, education_level: EducationLevel
) -> None:
    """Test getting school details using the education API."""
    # Create a school using the service layer
    async with session.begin():
        school = await create_institution(
            session,
            institution_type="school",
            country_code="BR",
            name="Test School",
            user_submitted=False,
            level_id=education_level.id,
        )

    # Get school details using the endpoint
    response = await client.get(f"/api/education/schools/{school.id}")
    assert response.status_code == 200
    school_data = response.json()
    assert school_data["id"] == school.id
    assert school_data["name"] == "Test School"
    assert school_data["institution_type"] == "school"
    assert school_data["user_submitted"] is False


async def test_get_school_detail_not_found(client: AsyncClient) -> None:
    """Test getting details of a non-existent school."""
    response = await client.get("/api/education/schools/9999")
    assert response.status_code == 404


async def test_create_school(client: AsyncClient) -> None:
    """Test creating a school via the API."""
    response = await client.post(
        "/api/education/schools",
        json={"name": "New School", "user_submitted": False},
    )
    assert response.status_code == 201
    school_data = response.json()
    assert school_data["name"] == "New School"
    assert school_data["institution_type"] == "school"
    assert (
        school_data["user_submitted"] is True
    )  # should still be true because its user endpoint

    # Verify that the school exists by listing all schools
    list_response = await client.get("/api/education/schools")
    assert list_response.status_code == 200
    schools = list_response.json()
    school_names = [school["name"] for school in schools]
    assert "New School" in school_names


async def test_create_school_invalid(client: AsyncClient) -> None:
    """Test creating a school with invalid data."""
    response = await client.post("/api/education/schools", json={"name": ""})
    assert response.status_code == 422


# College tests
async def test_list_colleges(
    client: AsyncClient, session: AsyncSession, education_level: EducationLevel
) -> None:
    """Test listing colleges using the education API."""
    # Create a college using the service layer
    async with session.begin():
        await create_institution(
            session,
            institution_type="college",
            country_code="BR",
            name="Test College",
            user_submitted=False,
            level_id=education_level.id,
        )

    # Get list of colleges
    response = await client.get("/api/education/colleges")
    assert response.status_code == 200
    colleges = response.json()
    college_names = [college["name"] for college in colleges]
    assert "Test College" in college_names
    assert colleges[0]["user_submitted"] is False


async def test_create_college(client: AsyncClient) -> None:
    """Test creating a college via the API."""
    response = await client.post("/api/education/colleges", json={"name": "MIT"})
    assert response.status_code == 201
    college_data = response.json()
    assert college_data["name"] == "MIT"
    assert college_data["institution_type"] == "college"
    assert college_data["user_submitted"] is True


# Course tests
async def test_list_courses(client: AsyncClient, session: AsyncSession) -> None:
    """Test listing courses using the education API."""
    # Create a course using the service layer
    async with session.begin():
        await create_course(session, name="Computer Science", user_submitted=False)

    # Get list of courses
    response = await client.get("/api/education/courses")
    assert response.status_code == 200
    courses = response.json()
    course_names = [course["name"] for course in courses]
    assert "Computer Science" in course_names


async def test_create_course(client: AsyncClient) -> None:
    """Test creating a course via the API."""
    response = await client.post(
        "/api/education/courses", json={"name": "Data Science"}
    )
    assert response.status_code == 201
    course_data = response.json()
    assert course_data["name"] == "Data Science"
    assert course_data["user_submitted"] is True


# Institution tests (unified view)
async def test_list_institutions(
    client: AsyncClient, session: AsyncSession, education_level: EducationLevel
) -> None:
    """Test listing all institutions (both schools and colleges)."""
    # Create both a school and a college
    async with session.begin():
        await create_institution(
            session,
            name="Test School for Institutions",
            institution_type="school",
            country_code="BR",
            user_submitted=False,
            level_id=education_level.id,
        )
        await create_institution(
            session,
            name="Test College for Institutions",
            institution_type="college",
            country_code="BR",
            user_submitted=False,
            level_id=education_level.id,
        )

    # Get list of all institutions
    response = await client.get("/api/education/institutions")
    assert response.status_code == 200
    institutions = response.json()

    institution_names = [inst["name"] for inst in institutions]
    assert "Test School for Institutions" in institution_names
    assert "Test College for Institutions" in institution_names
    assert institutions[0]["user_submitted"] is False
    assert institutions[1]["user_submitted"] is False

    # Verify that we have both types
    types = [inst["institution_type"] for inst in institutions]
    assert "school" in types
    assert "college" in types
