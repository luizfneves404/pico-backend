import logging

from fastapi import APIRouter, HTTPException, status

from app.deps import DBSessionAnnotated
from app.education import service as education_service
from app.education.schemas import (
    CourseOut,
    EducationLevelOut,
    InstitutionIn,
    InstitutionOut,
    SearchInstitutionsRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/education", tags=["education"])


@router.get("/levels", response_model=list[EducationLevelOut])
async def list_levels(
    db_session: DBSessionAnnotated, country_code: str | None = None
) -> list[EducationLevelOut]:
    levels = await education_service.list_levels(db_session, country_code=country_code)
    return [EducationLevelOut.from_orm_model(level) for level in levels]


@router.get("/courses", response_model=list[CourseOut])
async def list_courses(
    db_session: DBSessionAnnotated,
    level_id: int | None = None,
) -> list[CourseOut]:
    courses = await education_service.list_courses(db_session, level_id=level_id)
    return [CourseOut.from_orm_model(course) for course in courses]


@router.get("/courses/{id}", response_model=CourseOut)
async def get_course_detail(db_session: DBSessionAnnotated, id: int) -> CourseOut:
    try:
        course = await education_service.get_course(db_session, id=id)
        return CourseOut.from_orm_model(course)
    except education_service.CourseNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Course not found"
        )


@router.post("/institutions/create", response_model=InstitutionOut)
async def create_institution(
    db_session: DBSessionAnnotated, institution_in: InstitutionIn
) -> InstitutionOut:
    new_institution = await education_service.create_institution(
        db_session,
        name=institution_in.name,
        institution_type=institution_in.institution_type,
        user_submitted=True,
        country_code=institution_in.country_code,
    )
    return InstitutionOut.from_orm_model(new_institution)


@router.post("/institutions/search", response_model=list[InstitutionOut])
async def search_institutions(
    db_session: DBSessionAnnotated, search_institutions: SearchInstitutionsRequest
) -> list[InstitutionOut]:
    institutions = await education_service.search_institutions(
        db_session,
        name=search_institutions.name,
        institution_type=search_institutions.institution_type,
        latitude=search_institutions.location.latitude
        if search_institutions.location
        else None,
        longitude=search_institutions.location.longitude
        if search_institutions.location
        else None,
    )
    return [InstitutionOut.from_orm_model(institution) for institution in institutions]


@router.get("/institutions/{institution_id}", response_model=InstitutionOut)
async def get_institution_detail(db_session: DBSessionAnnotated, institution_id: int):
    try:
        institution = await education_service.get_institution(
            db_session, institution_id
        )
        return institution
    except education_service.InstitutionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Institution not found"
        )
