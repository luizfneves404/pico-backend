from sqlalchemy import func, select
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
        .order_by(InAppNotification.created_at.desc())
    )
    result = await db_session.execute(query)
    notifications = list(result.scalars().all())
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
