from typing import Literal, overload

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.in_app_notifications.models import (
    ExternalInAppNotification,
    FlowInAppNotification,
    InAppNotification,
)


async def list_notifications(
    db_session: AsyncSession,
    *,
    user_id: int,
) -> list[ExternalInAppNotification | FlowInAppNotification]:
    query = (
        select(InAppNotification)
        .where(InAppNotification.user_id == user_id)
        .order_by(InAppNotification.created_at.desc(), InAppNotification.id.desc())
    )
    result = await db_session.execute(query)
    notifications = list(result.scalars())
    return notifications  # type: ignore # i don't know how to do the correct type hints


async def count_unseen_notifications(
    db_session: AsyncSession,
    *,
    user_id: int,
) -> int:
    query = select(func.count(InAppNotification.id)).where(
        InAppNotification.user_id == user_id, InAppNotification.seen.is_(False)
    )
    result = await db_session.execute(query)
    return result.scalar_one()


async def mark_all_as_seen(
    db_session: AsyncSession,
    *,
    user_id: int,
) -> None:
    query = (
        update(InAppNotification)
        .where(InAppNotification.user_id == user_id)
        .values(seen=True)
    )
    await db_session.execute(query)


@overload
async def create_notification(
    db_session: AsyncSession,
    *,
    user_id: int,
    notification_type: Literal["external"],
    external_url: str,
) -> None:
    pass


@overload
async def create_notification(
    db_session: AsyncSession,
    *,
    user_id: int,
    notification_type: Literal["flow"],
    flow_id: int,
) -> None:
    pass


async def create_notification(
    db_session: AsyncSession,
    *,
    user_id: int,
    notification_type: Literal["flow", "external"],
    flow_id: int | None = None,
    external_url: str | None = None,
) -> None:
    if notification_type == "flow":
        notification = FlowInAppNotification(
            user_id=user_id,
            flow_id=flow_id,
        )
    elif notification_type == "external":
        notification = ExternalInAppNotification(
            user_id=user_id,
            external_url=external_url,
        )
    else:
        raise ValueError(f"Invalid notification type: {notification_type}")

    db_session.add(notification)
