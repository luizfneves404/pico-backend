import logging

from semchunk import semchunk

from app.shared import openai_utils

logger = logging.getLogger(__name__)


def split_text_into_chunks(text: str, chunk_size: int, model: str) -> list[str]:
    logger.info(f"Splitting text into chunks of size {chunk_size}...")
    chunks = semchunk.chunk(
        text,
        chunk_size=chunk_size,
        token_counter=lambda text: openai_utils.count_tokens(text, model),
    )
    logger.info(f"Split text into {len(chunks)} chunk(s)")
    return chunks
