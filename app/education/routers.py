import logging

from fastapi import APIRouter, HTTPException, status

logger = logging.getLogger(__name__)

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
    # Log what the frontend sent
    logger.info(f"Frontend requested education levels with country_code='{country_code}'")
    
    levels = await education_service.list_levels(db_session, country_code=country_code)
    
    # Log what we're returning
    logger.info(f"Returning {len(levels)} education levels to frontend")
    for level in levels:
        stage_count = len(level.stages) if hasattr(level, 'stages') else 0
        course_count = len(level.courses) if hasattr(level, 'courses') else 0
        level_name = level.name_i18n.get('en', 'Unknown') if level.name_i18n else 'Unknown'
        logger.info(f"Level '{level_name}': {stage_count} stages, {course_count} courses")
    
    return [EducationLevelOut.from_orm_model(level) for level in levels]


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
        level_id=institution_in.level_id,
    )
    return InstitutionOut.from_orm_model(new_institution)


@router.post("/institutions/search", response_model=list[InstitutionOut])
async def search_institutions(
    db_session: DBSessionAnnotated, search_institutions: SearchInstitutionsRequest
) -> list[InstitutionOut]:
    # Log what the frontend sent
    logger.info(f"Frontend search request: name='{search_institutions.name}', education_level_id={search_institutions.education_level_id}, location={search_institutions.location}")
    
    institutions = await education_service.search_institutions(
        db_session,
        name=search_institutions.name,
        education_level_id=search_institutions.education_level_id,
        latitude=search_institutions.location.latitude
        if search_institutions.location
        else None,
        longitude=search_institutions.location.longitude
        if search_institutions.location
        else None,
    )
    
    # Log what we're returning
    logger.info(f"Returning {len(institutions)} institutions to frontend")
    if institutions:
        logger.info(f"First institution: {institutions[0].name}")
    
    return [InstitutionOut.from_orm_model(institution) for institution in institutions]


@router.get("/institutions/{institution_id}", response_model=InstitutionOut)
async def get_institution_detail(
    db_session: DBSessionAnnotated, institution_id: int
) -> InstitutionOut:
    try:
        institution = await education_service.get_institution(
            db_session, institution_id
        )
        return InstitutionOut.from_orm_model(institution)
    except education_service.InstitutionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Institution not found"
        )
