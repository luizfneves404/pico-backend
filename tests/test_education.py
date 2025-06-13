"""
Tests for the education system endpoints.

This file contains tests for the education API endpoints:
- Education levels
- Institutions (schools, colleges)
- Courses
"""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.education.models import EducationLevel
from app.education.service import create_course, create_institution


async def test_list_levels(
    client: AsyncClient, session: AsyncSession, education_level: EducationLevel
) -> None:
    """Test listing education levels."""
    response = await client.get("/api/education/levels")
    assert response.status_code == 200
    levels = response.json()
    assert len(levels) >= 1

    # Find our created level
    level_names = [level["name_i18n"] for level in levels]
    assert education_level.name_i18n in level_names


async def test_list_levels_with_country_filter(
    client: AsyncClient, session: AsyncSession, education_level: EducationLevel
) -> None:
    """Test listing education levels with country filter."""
    response = await client.get("/api/education/levels?country_code=BR")
    assert response.status_code == 200
    levels = response.json()
    # Should still return levels (stages might be filtered by country)
    assert isinstance(levels, list)


async def test_list_courses(
    client: AsyncClient, session: AsyncSession, education_level: EducationLevel
) -> None:
    """Test listing courses."""
    # Create a course using the service layer
    async with session.begin():
        await create_course(
            session,
            name_i18n={"en": "Computer Science"},
            user_submitted=False,
            level_id=education_level.id,
        )

    # Get list of courses
    response = await client.get("/api/education/courses")
    assert response.status_code == 200
    courses = response.json()
    assert len(courses) >= 1

    course_names = [course["name_i18n"] for course in courses]
    assert {"en": "Computer Science"} in course_names


async def test_list_courses_with_level_filter(
    client: AsyncClient, session: AsyncSession, education_level: EducationLevel
) -> None:
    """Test listing courses filtered by level."""
    # Create a course using the service layer
    async with session.begin():
        course = await create_course(
            session,
            name_i18n={"en": "Mathematics"},
            user_submitted=False,
            level_id=education_level.id,
        )

    # Get list of courses filtered by level
    response = await client.get(f"/api/education/courses?level_id={education_level.id}")
    assert response.status_code == 200
    courses = response.json()

    # All returned courses should have the specified level_id
    for course in courses:
        assert course["level_id"] == education_level.id


async def test_get_course_detail(
    client: AsyncClient, session: AsyncSession, education_level: EducationLevel
) -> None:
    """Test getting course details."""
    # Create a course using the service layer
    async with session.begin():
        course = await create_course(
            session,
            name_i18n={"en": "Physics"},
            user_submitted=False,
            level_id=education_level.id,
        )

    # Get course details using the endpoint
    response = await client.get(f"/api/education/courses/{course.id}")
    assert response.status_code == 200
    course_data = response.json()
    assert course_data["id"] == course.id
    assert course_data["name_i18n"] == {"en": "Physics"}
    assert course_data["level_id"] == education_level.id


