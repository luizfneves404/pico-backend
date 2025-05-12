import logging

import api.services.school_service as school_service
from api.schemas.schools import SchoolIn, SchoolInRanking, SchoolOut
from asgiref.sync import sync_to_async
from ninja import Router
from ninja.errors import HttpError

logger = logging.getLogger(__name__)

router = Router()


@router.post("", response={201: SchoolOut}, auth=None, url_name="school_create")
async def school_create(request, school_in: SchoolIn):
    new_school = await school_service.create_school(
        school_in.name,
    )
    return 201, new_school


@router.get("", response=list[SchoolOut], auth=None, url_name="school_list")
async def school_list(request):
    schools = await school_service.list_schools()
    return schools


@router.get(
    "/{school_id}/detail",
    response=SchoolOut,
    auth=None,
    url_name="school_detail",
)
async def school_detail(request, school_id: int):
    try:
        school = await school_service.get_school(school_id)
        return school
    except school_service.SchoolNotFoundError:
        raise HttpError(404, "School not found")


@router.get(
    "/ranking",
    response=list[SchoolInRanking],
    url_name="school_ranking",
    summary="Get a ranking of all of the schools by summing up the dynamic_score of all of the users in the school",
)
async def school_ranking(request):
    schools = await sync_to_async(school_service.get_school_ranking)()
    return schools
