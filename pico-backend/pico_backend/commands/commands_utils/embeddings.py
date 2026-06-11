import logging
from typing import Generator

from api.models import Chatroom, EmbeddedFile, EmbeddedTextChunk, FileGroup
from django.db.models import Q
from pgvector.django import CosineDistance
from shared import openai_utils

MAX_TOKENS_FOR_EMBEDDING_MODEL = 8192  # less than the max to give a buffer
MAX_ARRAY_LENGTH_FOR_EMBEDDING_API_CALL = 2048
logger = logging.getLogger(__name__)


def group_embedded_text_chunks(
    input_list: list[EmbeddedTextChunk],
) -> Generator[list[EmbeddedTextChunk], None, None]:
    """Group embedded text chunks based on token and array length limits so that separate requests can be made"""
    # use the group_text_chunks function
    group, current_tokens = [], 0
    for chunk in input_list:
        item_tokens = openai_utils.count_tokens(chunk.text)
        if (
            current_tokens + item_tokens >= MAX_TOKENS_FOR_EMBEDDING_MODEL
            or len(group) >= MAX_ARRAY_LENGTH_FOR_EMBEDDING_API_CALL
        ):
            yield group
            group, current_tokens = [], 0
        group.append(chunk)
        current_tokens += item_tokens
    if group:
        yield group


def search_similar_text_chunks_in_file(
    n: int, search_text: str, embedded_file: EmbeddedFile
):
    """Search for the n most similar text chunks for the attachment message, returning a queryset."""
    search_embedding = openai_utils.compute_embedding(search_text)

    similar_text_chunks = EmbeddedTextChunk.objects.filter(
        embedded_file=embedded_file
    ).order_by(CosineDistance("embedding", search_embedding))[:n]

    return similar_text_chunks


def search_similar_text_chunks_in_file_group(
    n: int, search_text: str, file_group: FileGroup
) -> list[tuple[str, str]]:
    """Search for the n most similar text chunks within the attachment messages, returning a list of tuples with filenames and text chunks."""
    search_embedding = openai_utils.compute_embedding(search_text)

    similar_text_chunks_queryset = (
        EmbeddedTextChunk.objects.filter(embedded_file__file_group=file_group)
        .select_related("embedded_file")
        .order_by(CosineDistance("embedding", search_embedding))[:n]
    )

    # Create a list of tuples (filename, text chunk)
    similar_text_chunks = [
        (chunk.embedded_file.file.name.split("/")[-1], chunk.text)
        for chunk in similar_text_chunks_queryset
    ]

    return similar_text_chunks


def search_similar_text_chunks_in_all_files(
    n: int, search_text: str, chatroom: Chatroom
) -> list[tuple[str, str]]:
    """Search for the n most similar text chunks within all global files and local files, returning a list of tuples with filenames and text chunks."""
    search_embedding = openai_utils.compute_embedding(search_text)

    similar_text_chunks_queryset = (
        EmbeddedTextChunk.objects.select_related("embedded_file")
        .filter(
            Q(embedded_file__messages__chatroom=chatroom)
            | Q(embedded_file__messages=None)
        )
        .order_by(CosineDistance("embedding", search_embedding))[:n]
    )

    # Create a list of tuples (filename, text chunk)
    similar_text_chunks = [
        (chunk.embedded_file.file.name.split("/")[-1], chunk.text)
        for chunk in similar_text_chunks_queryset
    ]

    return similar_text_chunks
