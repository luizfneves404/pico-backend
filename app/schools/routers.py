import logging

from deps import DBSessionDep
from fastapi import APIRouter, HTTPException, status
from schools import service as school_service
from schools.schemas import SchoolIn, SchoolOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/schools", tags=["schools"])


@router.post("", response_model=SchoolOut, status_code=status.HTTP_201_CREATED)
async def create_school(db_session: DBSessionDep, school_in: SchoolIn):
    new_school = await school_service.create_school(
        db_session,
        school_in.name,
    )
    return new_school


@router.get("", response_model=list[SchoolOut])
async def list_schools(db_session: DBSessionDep):
    schools = await school_service.list_schools(db_session)
    return schools


@router.get("/{school_id}/detail", response_model=SchoolOut)
async def get_school_detail(db_session: DBSessionDep, school_id: int):
    try:
        school = await school_service.get_school(db_session, school_id)
        return school
    except school_service.SchoolNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="School not found"
        )
