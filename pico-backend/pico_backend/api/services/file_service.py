import logging

import api.file_tasks as file_tasks
import shared.file_utils as file_utils
from api.models import Chatroom, EmbeddedFile, FileGroup
from django.core.files import File as DjangoFile

MIME_TYPES_TO_PROCESS = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}

logger = logging.getLogger(__name__)


async def list_files_for_chatroom(chatroom: Chatroom) -> list[EmbeddedFile]:
    return [
        file
        async for file in EmbeddedFile.objects.filter(
            messages__chatroom=chatroom
        ).order_by("id")
    ]


async def list_file_groups() -> list[FileGroup]:
    return [file_group async for file_group in FileGroup.objects.all()]


def embed_and_add_text_chunks_to_file(embedded_file_id: int, text_chunks: list[str]):
    file_tasks.embed_and_save_text_chunks(embedded_file_id, text_chunks)


def check_file_should_be_processed(mime_type: str) -> bool:
    return mime_type in MIME_TYPES_TO_PROCESS


async def process_local_file(embedded_file_id: int):
    await file_tasks.process_file_async_workflow(embedded_file_id, True)


def handle_global_file(embedded_file_id: int, file_like: DjangoFile):
    mime_type = file_utils.get_mime_type(file_like)
    if mime_type in MIME_TYPES_TO_PROCESS:
        logger.info(f"Processing file {embedded_file_id} as global file...")
        file_tasks.process_file_sync_workflow(embedded_file_id, False)
