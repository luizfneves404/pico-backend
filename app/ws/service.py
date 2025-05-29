import datetime
import logging
from enum import StrEnum
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

import app.timezone as timezone
from app.redis_client import get_redis
from app.ws.models import UserWebsocketInfo

logger = logging.getLogger(__name__)


class UserStatus(StrEnum):
    """User status."""

    ONLINE = "online"
    OFFLINE = "offline"


async def handle_user_connection_event(db_session: AsyncSession, user_id: int) -> None:
    """
    Handles the user online event.
    """
    await _update_connection_timestamp(db_session, user_id)
    await _set_user_status(user_id, UserStatus.ONLINE)


async def handle_user_disconnection_event(
    db_session: AsyncSession, user_id: int
) -> None:
    """
    Handles the user offline event.
    """
    await _update_disconnection_timestamp(db_session, user_id)
    await _set_user_status(user_id, UserStatus.OFFLINE)


async def _update_connection_timestamp(db_session: AsyncSession, user_id: int) -> None:
    """
    Updates the websocket connection timestamp for a user.
    """
    now = timezone.localtime()

    # Using PostgreSQL's "upsert" functionality via SQLAlchemy
    stmt = (
        pg_insert(UserWebsocketInfo)
        .values(
            user_id=user_id,
            last_websocket_connection=now,
            last_websocket_disconnection=None,
        )
        .on_conflict_do_update(
            index_elements=["user_id"], set_=dict(last_websocket_connection=now)
        )
    )
    await db_session.execute(stmt)
    logger.debug(f"Updated connection timestamp for user {user_id}")


async def _update_disconnection_timestamp(
    db_session: AsyncSession, user_id: int
) -> None:
    """
    Updates the websocket disconnection timestamp for a user. The UserWebsocketInfo object must exist (you should have called update_connection_timestamp before this) for anything to happen.
    """
    now = timezone.localtime()

    stmt = (
        update(UserWebsocketInfo)
        .where(UserWebsocketInfo.user_id == user_id)
        .values(last_websocket_disconnection=now)
    )

    await db_session.execute(stmt)

    logger.debug(
        f"Updated disconnection timestamp for user {user_id} if the object exists"
    )


async def get_last_online_users(
    db_session: AsyncSession, user_ids: list[int]
) -> dict[int, datetime.datetime]:
    """
    Get the last online timestamp for a list of users.

    Args:
        db_session: The database session
        user_ids: List of user IDs to check

    Returns:
        Dictionary mapping user_id to last_websocket_disconnection
    """
    # Get all websocket info records for the users in a single query
    result = await db_session.execute(
        select(
            UserWebsocketInfo.user_id, UserWebsocketInfo.last_websocket_disconnection
        ).where(UserWebsocketInfo.user_id.in_(user_ids))
    )

    # Convert to dictionary mapping user_id to last_websocket_disconnection
    return {user_id: last_disconnection for user_id, last_disconnection in result.all()}


async def _set_user_status(user_id: int, status: UserStatus):
    conn = get_redis()
    await conn.set(f"user_status_{user_id}", status)
    logger.debug(f"User {user_id} status in redis set to '{status}'")


async def _clear_user_notifications(user_id: int):
    conn = get_redis()
    await conn.delete(f"notification_queue_{user_id}")
    logger.debug(f"User {user_id} notifications in redis cleared")


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


async def get_user_statuses(
    user_ids: list[int],
) -> list[UserStatus | None]:
    conn = get_redis()
    statuses: list[Literal["online", "offline"] | None] = await conn.mget(
        [f"user_status_{id}" for id in user_ids]
    )
    logger.debug(
        f"The status of the following users from redis {user_ids} are: {statuses}"
    )
    return list(UserStatus(status) for status in statuses)


async def get_queued_notifications(user_id: int) -> list[str]:
    logger.debug(f"Getting queued notifications for user {user_id}...")

    queued_events = await _get_user_notifications(user_id)

    await _clear_user_notifications(user_id)

    return queued_events
