import json
import logging
from dataclasses import dataclass

import firebase_admin.messaging as messaging
from firebase_admin import credentials, initialize_app
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.notifications as notifications_service
from app.config import settings
from app.fcm.models import DeviceType, FCMDevice
from app.users.models import User

logger = logging.getLogger(__name__)


def init_firebase():
    initialize_app(
        credential=credentials.Certificate(
            json.loads(settings.firebase_json_service_key.model_dump_json())
        )
    )
    logger.debug("Firebase initialized")


async def create_or_update_device(
    db_session: AsyncSession,
    user: User,
    registration_id: str,
    device_type: DeviceType,
) -> FCMDevice:
    logger.debug(
        f"Creating or updating device for user {user.id} with registration_id {registration_id}"
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
        existing_device.user = user
        db_session.add(existing_device)
        await db_session.flush()

        device_to_return = existing_device
    else:
        logger.debug(
            f"Device with registration_id {registration_id} does not exist, creating..."
        )
        # Create new device
        new_device = FCMDevice(
            user=user,
            registration_id=registration_id,
            device_type=device_type,
            active=True,
        )
        db_session.add(new_device)
        await db_session.flush()

        # Find and delete other devices for this user in a single operation
        await db_session.execute(
            delete(FCMDevice).filter(
                FCMDevice.user_id == user.id,
                FCMDevice.registration_id != registration_id,
            )
        )

        device_to_return = new_device

    return device_to_return


@dataclass
class NotificationData:
    """Type definition for notification data."""

    user_id: int
    title: str
    body: str
    badge: int | None = None


async def send_reset_badge_notification(
    db_session: AsyncSession,
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
    await _send_notifications_with_badge(db_session, notifications_with_badge)


async def send_notifications(
    db_session: AsyncSession,
    notification_data: list[NotificationData] | NotificationData,
) -> None:
    """
    Send notifications to users with notification content.

    Args:
        db_session: The database session
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
    notification_counts = await notifications_service.count_queued_notifications(
        user_ids
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
    await _send_notifications_with_badge(db_session, notifications_with_badge)


async def _send_notifications_with_badge(
    db_session: AsyncSession,
    notifications_with_badge: list[NotificationData],
) -> None:
    """
    Internal function to send notifications with pre-determined badge counts.

    Args:
        db_session: The database session
        notifications_with_badge: List of NotificationData objects with badge counts
    """
    if not notifications_with_badge:
        logger.debug("No notification data provided")
        return

    # Get all active devices for the relevant users in a single query
    user_ids = [data.user_id for data in notifications_with_badge]
    result = await db_session.execute(
        select(FCMDevice).filter(
            FCMDevice.user_id.in_(user_ids), FCMDevice.active.is_(True)
        )
    )

    # Create a direct mapping from user_id to device
    devices = {device.user_id: device for device in result.scalars().all()}

    if not devices:
        logger.debug(f"No active devices found for users {user_ids}")
        return

    # Build messages directly - one per notification with an active device
    messages: list[messaging.Message] = []
    for data in notifications_with_badge:
        user_id = data.user_id
        if user_id not in devices:
            continue

        messages.append(
            messaging.Message(
                notification=messaging.Notification(title=data.title, body=data.body),
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(aps=messaging.Aps(badge=data.badge))
                ),
                token=devices[user_id].registration_id,
            )
        )

    if not messages:
        logger.debug("No messages to send")
        return

    # Send notifications
    logger.debug(f"Sending {len(messages)} FCM notifications")
    response: messaging.BatchResponse = messaging.send_each(
        messages, dry_run=settings.fcm_dry_run
    )
    logger.debug(
        f"Successfully sent {response.success_count} messages, failed: {response.failure_count}"
    )
