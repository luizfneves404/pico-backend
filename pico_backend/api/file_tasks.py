import logging
import re

import celery.exceptions as celery_exceptions
import fitz
import pytesseract
import shared.file_utils as file_utils
from celery import chain as celery_chain
from celery import chord as celery_chord
from celery import shared_task
from commands.commands_utils.embeddings import group_embedded_text_chunks
from django.core.files import File as DjangoFile
from docx import Document
from PIL import Image
from shared import openai_utils
from shared.ai_utils import split_text_into_chunks

import api.services.message_service as message_service
from api.models import EmbeddedFile, EmbeddedTextChunk, Message
from pico_backend.celery import celery_async_workflow

logger = logging.getLogger(__name__)

TEXT_SPLITTING_CHUNK_SIZE = 128
MAX_CHARACTER_COUNT_FOR_FILE_PROCESSING = 2000000
FILE_TOO_BIG_MESSAGE = f"Desculpa, tem mais de {MAX_CHARACTER_COUNT_FOR_FILE_PROCESSING} caracteres esse arquivo.. não consigo ler tudo isso :("
FINISHED_READING_MESSAGE = "Já li! Pra tirar uma dúvida, clique no painel no botão Consulta e escolha o nome do documento que você mandou"
NO_TEXT_IN_FILE_MESSAGE = "Não consegui encontrar texto nesse arquivo."


def _smart_remove_linebreaks(text: str) -> str:
    pattern = re.compile(r"\n([a-z\s-])")
    cleaned_text = re.sub(pattern, " ", text)
    return cleaned_text


def _clean_text(text: str) -> str:
    linebreaks_removed = _smart_remove_linebreaks(text)
    return linebreaks_removed


@shared_task
def task_extract_and_save_text(embedded_file_id: int, validate_size: bool = True):
    embedded_file = EmbeddedFile.objects.get(id=embedded_file_id)
    logger.debug(f"Extracting text from file {embedded_file_id}...")
    text = extract_text(embedded_file.file.file)
    logger.info(
        f"Extracted {len(text)} characters of text from file {embedded_file_id}"
    )

    chatroom = embedded_file.chatroom

    if not text:
        if chatroom:
            message_service.send_message(
                sender="pico",
                chatroom=chatroom,
                content=NO_TEXT_IN_FILE_MESSAGE,
                have_embedding=False,
            )
        logger.warning(
            f"No text found when extracting from file {embedded_file_id}, skipping remaining processing tasks"
        )
        raise celery_exceptions.Ignore(f"No text found for file {embedded_file_id}")

    if validate_size:
        if len(text) > MAX_CHARACTER_COUNT_FOR_FILE_PROCESSING:
            if chatroom:
                message_service.send_message(
                    sender="pico",
                    chatroom=chatroom,
                    content=FILE_TOO_BIG_MESSAGE,
                    have_embedding=False,
                )
            logger.warning(
                f"File too large for processing: {len(text)} characters. Ignoring remaining processing tasks"
            )
            raise celery_exceptions.Ignore(
                f"File too large for processing: {len(text)} characters"
            )

    cleaned_text = _clean_text(text)

    embedded_file.text = cleaned_text
    embedded_file.save()


def extract_text(file: DjangoFile) -> str:
    mime_type = file_utils.get_mime_type(file)
    logger.debug(f"File to extract text has MIME type: {mime_type}")
    if mime_type == "application/pdf":
        return extract_text_from_pdf(file)
    elif mime_type in ["image/png", "image/jpeg"]:
        return extract_text_from_image(file)
    elif mime_type in [
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]:
        return extract_text_from_doc(file)
    elif mime_type == "text/plain":
        return extract_text_from_txt(file)
    else:
        raise ValueError(f"Unsupported MIME type: {mime_type}")


def extract_text_from_pdf(file: DjangoFile) -> str:
    opened_file = fitz.open("pdf", file.read())
    text = []
    for page in opened_file.pages():
        text.append(page.get_text())
    return "".join(text)


def extract_text_from_image(file: DjangoFile) -> str:
    with Image.open(file) as image:
        return pytesseract.image_to_string(image)


def extract_text_from_doc(file: DjangoFile) -> str:
    doc = Document(file)
    full_text = []
    for para in doc.paragraphs:
        full_text.append(para.text)
    return "\n".join(full_text)


