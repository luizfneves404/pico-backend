import logging

import study_plans.study_plan_service as study_plan_service
from ninja import Router
from study_plans.schemas.study_plan import StudyPlanIn, StudyPlanOut

logger = logging.getLogger(__name__)


router = Router()


@router.get("", response={200: StudyPlanOut | None}, url_name="get_recent_study_plan")
async def get_recent_study_plan(request):
    user = request.auth
    study_plan = await study_plan_service.get_most_recent_study_plan(user)
    return study_plan


@router.post("", response={201: StudyPlanOut}, url_name="get_recent_study_plan")
async def create_study_plan(
    request,
    study_plan_in: StudyPlanIn,
):
    user = request.auth
    study_plan = await study_plan_service.create_study_plan(user, study_plan_in.area)
    return study_plan
