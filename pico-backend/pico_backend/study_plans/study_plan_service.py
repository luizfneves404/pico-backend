import logging

from django.contrib.auth.models import AbstractUser
from study_plans.models import StudyPlan
from study_plans.tasks import add_calendar_json_async_workflow

logger = logging.getLogger(__name__)


async def create_study_plan(user: AbstractUser, area: str) -> StudyPlan:
    study_plan = await StudyPlan.objects.acreate(user=user)
    logger.debug(f"Created study plan {study_plan.id} for user {user.username}")
    await add_calendar_json_async_workflow(study_plan.id, area)
    logger.debug(
        f"Called add_calendar_json_async_workflow for study plan {study_plan.id}"
    )
    return study_plan


async def get_most_recent_study_plan(user: AbstractUser) -> StudyPlan | None:
    logger.debug(f"Getting most recent study plan for user {user.username}")
    return await StudyPlan.objects.filter(user=user).order_by("-created_at").afirst()
