import logging
from dataclasses import dataclass
from typing import Any

import firebase_admin.messaging as firebase_messaging
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.notifications.service as notifications_service
from app.arq_client import enqueue_job
from app.config import Environment, settings
from app.database import get_db_session_for_worker
from app.fcm.models import DeviceType, FCMDevice

logger = logging.getLogger(__name__)

FCM_NOTIFICATION_BATCH_SIZE = 450


async def create_or_update_device(
    db_session: AsyncSession,
    user_id: int,
    registration_id: str,
    device_type: DeviceType,
) -> FCMDevice:
    logger.debug(
        f"Creating or updating device for user {user_id} with registration_id {registration_id}"
    )

    # First, check if the device exists
    existing_device = (
        await db_session.execute(
            select(FCMDevice).filter(FCMDevice.registration_id == registration_id)
        )
    ).scalar_one_or_none()

    if existing_device:
        logger.debug(
            f"Device with registration_id {registration_id} already exists, updating..."
        )
        # Update existing device
        existing_device.device_type = device_type
        existing_device.active = True
        existing_device.user_id = user_id
        db_session.add(existing_device)
        await db_session.flush()

        device_to_return = existing_device
    else:
        logger.debug(
            f"Device with registration_id {registration_id} does not exist, creating..."
        )
        # Create new device
        new_device = FCMDevice(
            user_id=user_id,
            registration_id=registration_id,
            device_type=device_type,
            active=True,
        )
        db_session.add(new_device)
        await db_session.flush()

        # Find and delete other devices for this user in a single operation
        await db_session.execute(
            delete(FCMDevice).filter(
                FCMDevice.user_id == user_id,
                FCMDevice.registration_id != registration_id,
            )
        )

        device_to_return = new_device

    return device_to_return


@dataclass(slots=True, kw_only=True, frozen=True)
class NotificationData:
    """Type definition for notification data."""

    user_id: int
    title: str
    body: str
    badge: int | None = None


async def send_reset_badge_notification(
    user_ids: int | list[int],
) -> None:
    """Sends a notification to reset the badge of the user, especially in iOS.

    Args:
        user_ids (int | list[int]): The user id or list of user ids to send the notification to.
    """
    if isinstance(user_ids, int):
        user_ids = [user_ids]
    logger.debug(f"Sending reset badge notification to users {user_ids}")

    # Create notification data with explicit badge count of 0
    notifications_with_badge = [
        NotificationData(user_id=user_id, title="", body="", badge=0)
        for user_id in user_ids
    ]

    # Use the internal function with explicit badge counts
    await enqueue_job(
        "task_send_notifications",
        notifications_with_badge=notifications_with_badge,
    )


async def send_notifications(
    db_session: AsyncSession,
    notification_data: list[NotificationData] | NotificationData,
) -> None:
    """
    Send notifications to users with notification content. Determines the badge count for each user.

    Args:
        notification_data: NotificationData or list of NotificationData
    """
    # Normalize input to list
    notifications_list = (
        [notification_data]
        if not isinstance(notification_data, list)
        else notification_data
    )
    if not notifications_list:
        logger.debug("No notification data provided")
        return

    # Get all user IDs from the notification data
    user_ids = [data.user_id for data in notifications_list]

    # Get badge counts for these users
    notification_counts = (
        await notifications_service.count_unseen_notifications_for_users(
            db_session, user_ids=user_ids
        )
    )

    # Create notifications with badge counts
    notifications_with_badge = [
        NotificationData(
            user_id=data.user_id,
            title=data.title,
            body=data.body,
            badge=notification_counts.get(data.user_id, 0),
        )
        for data in notifications_list
    ]

    # Send the notifications with the calculated badge counts
    await enqueue_job(
        "task_send_notifications",
        notifications_with_badge=notifications_with_badge,
    )


async def task_send_notifications(
    ctx: dict[str, Any],
    notifications_with_badge: list[NotificationData],
) -> None:
    """
    Internal function to send notifications with pre-determined badge counts.

    Args:
        notifications_with_badge: List of NotificationData objects with badge counts
    """
    if not notifications_with_badge:
        logger.debug("No notification data provided")
        return

    # Get all active devices for the relevant users in a single query
    user_ids = [data.user_id for data in notifications_with_badge]
    async with get_db_session_for_worker(ctx) as db_session:
        result = await db_session.execute(
            select(FCMDevice, FCMDevice.user_id).where(
                FCMDevice.user_id.in_(user_ids), FCMDevice.active.is_(True)
            )
        )

    devices = {user_id: device for device, user_id in result.tuples()}

    if not devices:
        logger.debug(f"No active devices found for users {user_ids}")
        return

    # Build messages directly - one per notification with an active device
    messages: list[firebase_messaging.Message] = []
    for data in notifications_with_badge:
        user_id = data.user_id
        if user_id not in devices:
            continue

        messages.append(
            firebase_messaging.Message(
                notification=firebase_messaging.Notification(
                    title=data.title, body=data.body
                ),
                apns=firebase_messaging.APNSConfig(
                    payload=firebase_messaging.APNSPayload(
                        aps=firebase_messaging.Aps(badge=data.badge)
                    )
                ),
                token=devices[user_id].registration_id,
            )
        )

    if not messages:
        logger.debug("No messages to send")
        return

    # Send notifications in batches of 500 because otherwise send_each will complain

    total_success = 0
    total_failure = 0

    logger.debug(
        f"Sending {len(messages)} FCM notifications in batches of {FCM_NOTIFICATION_BATCH_SIZE}"
    )

    for i in range(0, len(messages), FCM_NOTIFICATION_BATCH_SIZE):
        batch = messages[i : i + FCM_NOTIFICATION_BATCH_SIZE]
        logger.debug(
            f"Sending batch {i // FCM_NOTIFICATION_BATCH_SIZE + 1} with {len(batch)} messages"
        )

        response: firebase_messaging.BatchResponse = await messaging.send_each_async(
            batch
        )

        total_success += response.success_count
        total_failure += response.failure_count

    logger.debug(f"Successfully sent {total_success} messages, failed: {total_failure}")


class FakeMessaging:
    def __init__(self):
        self._last_sent_messages: list[firebase_messaging.Message] = []

    async def send_each_async(
        self, messages: list[firebase_messaging.Message]
    ) -> firebase_messaging.BatchResponse:
        logger.debug(f"FakeMessaging.send_each: {messages}")
        if len(messages) > 500:
            raise ValueError("messages must not contain more than 500 elements.")

        self._last_sent_messages = messages

        responses: list[firebase_messaging.SendResponse] = [
            firebase_messaging.SendResponse(
                resp={"name": f"message_id_{i}"}, exception=None
            )
            for i in range(len(messages))
        ]
        return firebase_messaging.BatchResponse(responses=responses)

    @property
    def last_sent_messages(self) -> list[firebase_messaging.Message]:
        return self._last_sent_messages.copy()


messaging = (
    firebase_messaging if settings.environment == Environment.PROD else FakeMessaging()
)


def get_last_sent_messages() -> list[firebase_messaging.Message]:
    if isinstance(messaging, FakeMessaging):
        return messaging.last_sent_messages
    raise RuntimeError("messaging is not a FakeMessaging")
