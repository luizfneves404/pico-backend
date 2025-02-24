from datetime import datetime

from config import settings
from pydantic import BaseModel

DEFAULT_PHONE_NUMBER_AREA_CODE = settings.default_phone_number_country


class MemberOut(BaseModel):
    id: int
    username: str
    phone_number: str
    is_admin: bool


class ChatRoomIn(BaseModel):
    name: str
    members_ids: set[int]


class ChatRoomOut(BaseModel):
    name: str
    members: list[MemberOut] = list()
    id: int
    timestamp: datetime
