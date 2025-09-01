import copy
import logging
from collections.abc import Generator
from typing import (
    Literal,
    TypeVar,
    cast,
    overload,
)

import tiktoken
from openai.types.chat import (
    ChatCompletionMessageParam,
)
from openai.types.responses import (
    ResponseInputParam,
)
from openai.types.shared_params.reasoning import Reasoning
from pydantic import BaseModel

from app.shared.openai_service import openai_service

from .constants import (
    SYSTEM_MESSAGE_GENERATE_TRANSCRIPTION_FROM_IMAGE,
)

EMBEDDING_MODEL = "text-embedding-3-large"
NUMBER_OF_EMBEDDING_DIMENSIONS = 1024
MAX_CHARS_FOR_EMBEDDING_MODEL = 500000
EMBEDDING_BATCH_SIZE = 2048
JSONIFY_INFO_MODEL = "gpt-4o-mini"
JSONIFY_INFO_SYSTEM_MESSAGE = "Extraia a informação '{info}' do texto a seguir e "
"responda com um JSON contendo a chave '{json_key}' com o valor correspondente. "
"Se não houver {info}, ou por outro motivo não faça sentido extraí-la, "
"responda com o valor null para a chave."
DELATEXIFY_MODEL = "gpt-4o-mini"

# Models that support reasoning_effort parameter
REASONING_EFFORT_MODELS = ["o3-mini", "o3", "o4-mini", "gpt-5-mini", "gpt-5"]

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)

FEEDBACK_MODEL = "gpt-4o"

FEEDBACK_TIMEOUT = 90

# i wanted to use Pydantic AI (which has a testmodel implementation),
# but it does not support embeddings yet, so i built this to mock the real client

#############################################
# Helper: Message Sanitization (Minimal)
#############################################


def sanitize_messages_for_log(
    input: ResponseInputParam,  # noqa: A002
) -> ResponseInputParam:
    sanitized_messages: ResponseInputParam = []
    for input_item in input:
        if input_item.get("type") != "message":
            continue
        sanitized_message = copy.deepcopy(input_item)
        # Handle content if it's a list of content parts (multimodal messages)
        content = sanitized_message.get("content")
        if content and isinstance(content, list):
            for content_part in content:
                if content_part["type"] == "input_image":
                    image_url = content_part.get("image_url")
                    if isinstance(image_url, str):
                        content_part["image_url"] = "[IMAGE]"
        sanitized_messages.append(sanitized_message)
    return sanitized_messages


#############################################
# Image Transcription
#############################################


async def transcribe_image(image_url: str) -> str:
    """
    Generates a transcription for an image using OpenAI's vision model.
    """
    logger.info("Transcribing image with model=gpt-5-nano via Responses API")
    messages: list[ChatCompletionMessageParam] = [
        {
            "role": "system",
            "content": SYSTEM_MESSAGE_GENERATE_TRANSCRIPTION_FROM_IMAGE,
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": ""},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image_url,
                        "detail": "high",
                    },
                },
            ],
        },
    ]
    input_param: ResponseInputParam = cast(ResponseInputParam, messages)
    result = await openai_service.text(
        model="gpt-5-nano",
        input=input_param,
        temperature=0.0,
        reasoning=None,
    )
    logger.debug("Successfully transcribed image with url %s", image_url)
    return result


#############################################
# Embeddings
#############################################


@overload
async def compute_embedding(text: str) -> list[float]: ...


@overload
async def compute_embedding(text: list[str]) -> list[list[float]]: ...