async def test_get_course_detail_not_found(client: AsyncClient) -> None:
    """Test getting details of a non-existent course."""
    response = await client.get("/api/education/courses/9999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Course not found"


async def test_create_institution(
    client: AsyncClient, education_level: EducationLevel
) -> None:
    """Test creating an institution via the API."""
    response = await client.post(
        "/api/education/institutions/create",
        json={
            "name": "Test University",
            "institution_type": "college",
            "country_code": "BR",
            "level_id": education_level.id,
        },
    )
    assert response.status_code == 200
    institution_data = response.json()
    assert institution_data["name"] == "Test University"
    assert institution_data["institution_type"] == "college"
    assert institution_data["country_code"] == "BR"


async def test_create_institution_invalid_data(client: AsyncClient) -> None:
    """Test creating an institution with invalid data."""
    response = await client.post(
        "/api/education/institutions/create",
        json={
            "name": "",  # Invalid empty name
            "institution_type": "college",
            "country_code": "BR",
            "level_id": 1,
        },
    )
    assert response.status_code == 422


async def test_search_institutions_by_name(
    client: AsyncClient, session: AsyncSession, education_level: EducationLevel
) -> None:
    """Test searching institutions by name."""
    # Create an institution using the service layer
    async with session.begin():
        await create_institution(
            session,
            name="MIT",
            institution_type="college",
            country_code="US",
            user_submitted=False,
            level_id=education_level.id,
        )

    # Search for institutions
    response = await client.post(
        "/api/education/institutions/search",
        json={
            "name": "MIT",
            "institution_type": "college",
        },
    )
    assert response.status_code == 200
    institutions = response.json()
    assert len(institutions) >= 1

    institution_names = [inst["name"] for inst in institutions]
    assert "MIT" in institution_names


async def test_search_institutions_by_type(
    client: AsyncClient, session: AsyncSession, education_level: EducationLevel
) -> None:
    """Test searching institutions by type."""
    # Create institutions of different types
    async with session.begin():
        await create_institution(
            session,
            name="Harvard School",
            institution_type="school",
            country_code="US",
            user_submitted=False,
            level_id=education_level.id,
        )
        await create_institution(
            session,
            name="Harvard University",
            institution_type="college",
            country_code="US",
            user_submitted=False,
            level_id=education_level.id,
        )

    # Search for schools only
    response = await client.post(
        "/api/education/institutions/search",
        json={
            "institution_type": "school",
        },
    )
    assert response.status_code == 200
    institutions = response.json()

    # All returned institutions should be schools
    for institution in institutions:
        assert institution["institution_type"] == "school"


async def test_search_institutions_with_location(
    client: AsyncClient, session: AsyncSession, education_level: EducationLevel
) -> None:
    """Test searching institutions with location filter."""
    # Create an institution
    async with session.begin():
        await create_institution(
            session,
            name="Local University",
            institution_type="college",
            country_code="BR",
            user_submitted=False,
            level_id=education_level.id,
        )

    # Search with location (São Paulo coordinates)
    response = await client.post(
        "/api/education/institutions/search",
        json={
            "institution_type": "college",
            "location": {
                "latitude": -23.5505,
                "longitude": -46.6333,
            },
        },
    )
    assert response.status_code == 200
    institutions = response.json()
    assert isinstance(institutions, list)


async def test_get_institution_detail(
    client: AsyncClient, session: AsyncSession, education_level: EducationLevel
) -> None:
    """Test getting institution details."""
    # Create an institution using the service layer
    async with session.begin():
        institution = await create_institution(
            session,
            name="Test College",
            institution_type="college",
            country_code="BR",
            user_submitted=False,
            level_id=education_level.id,
        )

    # Get institution details using the endpoint
    response = await client.get(f"/api/education/institutions/{institution.id}")
    assert response.status_code == 200
    institution_data = response.json()
    assert institution_data["id"] == institution.id
    assert institution_data["name"] == "Test College"
    assert institution_data["institution_type"] == "college"
    assert institution_data["country_code"] == "BR"


async def test_get_institution_detail_not_found(client: AsyncClient) -> None:
    """Test getting details of a non-existent institution."""
    response = await client.get("/api/education/institutions/9999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Institution not found"


async def test_search_institutions_empty_results(client: AsyncClient) -> None:
    """Test searching for institutions with no matches."""
    response = await client.post(
        "/api/education/institutions/search",
        json={
            "name": "NonExistentUniversity",
            "institution_type": "college",
        },
    )
    assert response.status_code == 200
    institutions = response.json()
    assert institutions == []


async def test_search_institutions_invalid_type(client: AsyncClient) -> None:
    """Test searching institutions with invalid institution type."""
    response = await client.post(
        "/api/education/institutions/search",
        json={
            "institution_type": "invalid_type",
        },
    )
    assert response.status_code == 422
