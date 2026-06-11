from enum import StrEnum

from pydantic import BaseModel


class MessageType(StrEnum):
    """Message type."""

    ECHO = "echo"


class WebsocketMessage(BaseModel):
    """Websocket message schema."""

    message_type: MessageType
    message: str