async def compute_embedding(text: str | list[str]) -> list[float] | list[list[float]]:
    """
    Asynchronously computes and returns embeddings for text input.

    Args:
        text: Either a single string or a list of strings to embed

    Returns:
        For a single string: A list of floats representing the embedding vector
        For a list of strings: A list of embedding vectors (list of list of floats)
    """
    if isinstance(text, list):
        logger.info(
            "Async computing embeddings for %d texts with model=%s. "
            "The first 100 characters of the first text are: %s",
            len(text),
            EMBEDDING_MODEL,
            text[0][:100],
        )
        total: list[list[float]] = []
        for group in group_text_chunks(text):
            for item in group:
                validate_input(item)
            response = await openai_service.embed(
                model=EMBEDDING_MODEL,
                input=group,
                dimensions=NUMBER_OF_EMBEDDING_DIMENSIONS,
            )
            total.extend(response)
        logger.debug("Successfully computed embeddings for text list")
        return total
    else:
        logger.info(
            "Async computing embedding for single text with model=%s. "
            "The first 100 characters of the text are: %s",
            EMBEDDING_MODEL,
            text[:100],
        )
        validate_input(text)
        result = await openai_service.embed(
            model=EMBEDDING_MODEL,
            input=text,
            dimensions=NUMBER_OF_EMBEDDING_DIMENSIONS,
        )
        logger.debug("Successfully computed embedding for single text")
        return result


def validate_input(input_item: str):
    num_chars = len(input_item)
    if num_chars > MAX_CHARS_FOR_EMBEDDING_MODEL:
        raise ValueError(
            f"Input text exceeds the max token limit of {MAX_CHARS_FOR_EMBEDDING_MODEL}"
        )


def group_text_chunks(input_list: list[str]) -> Generator[list[str], None, None]:
    """Group text chunks based on char and array length limits so that separate requests
    can be made"""
    group: list[str] = []
    current_chars: int = 0
    logger.debug(
        "Computing embeddings for %d texts will have approximately %d requests if "
        "limited by batch size of %d. Will have approximately %d requests if "
        "limited by max chars of %d",
        len(input_list),
        len(input_list) / EMBEDDING_BATCH_SIZE,
        EMBEDDING_BATCH_SIZE,
        sum(len(item) for item in input_list) / MAX_CHARS_FOR_EMBEDDING_MODEL,
        MAX_CHARS_FOR_EMBEDDING_MODEL,
    )
    for item in input_list:
        item_chars = len(item)
        if (
            current_chars + item_chars >= MAX_CHARS_FOR_EMBEDDING_MODEL
            or len(group) >= EMBEDDING_BATCH_SIZE
        ):
            yield group
            group, current_chars = [], 0
        group.append(item)
        current_chars += item_chars
    if group:
        yield group


#############################################
# Token Counting
#############################################

encoding_cache: dict[str, tiktoken.Encoding] = {}


def count_tokens(text: str, model: str) -> int:
    if model not in encoding_cache:
        try:
            encoding_cache[model] = tiktoken.encoding_for_model(model)
        except KeyError:
            # Fallback for models not recognized by tiktoken
            # Use cl100k_base encoding which is used by GPT-4 models
            logger.warning(
                f"Model '{model}' not recognized by tiktoken, "
                "using 'cl100k_base' encoding as fallback"
            )
            encoding_cache[model] = tiktoken.get_encoding("cl100k_base")
    encoding = encoding_cache[model]
    return len(encoding.encode(text))


#############################################
# Image Generation
#############################################


async def generate_image(
    prompt: str,
    size: Literal["1024x1024", "1536x1024", "1024x1536"] = "1024x1024",
    quality: Literal["low", "medium", "high", "auto"] = "low",
    image_format: Literal["png", "jpeg", "webp"] = "jpeg",
) -> str:
    result = await openai_service.generate_image(
        prompt=prompt,
        size=size,
        quality=quality,
        image_format=image_format,
    )
    return result


async def get_completion(
    model: str,
    input: ResponseInputParam,  # noqa: A002
    reasoning: Reasoning | None = None,
    temperature: float | None = None,
) -> str:
    return await openai_service.text(
        model=model,
        temperature=temperature,
        input=input,
        reasoning=reasoning,
    )


async def get_completion_parsed(  # noqa: UP047
    model: str,
    input: ResponseInputParam,  # noqa: A002
    response_format: type[ModelT],
    reasoning: Reasoning | None = None,
    temperature: float | None = None,
) -> ModelT:
    return await openai_service.structured(
        model=model,
        input=input,
        reasoning=reasoning,
        temperature=temperature,
        response_model=response_format,
    )
