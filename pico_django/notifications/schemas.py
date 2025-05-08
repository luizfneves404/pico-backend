from typing import Any, ClassVar

from api.schemas.chatrooms import MemberOut
from api.schemas.messages import MessageOut
from pydantic import BaseModel, computed_field


class Notification(BaseModel):
    _event_type: ClassVar[str]

    @computed_field
    @property
    def type(self) -> str:
        return f"notification.{self._event_type}"


class ChatroomNotification(Notification):
    chatroom_id: int


class ChatroomRenameNotification(ChatroomNotification):
    _event_type: ClassVar[str] = "chatroom_rename"
    name: str
    by_user: MemberOut


class MessageNotification(ChatroomNotification):
    _event_type: ClassVar[str] = "message"
    message: MessageOut


class LeaveNotification(ChatroomNotification):
    _event_type: ClassVar[str] = "leave"
    user: MemberOut


class AddMemberNotification(ChatroomNotification):
    _event_type: ClassVar[str] = "add_member"
    added_user: MemberOut
    added_by_user: MemberOut


class RemoveMemberNotification(ChatroomNotification):
    _event_type: ClassVar[str] = "remove_member"
    removed_user: MemberOut
    removed_by_user: MemberOut


class MakeAdminNotification(ChatroomNotification):
    _event_type: ClassVar[str] = "make_admin"
    to_user: MemberOut
    by_user: MemberOut


class RemoveAdminNotification(ChatroomNotification):
    _event_type: ClassVar[str] = "remove_admin"
    to_user: MemberOut
    by_user: MemberOut


class ErrorNotification(Notification):
    _event_type: ClassVar[str] = "error"
    error: str


class FeatureErrorNotification(Notification):
    _event_type: ClassVar[str] = "feature_error"
    code: str
    extra_info: Any


class CleanedTextNotification(Notification):
    _event_type: ClassVar[str] = "cleaned_text"
    essay_topic_id: int
    cleaned_text: str


class EssayCorrectionNotification(Notification):
    _event_type: ClassVar[str] = "essay_correction"
    essay_topic_id: int
    feedbacks: list[str]
    grades: list[float | None]
