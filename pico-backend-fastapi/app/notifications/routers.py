from fastapi import APIRouter

from app.deps import CurrentUserAnnotated, DBSessionAnnotated
from app.notifications import service
from app.notifications.models import ExternalInAppNotification
from app.notifications.schemas import (
    ExternalNotificationOut,
    FlowNotificationOut,
    NotificationOut,
)

router = APIRouter(prefix="/in-app-notifications", tags=["in-app-notifications"])


@router.get("/list", response_model=list[NotificationOut])
async def list_notifications(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
) -> list[NotificationOut]:
    return [
        ExternalNotificationOut.from_orm_model(notification)
        if isinstance(notification, ExternalInAppNotification)
        else FlowNotificationOut.from_orm_model(notification)
        for notification in await service.list_notifications(
            db_session, user_id=current_user.id
        )
    ]


@router.get("/count-unseen", response_model=int)
async def count_unseen_notifications(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
) -> int:
    return await service.count_unseen_notifications_for_user(
        db_session, user_id=current_user.id
    )


@router.post("/mark-all-as-seen", name="mark_all_notifications_as_seen")
async def mark_all_as_seen(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
) -> None:
    await service.mark_all_as_seen(db_session, user_id=current_user.id)
