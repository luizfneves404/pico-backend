from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, Field

from app.in_app_notifications.models import (
    ExternalInAppNotification,
    FlowInAppNotification,
)


class BaseNotification(BaseModel):
    id: int
    created_at: AwareDatetime
    seen: bool
    text: str


class ExternalNotificationOut(BaseNotification):
    external_url: str
    notification_type: Literal["external"] = "external"

    @classmethod
    def from_orm_model(
        cls, model: ExternalInAppNotification
    ) -> "ExternalNotificationOut":
        return cls(
            id=model.id,
            created_at=model.created_at,
            seen=model.seen,
            text=model.text,
            external_url=model.external_url,
        )


class FlowNotificationOut(BaseNotification):
    flow_id: int
    notification_type: Literal["flow"] = "flow"

    @classmethod
    def from_orm_model(cls, model: FlowInAppNotification) -> "FlowNotificationOut":
        return cls(
            id=model.id,
            created_at=model.created_at,
            seen=model.seen,
            text=model.text,
            flow_id=model.flow_id,
        )


NotificationOut = Annotated[
    ExternalNotificationOut | FlowNotificationOut,
    Field(discriminator="notification_type"),
]
