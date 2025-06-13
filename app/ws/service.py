import datetime
import logging
from enum import StrEnum
from typing import TypedDict

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

import app.timezone as timezone
from app.redis_client import get_redis
from app.ws.models import UserOnlineInfo

logger = logging.getLogger(__name__)


class UserStatus(StrEnum):
    """User status."""

    ONLINE = "online"
    OFFLINE = "offline"


async def handle_user_connection_event(db_session: AsyncSession, user_id: int) -> None:
    """
    Handles the user online event.
    """
    now = timezone.localtime()

    # Using PostgreSQL's "upsert" functionality via SQLAlchemy
    stmt = (
        pg_insert(UserOnlineInfo)
        .values(
            user_id=user_id,
            last_websocket_connection=now,
            last_websocket_disconnection=None,
            is_online=True,
        )
        .on_conflict_do_update(
            index_elements=["user_id"],
            set_=dict(
                last_websocket_connection=now,
                is_online=True,
            ),
        )
    )
    await db_session.execute(stmt)
    logger.debug(f"Updated connection timestamp for user {user_id}")


async def handle_user_disconnection_event(
    db_session: AsyncSession, user_id: int
) -> None:
    """
    Handles the user offline event.
    """
    now = timezone.localtime()

    stmt = (
        update(UserOnlineInfo)
        .where(UserOnlineInfo.user_id == user_id)
        .values(
            last_websocket_disconnection=now,
            is_online=False,
        )
    )

    await db_session.execute(stmt)

    logger.debug(
        f"Updated disconnection timestamp for user {user_id} if the object exists"
    )


class OnlineInfo(TypedDict):
    id: int
    is_online: bool
    last_online: datetime.datetime | None


async def get_online_info(
    db_session: AsyncSession, user_ids: list[int]
) -> dict[int, OnlineInfo]:
    """
    Get the last online timestamp for a list of users.

    Args:
        db_session: The database session
        user_ids: List of user IDs to check

    Returns:
        Dictionary mapping user_id to OnlineInfo.
        For users not found in the DB (never logged in), is_online is False and last_online is None.
    """
    # Fetch existing user online info
    result = await db_session.execute(
        select(
            UserOnlineInfo.user_id,
            UserOnlineInfo.last_websocket_disconnection,
            UserOnlineInfo.is_online,
        ).where(UserOnlineInfo.user_id.in_(user_ids))
    )

    # Build a partial result from DB
    partial_info = {
        user_id: OnlineInfo(
            id=user_id,
            is_online=is_online,
            last_online=None if is_online else last_disconnection,
        )
        for user_id, last_disconnection, is_online in result.all()
    }

    # Fill in missing users (i.e., users never logged in)
    full_info = {
        user_id: partial_info.get(
            user_id,
            OnlineInfo(id=user_id, is_online=False, last_online=None),
        )
        for user_id in user_ids
    }

    return full_info


async def count_queued_notifications(user_ids: list[int]) -> dict[int, int]:
    notification_counts: dict[int, int] = {}

    conn = get_redis()
    # Split user_ids into batches
    for i in range(0, len(user_ids), MAX_PIPELINE_BATCH_SIZE):
        current_batch = user_ids[i : i + MAX_PIPELINE_BATCH_SIZE]
        async with conn.pipeline() as pipe:
            # Queue all the LLEN commands for the current batch
            for user_id in current_batch:
                pipe.llen(f"notification_queue_{user_id}")

            # Execute all commands in the pipeline for the current batch
            batch_results: list[int] = await pipe.execute()

            # Map the results back to user IDs for the current batch
            batch_counts = {
                user_id: count for user_id, count in zip(current_batch, batch_results)
            }
            notification_counts.update(batch_counts)

            # Log the results for the current batch
            logger.debug(f"User notification counts: {batch_counts}")

    return notification_counts


async def get_queued_notifications(user_id: int) -> list[str]:
    logger.debug(f"Getting queued notifications for user {user_id}...")

    queued_events = await _get_user_notifications(user_id)

    await _clear_user_notifications(user_id)

    return queued_events
