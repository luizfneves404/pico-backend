from typing import Any, ClassVar

from pydantic import AwareDatetime, BaseModel, ConfigDict, computed_field

from app.shared.validation import CustomPhoneNumber, LowercaseEmailStr


class Notification(BaseModel):
    _event_type: ClassVar[str]

    @computed_field
    @property
    def type(self) -> str:
        return f"notification.{self._event_type}"


class ChatroomNotification(Notification):
    chatroom_id: int


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


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    phone_number: CustomPhoneNumber
    email: LowercaseEmailStr


class SenderOut(MemberOut):
    pass


class IdOut(BaseModel):
    id: int


class MessageOut(BaseModel):
    id: int
    sender: SenderOut
    content: str
    attachment: str | None = None
    extra_object_id: int | None = None
    timestamp: AwareDatetime
    parent_message: IdOut | None = None
    thread_messages: list["MessageOut"] = []

    model_config = ConfigDict(from_attributes=True)


class MessageNotification(ChatroomNotification):
    _event_type: ClassVar[str] = "message"
    message: MessageOut
