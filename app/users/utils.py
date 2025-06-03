import datetime

from sqlalchemy.ext.asyncio import AsyncSession

import app.timezone as timezone
import app.ws.service as ws_service


def get_streak_info(answer_timestamps: list[datetime.datetime]) -> tuple[bool, int]:
    """Calculate user's streak information from answer timestamps.

    Args:
        answer_timestamps: List of user answer timestamps (must be timezone-aware)

    Returns:
        Tuple of (done_today, streak_count)

    Raises:
        ValueError: If timestamps are not timezone-aware
    """

    if not answer_timestamps:
        return False, 0

    # Ensure all timestamps are timezone-aware
    if any(
        ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None for ts in answer_timestamps
    ):
        raise ValueError("All timestamps must be timezone-aware")

    # Convert timestamps to server's timezone
    ordered_timestamps = sorted(
        (timezone.localtime(ts) for ts in answer_timestamps), reverse=True
    )

    streak = 0
    today = timezone.localdate()
    done_today = False
    last_processed_date = None

    for timestamp in ordered_timestamps:
        current_date = timestamp.date()

        if last_processed_date == current_date:
            continue
        last_processed_date = current_date

        if streak == 0:
            if current_date == today:
                done_today = True
                streak += 1
            elif current_date == today - datetime.timedelta(days=1):
                streak += 1
            else:
                break
        else:
            if current_date == today - datetime.timedelta(
                days=streak + 1 if not done_today else streak
            ):
                streak += 1
            else:
                break

    return done_today, streak


async def get_online_info(
    db_session: AsyncSession,
    user_ids: list[int],
) -> list[dict[str, int | bool | datetime.datetime | None]]:
    """Get online status and last online time for a list of users.

    Args:
        db_session: The database session
        user_ids: List of user IDs to check status for

    Returns:
        List of dicts containing:
            - id: user ID
            - is_online: boolean indicating if the user is online
            - last_online: last online time for offline users, None for online users
    """
    # Get current online/offline status for all users
    statuses = await ws_service.get_user_statuses(user_ids)

    # Get last online time for offline users
    offline_user_ids = [
        user_id for user_id, status in zip(user_ids, statuses) if status != "online"
    ]
    last_online_users = await ws_service.get_last_online_users(
        db_session, offline_user_ids
    )

    # Build response combining status and last online time
    return [
        {
            "id": user_id,
            "is_online": status == "online",  # Convert to boolean
            "last_online": last_online_users.get(user_id)
            if status != "online"
            else None,
        }
        for user_id, status in zip(user_ids, statuses)
    ]
