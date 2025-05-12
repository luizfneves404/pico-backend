import logging

from api.models import Chatroom, User
from ninja.errors import HttpError

logger = logging.getLogger(__name__)


async def get_chatroom_or_http_error(chatroom_id: int):
    chatroom = (
        await Chatroom.objects.filter(id=chatroom_id)
        .prefetch_related("members")
        .afirst()
    )
    if not chatroom:
        raise HttpError(404, "Chatroom not found")
    return chatroom


async def validate_chatroom_membership_members_prefetched(chatroom_id: int, user: User):
    chatroom = (
        await Chatroom.objects.filter(id=chatroom_id)
        .prefetch_related("members")
        .afirst()
    )
    if not chatroom:
        raise HttpError(404, "Chatroom not found")
    if not await chatroom.ais_member(user):
        raise HttpError(403, "User is not a member of this chatroom")
    return chatroom
