import logging

import notifications.utils as notifications_utils
from api.models import Message
from celery import shared_task
from pico_backend.celery import celery_async_workflow
from shared import openai_utils

from app.config import settings

API_KEY = settings.openai_api_key
NUMBER_OF_SIMILAR_EMBEDDINGS = 4
NUMBER_OF_SIMILAR_TEXT_CHUNK_EMBEDDINGS = 4

BULK_MESSAGE_BATCH_SIZE = 100

logger = logging.getLogger(__name__)


def add_embedding_to_message(message_id: int, content: str):
    message = Message.objects.get(id=message_id)
    logger.debug(f"Adding embedding to message '{message.content}'")
    message.embedding = openai_utils.compute_embedding(content)
    message.save()
    logger.debug(f"Added embedding to message '{message.content}'")


@shared_task
def task_add_embedding_to_message(message_id: int, content: str):
    add_embedding_to_message(message_id, content)


@celery_async_workflow
def add_embedding_to_message_async_workflow(message_id: int, content: str):
    task_add_embedding_to_message.s(message_id, content).apply_async(
        countdown=5
    ).forget()


def add_embedding_to_message_sync_workflow(message_id: int, content: str):
    task_add_embedding_to_message.s(message_id, content).apply_async(
        countdown=5
    ).forget()


@shared_task
def task_bulk_notify_messages(message_ids: list[int]):
    logger.debug(f"Starting task_bulk_notify_messages for messages: {message_ids}")
    messages = Message.objects.prefetch_for_notification().filter(id__in=message_ids)
    messages = [message for message in messages]
    notifications_utils.prepare_messages_notifications(messages).send_sync()

    logger.debug(f"Finished task_bulk_notify_messages for {len(messages)} messages")


@shared_task
def task_bulk_embed_messages(message_ids: list[int]):
    logger.debug(f"Starting task_bulk_embed_messages for messages: {message_ids}")
    messages = Message.objects.filter(id__in=message_ids)

    # Get unique contents
    unique_contents = list(set(message.content for message in messages))

    # Create embeddings only for unique contents
    embeddings = openai_utils.compute_embedding(unique_contents)

    # Create a dictionary mapping content to embedding
    content_to_embedding = dict(zip(unique_contents, embeddings))

    # Assign correct embeddings to messages
    messages_to_update = [
        Message(id=message.id, embedding=content_to_embedding[message.content])
        for message in messages
    ]

    # Update all messages in one go
    Message.objects.bulk_update(messages_to_update, ["embedding"])

    logger.debug(f"Finished task_bulk_embed_messages for {len(messages)} messages")


def bulk_notify_messages_sync_workflow(message_ids: list[int]):
    task_bulk_notify_messages.delay(
        message_ids,
    ).forget()
