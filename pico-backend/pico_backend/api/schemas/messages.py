from datetime import datetime

from api.schemas.chatrooms import MemberOut
from ninja import Schema
from pydantic import AwareDatetime, ConfigDict


class SenderOut(MemberOut):
    pass


class IdOut(Schema):
    id: int


class ForwardMessageIn(Schema):
    to_usernames: list[str]


class MessageOut(Schema):
    id: int
    sender: SenderOut
    content: str
    attachment: str | None = None
    extra_object_id: int | None = None
    timestamp: AwareDatetime
    parent_message: IdOut | None = None
    thread_messages: list["MessageOut"] = []

    model_config = ConfigDict(from_attributes=True)
