import logging

from ninja import Router

from badges import badge_service
from badges.schemas import BadgeOut

logger = logging.getLogger(__name__)


router = Router()


@router.get("", response={200: list[BadgeOut]}, url_name="list_badges")
async def list_badges(request):
    user = request.auth
    badges = await badge_service.list_badges(user.id)
    return badges
