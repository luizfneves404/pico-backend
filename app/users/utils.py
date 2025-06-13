import datetime

import app.timezone as timezone


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
