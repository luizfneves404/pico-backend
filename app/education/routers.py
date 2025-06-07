import logging

from fastapi import APIRouter, HTTPException, status

from app.deps import DBSessionAnnotated
from app.education import service as education_service
from app.education.schemas import (
    CollegeIn,
    CollegeOut,
    CourseIn,
    CourseOut,
    InstitutionOut,
    SchoolIn,
    SchoolOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/education", tags=["education"])


# School endpoints
@router.post("/schools", response_model=SchoolOut, status_code=status.HTTP_201_CREATED)
async def create_school(db_session: DBSessionAnnotated, school_in: SchoolIn):
    new_school = await education_service.create_school(
        db_session,
        name=school_in.name,
        inep_code=school_in.inep_code,
        user_submitted=True,
    )
    return new_school


@router.get("/schools", response_model=list[SchoolOut])
async def list_schools(db_session: DBSessionAnnotated):
    schools = await education_service.list_schools(db_session)
    return schools


@router.get("/schools/{school_id}", response_model=SchoolOut)
async def get_school_detail(db_session: DBSessionAnnotated, school_id: int):
    try:
        school = await education_service.get_school(db_session, school_id)
        return school
    except education_service.SchoolNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="School not found"
        )


# College endpoints
@router.post(
    "/colleges", response_model=CollegeOut, status_code=status.HTTP_201_CREATED
)
async def create_college(db_session: DBSessionAnnotated, college_in: CollegeIn):
    new_college = await education_service.create_college(
        db_session,
        name=college_in.name,
        user_submitted=True,
    )
    return new_college


@router.get("/colleges", response_model=list[CollegeOut])
async def list_colleges(db_session: DBSessionAnnotated):
    colleges = await education_service.list_colleges(db_session)
    return colleges


@router.get("/colleges/{college_id}", response_model=CollegeOut)
async def get_college_detail(db_session: DBSessionAnnotated, college_id: int):
    try:
        college = await education_service.get_college(db_session, college_id)
        return college
    except education_service.InstitutionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="College not found"
        )


# Course endpoints
@router.post("/courses", response_model=CourseOut, status_code=status.HTTP_201_CREATED)
async def create_course(db_session: DBSessionAnnotated, course_in: CourseIn):
    new_course = await education_service.create_course(
        db_session,
        name=course_in.name,
        user_submitted=True,
    )
    return new_course


@router.get("/courses", response_model=list[CourseOut])
async def list_courses(db_session: DBSessionAnnotated):
    courses = await education_service.list_courses(db_session)
    return courses


@router.get("/courses/{course_id}", response_model=CourseOut)
async def get_course_detail(db_session: DBSessionAnnotated, course_id: int):
    try:
        course = await education_service.get_course(db_session, course_id)
        return course
    except education_service.CourseNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Course not found"
        )


# Institution endpoints
@router.get("/institutions", response_model=list[InstitutionOut])
async def list_institutions(db_session: DBSessionAnnotated):
    institutions = await education_service.list_institutions(db_session)
    return institutions


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
