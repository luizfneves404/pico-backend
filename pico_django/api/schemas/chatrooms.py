from enum import StrEnum
from typing import Self

from api.schemas.users import PhoneNumber
from django.conf import settings
from ninja import Schema
from pydantic import (
    AwareDatetime,
    ConfigDict,
    Field,
    model_validator,
)
from shared.validation import LowercaseEmailStr

OFFICIAL_CHATROOM_ICON_URL = settings.OFFICIAL_CHATROOM_ICON_URL


class MemberOut(Schema):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    phone_number: PhoneNumber
    email: LowercaseEmailStr


class MemberOutIsAdmin(MemberOut):
    is_admin: bool


class ChatroomIn(Schema):
    name: str = Field(max_length=50)
    members_ids: set[int] = Field(max_length=50, default_factory=set)


class ChatroomNameIn(Schema):
    name: str = Field(max_length=50)


class ChatTypeEnum(StrEnum):
    GROUP = "GP"
    DM = "DM"
    OFFICIAL = "OF"


class ChatroomOut(Schema):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    timestamp: AwareDatetime
    members: list[MemberOutIsAdmin] = []
    icon: str | None
    chat_type: ChatTypeEnum

    @model_validator(mode="after")
    def change_icon_if_official(self) -> Self:
        if self.chat_type == ChatTypeEnum.OFFICIAL:
            self.icon = OFFICIAL_CHATROOM_ICON_URL

        return self

    @model_validator(mode="after")
    def set_name_of_dm_chatroom(self) -> Self:
        if self.chat_type == ChatTypeEnum.DM:
            self.name = (
                f"{self.members[0].username} e {self.members[1].username}"
                if len(self.members) >= 2
                else self.members[0].username
            )

        return self


class UserUsernameSchema(Schema):
    username: str = Field(max_length=50)
