import datetime
import logging

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

import app.timezone as timezone
from app.chat.models import UserWebsocketInfo

logger = logging.getLogger(__name__)


async def update_connection_timestamp(db_session: AsyncSession, user_id: int) -> None:
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


async def update_disconnection_timestamp(
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
