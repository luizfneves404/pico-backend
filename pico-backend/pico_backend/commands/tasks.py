import logging

from api.models import Chatroom, Message
from celery import shared_task

import pico_backend.amp as pico_backend_amp
from commands.commands_utils.common import CommandRegistry
from pico_backend.celery import celery_async_workflow

logger = logging.getLogger(__name__)

COMMAND_EVENT_TYPE = "Send Command"


def handle_command(
    message_content: str,
    chatroom_id: int,
    parent_message_id: int | None,
    user_id: int,
):
    """
    Handles command processing.
    """
    command_prefix = message_content.strip().split(" ")[0]
    chatroom = Chatroom.objects.prefetch_related("members").get(id=chatroom_id)
    user = chatroom.members.get(id=user_id)
    parent_message = (
        Message.objects.get(id=parent_message_id, chatroom=chatroom)
        if parent_message_id
        else None
    )
    handler = CommandRegistry.get_handler(
        command_prefix,
        chatroom=chatroom,
        parent_message=parent_message,
        query=message_content,
        user=user,
    )
    if handler:
        handler.handle()
        pico_backend_amp.track_amplitude_event(
            user.id,
            COMMAND_EVENT_TYPE,
            {
                "chatroom_id": chatroom.id,
                "command": command_prefix,
            },
        )


@shared_task
def task_handle_command(
    message_content: str,
    chatroom_id: int,
    parent_message_id: int | None,
    user_id: int,
):
    handle_command(message_content, chatroom_id, parent_message_id, user_id)


@celery_async_workflow
def handle_command_workflow(
    message_content: str,
    chatroom_id: int,
    parent_message_id: int | None,
    user_id: int,
):
    """
    Handles command processing.
    """
    task_handle_command.delay(
        message_content, chatroom_id, parent_message_id, user_id
    ).forget()
