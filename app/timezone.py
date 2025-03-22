import datetime
from zoneinfo import ZoneInfo

from config import settings

local_tz = ZoneInfo(settings.local_timezone)


def localtime(dt: datetime.datetime | None = None) -> datetime.datetime:
    """Convert a datetime to the local timezone.

    Args:
        dt (datetime.datetime, optional): The datetime to convert. Must be timezone-aware if provided.
            Defaults to None, in which case returns current time.

    Raises:
        ValueError: If the datetime is naive (has no timezone info).

    Returns:
        datetime.datetime: The datetime in the local timezone.
    """
    if dt is None:
        return datetime.datetime.now(local_tz)
    if dt.tzinfo is None:
        raise ValueError("Datetime must be timezone-aware")
    return dt.astimezone(local_tz)


def localdate(dt: datetime.datetime | None = None) -> datetime.date:
    """Convert a datetime to the local timezone and return the date.

    Args:
        dt (datetime.datetime, optional): The datetime to convert. Must be timezone-aware if provided.
            Defaults to None, in which case returns current date.

    Returns:
        datetime.date: The date in the local timezone.
    """
    return localtime(dt).date()
