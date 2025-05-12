from pydantic import BaseModel, ConfigDict, Field


class MessageEventIn(BaseModel):
    """Message event schema."""

    message: str = Field(max_length=30000)
    chatroom_id: int | None = None
    parent_message_id: int | None = None

    model_config = ConfigDict(extra="forbid")
