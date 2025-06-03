from pydantic import AwareDatetime, BaseModel

from app.notifications.models import InAppNotificationType


class Notification(BaseModel):
    id: int
    created_at: AwareDatetime
    seen: bool
    text: str
    in_app_notification_type: InAppNotificationType