def extract_text_from_txt(file: DjangoFile) -> str:
    text = []
    for chunk in file.chunks():
        text.append(chunk.decode("utf-8", errors="ignore"))
    return "".join(text)


@shared_task(
    rate_limit="20/m", ignore_result=False
)  # false because its part of a chord
def task_embed_and_save_text_chunk_group(text_chunk_ids: list[int]):
    embedded_text_chunk_group = list(
        EmbeddedTextChunk.objects.filter(id__in=text_chunk_ids).only(
            "text", "embedding"
        )
    )

    text_chunk_group = [chunk.text for chunk in embedded_text_chunk_group]

    embeddings_for_group = openai_utils.compute_embedding(text_chunk_group)

    for embedded_text_chunk, embedding in zip(
        embedded_text_chunk_group, embeddings_for_group
    ):
        embedded_text_chunk.embedding = embedding

    logger.debug(
        f"Updating {len(embedded_text_chunk_group)} embedded text chunks to save their embeddings..."
    )
    EmbeddedTextChunk.objects.bulk_update(embedded_text_chunk_group, ["embedding"])
    logger.info(
        f"Updated {len(embedded_text_chunk_group)} embedded text chunks to save their embeddings"
    )


@shared_task
def task_finalize_file_processing(embedded_file_id: int):
    embedded_file = EmbeddedFile.objects.get(id=embedded_file_id)
    embedded_file.file_processing_done = True
    embedded_file.save()


@shared_task
def task_send_completion_message(embedded_file_id: int):
    attachment_messages = (
        Message.objects.prefetch_related("chatroom__members")
        .select_related("chatroom")
        .filter(embedded_files__id=embedded_file_id)
    )
    if not attachment_messages.exists():
        return

    for attachment_message in attachment_messages:
        message_service.send_message(
            content=FINISHED_READING_MESSAGE,
            chatroom=attachment_message.chatroom,
            sender="pico",
            have_embedding=False,
        )
    logger.debug("PDF processing complete")


def embed_and_save_text_chunks(embedded_file_id: int, text_chunks: list[str]):
    embedded_text_chunks = [
        EmbeddedTextChunk(embedded_file_id=embedded_file_id, text=chunk)
        for chunk in text_chunks
    ]

    logger.debug(
        f"Saving {len(embedded_text_chunks)} embedded text chunks without embeddings..."
    )

    embedded_text_chunks_in_db = EmbeddedTextChunk.objects.bulk_create(
        embedded_text_chunks
    )

    logger.debug(
        f"Saved {len(embedded_text_chunks)} embedded text chunks without embeddings"
    )

    embed_and_save_tasks = [
        task_embed_and_save_text_chunk_group.s([chunk.id for chunk in group])
        for group in group_embedded_text_chunks(embedded_text_chunks_in_db)
    ]
    # Create the dynamic workflow
    dynamic_workflow = celery_chord(
        embed_and_save_tasks,
        celery_chain(
            task_finalize_file_processing.si(embedded_file_id),
            task_send_completion_message.si(embedded_file_id),
        ),
    )

    # Trigger the dynamic workflow
    dynamic_workflow.delay().forget()


@shared_task
def task_split_and_process_text(embedded_file_id: int):
    embedded_file = EmbeddedFile.objects.get(id=embedded_file_id)

    text = embedded_file.text
    if not text:
        raise celery_exceptions.Ignore(f"No text found for file {embedded_file_id}")
    text_chunks = split_text_into_chunks(text, TEXT_SPLITTING_CHUNK_SIZE)

    embed_and_save_text_chunks(embedded_file_id, text_chunks)


@celery_async_workflow
def process_file_async_workflow(embedded_file_id: int, validate_size: bool = True):
    processing_workflow = task_extract_and_save_text.s(
        embedded_file_id, validate_size
    ) | task_split_and_process_text.si(embedded_file_id)

    processing_workflow.apply_async().forget()
    logger.debug(f"Started process_file_async_workflow for file {embedded_file_id}")


def process_file_sync_workflow(embedded_file_id: int, validate_size: bool = True):
    processing_workflow = task_extract_and_save_text.s(
        embedded_file_id, validate_size
    ) | task_split_and_process_text.si(embedded_file_id)

    processing_workflow.apply_async().forget()
    logger.debug(f"Started process_file_sync_workflow for file {embedded_file_id}")
