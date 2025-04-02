import asyncio
import logging
from typing import Any, ClassVar, Coroutine, Literal

from pydantic import BaseModel, computed_field
from redis.asyncio.client import Pipeline

import app.fcm_service as fcm_service
from app.redis_client import get_redis

MAX_PIPELINE_BATCH_SIZE = 100

FILE_TOO_BIG_MESSAGE = (
    "Desculpa, 500 páginas esse arquivo.. não consigo ler tudo isso :("
)

logger = logging.getLogger(__name__)


class Notification(BaseModel):
    _event_type: ClassVar[str]

    @computed_field
    @property
    def type(self) -> str:
        return f"notification.{self._event_type}"


async def set_user_status(user_id: int, status: Literal["online", "offline"]):
    conn = get_redis()
    await conn.set(f"user_status_{user_id}", status)
    logger.debug(f"User {user_id} status in redis set to '{status}'")


async def _get_user_notifications(user_id: int) -> list[str]:
    conn = get_redis()
    notifications: list[str] = await conn.lrange(f"notification_queue_{user_id}", 0, -1)
    logger.debug(f"User {user_id} notifications from redis: {notifications}")
    return notifications


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
) -> list[Literal["online", "offline"] | None]:
    conn = get_redis()
    statuses: list[Literal["online", "offline"] | None] = await conn.mget(
        [f"user_status_{id}" for id in user_ids]
    )
    logger.debug(
        f"The status of the following users from redis {user_ids} are: {statuses}"
    )
    return list(statuses)


async def get_queued_notifications(user_id: int) -> list[str]:
    logger.debug(f"Getting queued notifications for user {user_id}...")

    queued_events = await _get_user_notifications(user_id)

    await _clear_user_notifications(user_id)

    return queued_events


class NotificationBatch:
    def __init__(
        self,
        user_notification_tuples: list[tuple[int, Notification]],
    ):
        self.user_notification_tuples = user_notification_tuples

    async def send_async(self):
        async def send_notification(user_id: int, notification: Notification):
            notification_json = notification.model_dump(mode="json")
            await channel_layer.group_send(
                f"notifications_{user_id}",
                notification_json,
            )
            logger.debug(
                f"Notification sent to notifications_{user_id}: {notification_json}"
            )

        def enqueue_notification(
            user_ids: set[int], notification: Notification, pipeline: Pipeline
        ):
            for user_id in user_ids:
                pipeline.rpush(
                    f"notification_queue_{user_id}", notification.model_dump_json()
                )

        # Extract user IDs
        user_ids = list({user_id for user_id, _ in self.user_notification_tuples})

        # Get user statuses
        statuses = await get_user_statuses(user_ids)

        # Map user IDs to statuses
        user_status_map = {
            user_id: status for user_id, status in zip(user_ids, statuses)
        }

        online_tasks: list[Coroutine[Any, Any, None]] = []

        grouped_notifications: dict[tuple[str, str], list[int]] = {}

        # Create a Redis pipeline
        conn = get_redis()
        pipe = conn.pipeline()
        batch_count = 0

        # Process each user-notification tuple
        for user_id, notification in self.user_notification_tuples:
            if user_status_map[user_id] == "online":
                online_tasks.append(send_notification(user_id, notification))
            else:
                enqueue_notification({user_id}, notification, pipeline=pipe)
                batch_count += 1

                if batch_count >= MAX_PIPELINE_BATCH_SIZE:
                    logger.info(
                        f"Executing enqueueing Redis pipeline with batch count {batch_count}"
                    )
                    await pipe.execute()
                    await pipe.reset()
                    pipe = conn.pipeline()  # Start a new pipeline
                    batch_count = 0

            if isinstance(notification, MessageNotification):
                key: tuple[str, str] = (
                    notification.message.sender.username,
                    notification.message.content,
                )
                if key not in grouped_notifications:
                    grouped_notifications[key] = []
                grouped_notifications[key].append(user_id)

            # Execute any remaining commands in the pipeline
            if batch_count > 0:
                logger.info(
                    f"Executing final enqueueing Redis pipeline with batch count {batch_count}"
                )
                await pipe.execute()
                await pipe.reset()
                logger.debug(f"Last NotificationBatch was {(user_id, notification)}")

        for (title, body), user_ids in grouped_notifications.items():
            await fcm_service.send_notifications(
                db_session,
                [
                    fcm_service.NotificationData(
                        user_id=user_id, title=title, body=body
                    )
                    for user_id in user_ids
                ],
            )

        await asyncio.gather(*online_tasks)


def prepare_error_notification(receiver_user_id: int, error_message: str):
    notification = ErrorNotification(error=error_message)
    return NotificationBatch([(receiver_user_id, notification)])


def prepare_feature_error_notification(
    receiver_user_id: int, code: str, extra_info: Any
):
    notification = FeatureErrorNotification(code=code, extra_info=extra_info)
    return NotificationBatch([(receiver_user_id, notification)])


def prepare_chatroom_rename_notifications(
    members_ids: list[int], chatroom_id: int, by_user_data, name: str
):
    by_user = MemberOut.model_validate(by_user_data)
    notification = ChatroomRenameNotification(
        chatroom_id=chatroom_id, by_user=by_user, name=name
    )
    user_notification_tuples = [(member_id, notification) for member_id in members_ids]
    return NotificationBatch(user_notification_tuples)


