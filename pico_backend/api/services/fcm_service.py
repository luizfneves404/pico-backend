import logging

import notifications.utils as notifications_utils
from django.contrib.auth.models import AbstractBaseUser
from fcm_django.models import FCMDevice
from firebase_admin.messaging import APNSConfig, APNSPayload, Aps, Message, Notification

logger = logging.getLogger(__name__)


async def create_or_update_device(
    user: AbstractBaseUser,
    registration_id: str,
    type_: str,
) -> FCMDevice:
    logger.debug(
        f"Creating or updating device for user {user.id} with registration_id {registration_id}"
    )
    existing_device = await FCMDevice.objects.filter(
        registration_id=registration_id
    ).afirst()
    if existing_device:
        logger.debug(
            f"Device with registration_id {registration_id} already exists, updating..."
        )
        existing_device.type = type_
        existing_device.active = True
        existing_device.user = user
        await existing_device.asave()
        return existing_device
    else:
        logger.debug(
            f"Device with registration_id {registration_id} does not exist, creating..."
        )
        new_device = FCMDevice(
            user=user,
            registration_id=registration_id,
            type=type_,
            active=True,
        )
        await new_device.asave()

        # deleting other devices because only one device per user is allowed
        await FCMDevice.objects.filter(user=user).exclude(id=new_device.id).adelete()

        return new_device


def send_notification(user_ids: list[int] | int, title: str, body: str) -> None:
    """Sends a notification to the users with the given ids.

    Args:
        users_ids (list[int] | int): The user ids to send the notification to.
        title (str): The title of the notification.
        body (str): The body of the notification.
    """
    if isinstance(user_ids, int):
        user_ids = [user_ids]
    notification_counts = notifications_utils.count_queued_notifications(user_ids)

    for user_id in (
        user_ids
    ):  # cannot send all in one go because of the badges, that are different per user
        devices = FCMDevice.objects.filter(user_id=user_id, active=True)
        badge = notification_counts.get(user_id, 0)
        _send_notification_to_devices(devices, title, body, badge)


def send_reset_badge_notification(
    user_ids: int | list[int],
) -> None:
    """Sends a notification to reset the badge of the user, especially in iOS.

    Args:
        users_ids (int | list[int]): The user id or list of user ids to send the notification to.
    """
    if isinstance(user_ids, int):
        user_ids = [user_ids]
    logger.debug(f"Sending reset badge notification to users {user_ids}")
    devices = FCMDevice.objects.filter(user_id__in=user_ids, active=True)
    _send_notification_to_devices(devices, "", "", 0)


def _send_notification_to_devices(
    devices_queryset, title: str, body: str, badge: int
) -> None:
    device_ids = [device.id for device in devices_queryset]
    logger.debug(
        f"Sending FCM notification to devices {device_ids}: Title='{title}', Body='{body}', Badge={badge}"
    )
    devices_queryset.send_message(
        Message(
            notification=Notification(title=title, body=body),
            apns=APNSConfig(payload=APNSPayload(aps=Aps(badge=badge))),
        )
    )
