import logging

from django.db import connection
from django.utils import timezone

from chat.models import UserWebsocketInfo

logger = logging.getLogger(__name__)


def update_connection_timestamp(user_id: int):
    """
    Updates the websocket connection timestamp for a user.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
        INSERT INTO chat_userwebsocketinfo (user_id, last_websocket_connection, last_websocket_disconnection) 
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id) 
        DO UPDATE SET last_websocket_connection = EXCLUDED.last_websocket_connection
    """,
            [user_id, timezone.now(), None],
        )
    logger.debug(f"Updated connection timestamp for user {user_id}")


def update_disconnection_timestamp(user_id: int):
    """
    Updates the websocket disconnection timestamp for a user. The UserWebsocketInfo object must exist (you should have called update_connection_timestamp before this) for anything to happen.
    """
    UserWebsocketInfo.objects.filter(user_id=user_id).update(
        last_websocket_disconnection=timezone.now()
    )
    logger.debug(
        f"Updated disconnection timestamp for user {user_id} if the object exists"
    )


def get_last_online_users(user_ids: list[int]) -> dict[int, timezone.datetime]:
    # Get all websocket info records for the users in a single query
    websocket_infos = UserWebsocketInfo.objects.filter(
        user_id__in=user_ids
    ).values_list("user_id", "last_websocket_disconnection")

    # Convert to dictionary mapping user_id to last_websocket_connection
    return dict(websocket_infos)