def prepare_leave_notifications(members_ids: list[int], chatroom_id: int, user_data):
    user = MemberOut.model_validate(user_data)
    notification = LeaveNotification(user=user, chatroom_id=chatroom_id)
    user_notification_tuples = [(member_id, notification) for member_id in members_ids]
    return NotificationBatch(user_notification_tuples)


def prepare_add_member_notifications_on_create(
    members: list, chatroom_id: int, creator_data
):
    creator = MemberOut.model_validate(creator_data)

    def create_add_member_notification(
        member: MemberOut,
    ) -> AddMemberNotification:
        return AddMemberNotification(
            added_by_user=creator,
            added_user=MemberOut.model_validate(member),
            chatroom_id=chatroom_id,
        )

    user_notification_tuples = [
        (
            MemberOut.model_validate(member).id,
            create_add_member_notification(MemberOut.model_validate(member)),
        )
        for member in members
    ]
    return NotificationBatch(user_notification_tuples)


def prepare_add_member_notifications(
    members_ids: list[int], chatroom_id: int, added_by_user_data, added_user_data
):
    notification = AddMemberNotification(
        added_by_user=MemberOut.model_validate(added_by_user_data),
        added_user=MemberOut.model_validate(added_user_data),
        chatroom_id=chatroom_id,
    )
    user_notification_tuples = [(member_id, notification) for member_id in members_ids]
    return NotificationBatch(user_notification_tuples)


def prepare_remove_member_notifications(
    members_ids: list[int], chatroom_id: int, removed_by_user_data, removed_user_data
):
    notification = RemoveMemberNotification(
        removed_by_user=MemberOut.model_validate(removed_by_user_data),
        removed_user=MemberOut.model_validate(removed_user_data),
        chatroom_id=chatroom_id,
    )
    user_notification_tuples = [(member_id, notification) for member_id in members_ids]
    return NotificationBatch(user_notification_tuples)


def create_admin_status_notification(
    notification_class, by_user_data, to_user_data, chatroom_id
):
    by_user = MemberOut.model_validate(by_user_data)
    to_user = MemberOut.model_validate(to_user_data)
    return notification_class(by_user=by_user, to_user=to_user, chatroom_id=chatroom_id)


def prepare_make_admin_notifications(
    members_ids: list[int], chatroom_id: int, by_user_data, to_user_data
):
    notification = create_admin_status_notification(
        MakeAdminNotification, by_user_data, to_user_data, chatroom_id
    )
    user_notification_tuples = [(member_id, notification) for member_id in members_ids]
    return NotificationBatch(user_notification_tuples)


def prepare_remove_admin_notifications(
    members_ids: list[int], chatroom_id: int, by_user_data, to_user_data
):
    notification = create_admin_status_notification(
        RemoveAdminNotification, by_user_data, to_user_data, chatroom_id
    )
    user_notification_tuples = [(member_id, notification) for member_id in members_ids]
    return NotificationBatch(user_notification_tuples)


def prepare_cleaned_text_notification(
    receiver_user_id: int, essay_topic_id: int, cleaned_text: str, essay_topic_name: str
):
    notification = CleanedTextNotification(
        essay_topic_id=essay_topic_id, cleaned_text=cleaned_text
    )
    notification_batch = NotificationBatch([(receiver_user_id, notification)])
    fcm_service.send_notification(
        receiver_user_id,
        f"Extração da redação {essay_topic_name}",
        "Abra o app para pedir a correção da sua redação!",
    )
    return notification_batch


def prepare_essay_correction_notification(
    receiver_user_id: int,
    essay_topic_id: int,
    feedbacks: list[str],
    grades: list[float | None],
    essay_topic_name: str,
):
    notification = EssayCorrectionNotification(
        essay_topic_id=essay_topic_id, feedbacks=feedbacks, grades=grades
    )
    notification_batch = NotificationBatch([(receiver_user_id, notification)])
    fcm_service.send_notification(
        receiver_user_id,
        f"Correção da redação {essay_topic_name}",
        "Abra o app para ver a correção da sua redação!",
    )
    return notification_batch


def create_message_notification(message_data):
    return MessageNotification(
        chatroom_id=message_data.chatroom.id,
        message=MessageOut.model_validate(message_data),
    )


def prepare_message_data(message_data):
    embedded_file = (
        message_data.embedded_files.all()[0]
        if message_data.embedded_files.all()
        else None
    )
    essay_topic_id = message_data.essay_topic.id if message_data.essay_topic else None
    session_id = message_data.session.id if message_data.session else None
    attachment_url = embedded_file.file.url if embedded_file else None

    setattr(message_data, "attachment", attachment_url)
    setattr(
        message_data,
        "extra_object_id",
        essay_topic_id if essay_topic_id else session_id,
    )


def prepare_messages_notifications(messages_data: list):
    logger.debug(
        f"Preparing message NotificationBatch for {len(messages_data)} messages..."
    )
    user_notification_tuples: list[tuple[int, Notification]] = []
    for message_data in messages_data:
        prepare_message_data(message_data)
        notification = create_message_notification(message_data)

        for member in message_data.chatroom.members.all():
            user_id = member.id
            user_notification_tuples.append((user_id, notification))

    logger.debug(
        f"Prepared message NotificationBatch for {len(user_notification_tuples)} user-notification tuples"
    )

    return NotificationBatch(user_notification_tuples)
