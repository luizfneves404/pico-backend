import copy
import json
import logging
import random
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Coroutine,
    Generator,
    Generic,
    Literal,
    TypeVar,
    overload,
)

import tiktoken
from openai import NOT_GIVEN, AsyncOpenAI, NotGiven, OpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
)
from pydantic import BaseModel

from app.config import settings

from .constants import (
    SYSTEM_MESSAGE_GENERATE_TRANSCRIPTION_FROM_IMAGE,
)

EMBEDDING_MODEL = "text-embedding-3-large"
NUMBER_OF_EMBEDDING_DIMENSIONS = 1024
MAX_TOKENS_FOR_EMBEDDING_MODEL = 4096  # less than the max to give a buffer
MAX_ARRAY_LENGTH_FOR_EMBEDDING_API_CALL = 2048
JSONIFY_INFO_MODEL = "gpt-4o-mini"
JSONIFY_INFO_SYSTEM_MESSAGE = "Extraia a informação '{info}' do texto a seguir e responda com um JSON contendo a chave '{json_key}' com o valor correspondente. Se não houver {info}, ou por outro motivo não faça sentido extraí-la, responda com o valor null para a chave."
DELATEXIFY_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT = 10
DEFAULT_MAX_RETRIES = 5
logger = logging.getLogger(__name__)

T = TypeVar("T")

ModelT = TypeVar("ModelT", bound=BaseModel)

FEEDBACK_MODEL = "gpt-4o"

FEEDBACK_TIMEOUT = 90


# Initialize OpenAI clients for sync and async operations
client = OpenAI(
    api_key=settings.openai_api_key,
    timeout=DEFAULT_TIMEOUT,
    max_retries=DEFAULT_MAX_RETRIES,
)
async_client = AsyncOpenAI(
    api_key=settings.openai_api_key,
    timeout=DEFAULT_TIMEOUT,
    max_retries=DEFAULT_MAX_RETRIES,
)


class CompletionResult(BaseModel, Generic[T]):
    content: T
    tokens_used: int


#############################################
# Helper: Message Sanitization (Minimal)
#############################################


def sanitize_messages_for_log(
    messages: list[ChatCompletionMessageParam],
) -> list[ChatCompletionMessageParam]:
    sanitized_messages: list[ChatCompletionMessageParam] = []
    for message in messages:
        sanitized_message = copy.deepcopy(message)
        # Handle content if it's a list of content parts (multimodal messages)
        content = sanitized_message.get("content")
        if content and isinstance(content, list):
            for idx, content_part in enumerate(content):
                if content_part.get("type") == "image_url":
                    # Safely access and modify image URL
                    image_url = content_part.get("image_url")
                    if isinstance(image_url, dict) and "url" in image_url:
                        sanitized_message["content"][idx]["image_url"]["url"] = (
                            "[IMAGE]"
                        )
        sanitized_messages.append(sanitized_message)
    return sanitized_messages


#############################################
# Chat Completions
#############################################


def get_completion(
    model: str,
    temperature: float,
    messages: list[ChatCompletionMessageParam],
    json_mode: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
) -> CompletionResult[str]:
    """
    Synchronous chat completion.
    """
    logger.info(
        "Calling sync chat completion with model=%s, temperature=%.2f for messages %s",
        model,
        temperature,
        sanitize_messages_for_log(messages),
    )
    return _openai_request(
        endpoint="chat_completion",
        model=model,
        temperature=temperature,
        messages=messages,
        json_mode=json_mode,
        timeout=timeout,
    )


async def aget_completion(
    model: str,
    temperature: float,
    messages: list[ChatCompletionMessageParam],
    json_mode: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
) -> CompletionResult[str]:
    """
    Asynchronous chat completion.
    """
    logger.info(
        "Calling async chat completion with model=%s, temperature=%.2f, messages=%s",
        model,
        temperature,
        sanitize_messages_for_log(messages),
    )
    return await _aopenai_request(
        endpoint="chat_completion",
        model=model,
        temperature=temperature,
        messages=messages,
        json_mode=json_mode,
        timeout=timeout,
        stream=False,
    )


def get_completion_parsed(
    model: str,
    messages: list[ChatCompletionMessageParam],
    response_format: type[ModelT],
    temperature: float | None = None,  # Agora é opcional
    timeout: int = DEFAULT_TIMEOUT,
    reasoning_effort: Literal["low", "medium", "high"] | None = None,
) -> CompletionResult[ModelT]:
    """
    Synchronous chat completion with structured (parsed) response.
    """
    logger.info(
        "Calling sync parsed chat completion with model=%s, temperature=%s, response_format=%s, messages=%s",
        model,
        "N/A" if temperature is None else f"{temperature:.2f}",
        response_format.__name__,
        sanitize_messages_for_log(messages),
    )
    if model == "o3-mini":
        if reasoning_effort is None:
            raise ValueError("o3-mini must have reasoning_effort")
        if temperature is not None:
            logger.warning("temperature is ignored for model o3-mini")

        return _openai_request(
            endpoint="chat_completion_parsed",
            model="o3-mini",
            temperature=NOT_GIVEN,
            messages=messages,
            response_format=response_format,
            json_mode=False,
            timeout=timeout,
            reasoning_effort=reasoning_effort,
        )
    else:
        if temperature is None:
            raise ValueError("temperature is required for models other than o3-mini")

        return _openai_request(
            endpoint="chat_completion_parsed",
            model=model,
            temperature=temperature,
            messages=messages,
            response_format=response_format,
            json_mode=False,
            timeout=timeout,
            reasoning_effort=None,
        )


async def aget_completion_parsed(
    model: str,
    messages: list[ChatCompletionMessageParam],
    response_format: type[ModelT],
    temperature: float | None = None,  # Agora é opcional
    timeout: int = DEFAULT_TIMEOUT,
    reasoning_effort: Literal["low", "medium", "high"] | None = None,
) -> CompletionResult[ModelT]:
    """
    Asynchronous chat completion with structured (parsed) response.
    """
    logger.info(
        "Calling async parsed chat completion with model=%s, temperature=%s, response_format=%s, messages=%s",
        model,
        "N/A" if temperature is None else f"{temperature:.2f}",
        response_format.__name__,
        sanitize_messages_for_log(messages),
    )
    if model == "o3-mini":
        if reasoning_effort is None:
            raise ValueError("o3-mini must have reasoning_effort")
        if temperature is not None:
            logger.warning("temperature is ignored for model o3-mini")

        return await _aopenai_request(
            endpoint="chat_completion_parsed",
            model="o3-mini",
            temperature=NOT_GIVEN,
            messages=messages,
            response_format=response_format,
            json_mode=False,
            timeout=timeout,
            reasoning_effort=reasoning_effort,
        )
    else:
        if temperature is None:
            raise ValueError("temperature is required for models other than o3-mini")

        return await _aopenai_request(
            endpoint="chat_completion_parsed",
            model=model,
            temperature=temperature,
            messages=messages,
            response_format=response_format,
            json_mode=False,
            timeout=timeout,
            reasoning_effort=None,
        )


async def stream_completion(
    model: str,
    temperature: float,
    messages: list[ChatCompletionMessageParam],
    timeout: int = DEFAULT_TIMEOUT,
) -> AsyncGenerator[str, None]:
    """
    Asynchronous stream of chat completion content.
    Yields text chunks as they arrive.
    """
    logger.info(
        "Starting async chat completion stream with model=%s, temperature=%.2f, messages=%s",
        model,
        temperature,
        sanitize_messages_for_log(messages),
    )
    generator = await _aopenai_request(
        endpoint="chat_completion",
        model=model,
        temperature=temperature,
        messages=messages,
        json_mode=False,
        timeout=timeout,
        stream=True,
    )
    async for chunk in generator:
        yield chunk


#############################################
# JSON Extraction via Chat
#############################################


def jsonify_info(
    raw_text: str,
    info: str,
    json_key: str,
    coerce_to: Callable[[Any], T],
    default_value: T,
) -> T:
    """Extracts a specific key's value from raw info via a chat prompt.

    Args:
        raw_text (str): The raw info to extract the value from.
        info (str): The name of the info you want to extract. The LLM should recognize this in the text
        json_key (str): The key that the LLM should return.
        coerce_to (Callable[[Any], T]): The function that coerces the value returned by the LLM to the desired type.
        default_value (T): The default value to return if the value is not found.

    Returns:
        T: The value extracted from the raw info.
    """
    logger.info(
        "Extracting info=%s with key=%s using model=%s",
        info,
        json_key,
        JSONIFY_INFO_MODEL,
    )
    response = _openai_request(
        endpoint="chat_completion",
        model=JSONIFY_INFO_MODEL,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": JSONIFY_INFO_SYSTEM_MESSAGE.format(
                    info=info, json_key=json_key
                ),
            },
            {"role": "user", "content": raw_text},
        ],
        json_mode=True,
        timeout=30,
    )
    try:
        data = json.loads(response.content)
        value = data.get(json_key)
        result = coerce_to(value) if value is not None else default_value
        logger.debug("Extracted value=%s for info=%s", result, info)
        return result
    except Exception as e:
        logger.error("Failed to parse JSON response: %s", e)
        return default_value


async def ajsonify_info(
    raw_text: str,
    info: str,
    json_key: str,
    coerce_to: Callable[[Any], T],
    default_value: T,
) -> T:
    """Extracts a specific key's value from raw info via a chat prompt asynchronously.

    Args:
        raw_text (str): The raw info to extract the value from.
        info (str): The name of the info you want to extract. The LLM should recognize this in the text
        json_key (str): The key that the LLM should return.
        coerce_to (Callable[[Any], T]): The function that coerces the value returned by the LLM to the desired type.
        default_value (T): The default value to return if the value is not found.

    Returns:
        T: The value extracted from the raw info.
    """
    logger.info(
        "Async extracting info=%s with key=%s using model=%s",
        info,
        json_key,
        JSONIFY_INFO_MODEL,
    )
    response = await _aopenai_request(
        endpoint="chat_completion",
        model=JSONIFY_INFO_MODEL,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": JSONIFY_INFO_SYSTEM_MESSAGE.format(
                    info=info, json_key=json_key
                ),
            },
            {"role": "user", "content": raw_text},
        ],
        json_mode=True,
        timeout=30,
        stream=False,
    )
    try:
        data = json.loads(response.content)
        value = data.get(json_key)
        result = coerce_to(value) if value is not None else default_value
        logger.debug("Extracted value=%s for info=%s", result, info)
        return result
    except Exception as e:
        logger.error("Failed to parse JSON response: %s", e)
        return default_value


#############################################
# Feedback and Grading
#############################################


def get_feedback(
    system_message: str,
    user_message: str,
    temperature: float,
) -> dict[str, Any]:
    """
    Retrieves feedback and extracts a numeric grade from the response.
    """
    logger.info(
        "Getting feedback with model=%s, temperature=%.2f, messages=%s",
        FEEDBACK_MODEL,
        temperature,
        sanitize_messages_for_log(
            [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message},
            ]
        ),
    )
    response = _openai_request(
        endpoint="chat_completion",
        model=FEEDBACK_MODEL,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ],
        json_mode=False,
        timeout=90,
    )
    grade = jsonify_info(response.content, "nota", "grade", float, 0.0)
    logger.debug("Generated feedback with grade=%.2f", grade)
    return {"feedback": response.content, "grade": grade}


async def get_grade(feedback_text: str) -> int:
    """
    Asynchronously extracts a numeric grade from feedback text.
    """
    logger.info("Extracting grade from feedback text")
    grade = await ajsonify_info(feedback_text, "nota", "grade", int, 0)
    logger.debug("Extracted grade=%d", grade)
    return grade


#############################################
# Image Transcription
#############################################


async def transcribe_image(image_url: str) -> str:
    """
    Generates a transcription for an image using OpenAI's vision model.
    """
    logger.info("Transcribing image with model=gpt-4o")
    response = await _aopenai_request(
        endpoint="chat_completion",
        model="gpt-4o",
        temperature=0.1,
        messages=[
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
        ],
        json_mode=False,
        timeout=60,
        stream=False,
    )
    if not response:
        logger.error("Empty response from OpenAI for image transcription")
        raise ValueError("Empty response from OpenAI for image transcription.")
    logger.debug("Successfully transcribed image")
    return response.content


#############################################
# Embeddings
#############################################


@overload
def compute_embedding(text: str) -> list[float]: ...


@overload
def compute_embedding(text: list[str]) -> list[list[float]]: ...


def compute_embedding(text: str | list[str]) -> list[float] | list[list[float]]:
    """
    Computes and returns embeddings for text input.

    Args:
        text: Either a single string or a list of strings to embed

    Returns:
        For a single string: A list of floats representing the embedding vector
        For a list of strings: A list of embedding vectors (list of list of floats)
    """
    if isinstance(text, list):
        logger.info(
            "Computing embeddings for %d texts with model=%s",
            len(text),
            EMBEDDING_MODEL,
        )
        total: list[list[float]] = []
        for group in group_text_chunks(text):
            for item in group:
                validate_input(item)
            response = _openai_request(
                endpoint="embeddings",
                model=EMBEDDING_MODEL,
                input_text=group,
                dimensions=NUMBER_OF_EMBEDDING_DIMENSIONS,
                timeout=DEFAULT_TIMEOUT,
            )
            total.extend(response)
        logger.debug("Successfully computed embeddings for text list")
        return total
    else:
        logger.info(
            "Computing embedding for single text with model=%s", EMBEDDING_MODEL
        )
        validate_input(text)
        result = _openai_request(
            endpoint="embeddings",
            model=EMBEDDING_MODEL,
            input_text=text,
            dimensions=NUMBER_OF_EMBEDDING_DIMENSIONS,
            timeout=DEFAULT_TIMEOUT,
        )
        logger.debug("Successfully computed embedding for single text")
        return result


@overload
async def acompute_embedding(text: str) -> list[float]: ...


@overload
async def acompute_embedding(text: list[str]) -> list[list[float]]: ...


async def acompute_embedding(text: str | list[str]) -> list[float] | list[list[float]]:
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
            "Async computing embeddings for %d texts with model=%s",
            len(text),
            EMBEDDING_MODEL,
        )
        total: list[list[float]] = []
        for group in group_text_chunks(text):
            for item in group:
                validate_input(item)
            response = await _aopenai_request(
                endpoint="embeddings",
                model=EMBEDDING_MODEL,
                input_text=group,
                dimensions=NUMBER_OF_EMBEDDING_DIMENSIONS,
                timeout=DEFAULT_TIMEOUT,
            )
            total.extend(response)
        logger.debug("Successfully computed embeddings for text list")
        return total
    else:
        logger.info(
            "Async computing embedding for single text with model=%s", EMBEDDING_MODEL
        )
        validate_input(text)
        result = await _aopenai_request(
            endpoint="embeddings",
            model=EMBEDDING_MODEL,
            input_text=text,
            dimensions=NUMBER_OF_EMBEDDING_DIMENSIONS,
            timeout=DEFAULT_TIMEOUT,
        )
        logger.debug("Successfully computed embedding for single text")
        return result


def validate_input(input_item: str):
    num_tokens = count_tokens(input_item)
    if num_tokens > MAX_TOKENS_FOR_EMBEDDING_MODEL:
        raise ValueError(
            f"Input text exceeds the max token limit of {MAX_TOKENS_FOR_EMBEDDING_MODEL}"
        )


def group_text_chunks(input_list: list[str]) -> Generator[list[str], None, None]:
    """Group text chunks based on token and array length limits so that separate requests can be made"""
    group: list[str] = []
    current_tokens: int = 0
    for item in input_list:
        item_tokens = count_tokens(item)
        if (
            current_tokens + item_tokens >= MAX_TOKENS_FOR_EMBEDDING_MODEL
            or len(group) >= MAX_ARRAY_LENGTH_FOR_EMBEDDING_API_CALL
        ):
            yield group
            group, current_tokens = [], 0
        group.append(item)
        current_tokens += item_tokens
    if group:
        yield group


#############################################
# Token Counting
#############################################


def count_tokens(text: str) -> int:
    encoding_cl100k_base = tiktoken.get_encoding("cl100k_base")
    return len(encoding_cl100k_base.encode(text))


#############################################
# OpenAI API
# This is needed so that we can mock in tests and runserver_mocked. It's useless, but don't delete!
#############################################


@overload
def _openai_request(
    *,
    endpoint: Literal["chat_completion"],
    model: str,
    temperature: float,
    messages: list[ChatCompletionMessageParam],
    json_mode: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
) -> CompletionResult[str]: ...


@overload
def _openai_request(
    *,
    endpoint: Literal["chat_completion_parsed"],
    model: str,  # Qualquer modelo exceto "o3-mini"
    temperature: float,
    messages: list[ChatCompletionMessageParam],
    response_format: type[ModelT],
    json_mode: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
    reasoning_effort: None = None,
) -> CompletionResult[ModelT]: ...


@overload
def _openai_request(
    *,
    endpoint: Literal["chat_completion_parsed"],
    model: Literal["o3-mini"],
    temperature: NotGiven = NOT_GIVEN,  # o3-mini não aceita temperature
    messages: list[ChatCompletionMessageParam],
    response_format: type[ModelT],
    reasoning_effort: Literal["low", "medium", "high"],
    json_mode: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
) -> CompletionResult[ModelT]: ...


@overload
def _openai_request(
    *,
    endpoint: Literal["embeddings"],
    model: str,
    input_text: str,
    dimensions: int | NotGiven = NOT_GIVEN,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[float]: ...


@overload
def _openai_request(
    *,
    endpoint: Literal["embeddings"],
    model: str,
    input_text: list[str],
    dimensions: int | NotGiven = NOT_GIVEN,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[list[float]]: ...


def _openai_request(
    *,
    endpoint: Literal["chat_completion", "chat_completion_parsed", "embeddings"],
    model: str,
    temperature: float | NotGiven = NOT_GIVEN,
    messages: list[ChatCompletionMessageParam] | None = None,
    response_format: type[ModelT] | type[NotGiven] = NotGiven,
    json_mode: bool = False,
    input_text: str | list[str] | None = None,
    dimensions: int | NotGiven = NOT_GIVEN,
    timeout: int = DEFAULT_TIMEOUT,
    reasoning_effort: Literal["low", "medium", "high"] | None = None,
) -> CompletionResult[ModelT] | CompletionResult[str] | list[float] | list[list[float]]:
    if endpoint == "chat_completion":
        if not messages:
            raise ValueError("messages is required for the chat_completion endpoint.")
        response = client.with_options(timeout=timeout).chat.completions.create(
            model=model,
            temperature=temperature,
            messages=messages,
            response_format={"type": "json_object"} if json_mode else {"type": "text"},
        )
        if response.usage is None:
            raise Exception("No usage data returned from OpenAI.")
        if response.choices[0].message.content is None:
            raise Exception("No content returned from OpenAI.")
        return CompletionResult(
            content=response.choices[0].message.content,
            tokens_used=response.usage.total_tokens,
        )
    elif endpoint == "chat_completion_parsed":
        if not messages:
            raise ValueError(
                "messages is required for the chat_completion_parsed endpoint."
            )

        # Handle the special case for o3-mini with reasoning_effort
        if model == "o3-mini" and reasoning_effort is not None:
            # Para o3-mini, não passamos temperature
            response = client.with_options(timeout=timeout).beta.chat.completions.parse(
                model=model,
                messages=messages,
                response_format=response_format,
                extra_headers={"X-Reasoning-Effort": reasoning_effort},
            )
        else:
            # Para outros modelos, passamos temperature normalmente
            if isinstance(temperature, NotGiven):
                raise ValueError(
                    "temperature is required for models other than o3-mini"
                )
            response = client.with_options(timeout=timeout).beta.chat.completions.parse(
                model=model,
                temperature=temperature,
                messages=messages,
                response_format=response_format,
            )

        if not response.choices or not response.choices[0].message.parsed:
            raise Exception("No parsed content returned from OpenAI.")
        if not response.usage:
            raise Exception("No usage data returned from OpenAI.")
        return CompletionResult(
            content=response.choices[0].message.parsed,
            tokens_used=response.usage.total_tokens,
        )
    elif endpoint == "embeddings":
        if input_text is None:
            raise ValueError("input_text is required for the embeddings endpoint.")
        response = client.embeddings.create(
            model=model,
            input=input_text,
            dimensions=dimensions,
        )
        if isinstance(input_text, str):
            return response.data[0].embedding
        else:
            return [item.embedding for item in response.data]
    else:
        raise ValueError(f"Unsupported endpoint: {endpoint}")


@overload
async def _aopenai_request(
    *,
    endpoint: Literal["chat_completion"],
    model: str,
    temperature: float,
    messages: list[ChatCompletionMessageParam],
    json_mode: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
    stream: Literal[False],
) -> CompletionResult[str]: ...


@overload
def _aopenai_request(
    *,
    endpoint: Literal["chat_completion"],
    model: str,
    temperature: float,
    messages: list[ChatCompletionMessageParam],
    json_mode: Literal[False] = False,
    timeout: int = DEFAULT_TIMEOUT,
    stream: Literal[True],
) -> Coroutine[Any, Any, AsyncGenerator[str, None]]: ...


@overload
async def _aopenai_request(
    *,
    endpoint: Literal["chat_completion_parsed"],
    model: str,  # Qualquer modelo exceto "o3-mini"
    temperature: float,
    messages: list[ChatCompletionMessageParam],
    response_format: type[ModelT],
    json_mode: Literal[False] = False,
    timeout: int = DEFAULT_TIMEOUT,
    reasoning_effort: None = None,
) -> CompletionResult[ModelT]: ...


@overload
async def _aopenai_request(
    *,
    endpoint: Literal["chat_completion_parsed"],
    model: Literal["o3-mini"],
    temperature: NotGiven = NOT_GIVEN,
    messages: list[ChatCompletionMessageParam],
    response_format: type[ModelT],
    reasoning_effort: Literal["low", "medium", "high"],
    json_mode: Literal[False] = False,
    timeout: int = DEFAULT_TIMEOUT,
) -> CompletionResult[ModelT]: ...


@overload
async def _aopenai_request(
    *,
    endpoint: Literal["embeddings"],
    model: str,
    input_text: str,
    dimensions: int | NotGiven = NOT_GIVEN,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[float]: ...


@overload
async def _aopenai_request(
    *,
    endpoint: Literal["embeddings"],
    model: str,
    input_text: list[str],
    dimensions: int | NotGiven = NOT_GIVEN,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[list[float]]: ...


async def _aopenai_request(
    *,
    endpoint: Literal["chat_completion", "chat_completion_parsed", "embeddings"],
    model: str,
    temperature: float | NotGiven = NOT_GIVEN,
    messages: list[ChatCompletionMessageParam] | None = None,
    response_format: type[ModelT] | type[NotGiven] = NotGiven,
    json_mode: bool = False,
    input_text: str | list[str] | None = None,
    dimensions: int | NotGiven = NOT_GIVEN,
    timeout: int = DEFAULT_TIMEOUT,
    stream: bool = False,
    reasoning_effort: Literal["low", "medium", "high"] | None = None,
) -> (
    CompletionResult[ModelT]
    | CompletionResult[str]
    | AsyncGenerator[str, None]
    | list[float]
    | list[list[float]]
):
    """
    Raw asynchronous wrapper around the OpenAI client.

    Supported endpoints:
      - "chat_completion": Regular chat completion.
          * If stream=True, returns an async generator yielding text chunks.
      - "chat_completion_parsed": Chat completion with parsing.
      - "embeddings": Compute embeddings (input_text required).
    """
    if endpoint == "chat_completion":
        if not messages:
            raise ValueError("messages is required for the chat_completion endpoint.")
        if stream:
            response_stream = await async_client.with_options(
                timeout=timeout
            ).chat.completions.create(
                model=model,
                temperature=temperature,
                messages=messages,
                stream=True,
            )

            async def generator() -> AsyncGenerator[str, None]:
                async for chunk in response_stream:
                    if chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content

            return generator()
        else:
            response = await async_client.with_options(
                timeout=timeout
            ).chat.completions.create(
                model=model,
                temperature=temperature,
                messages=messages,
                response_format=(
                    {"type": "json_object"} if json_mode else {"type": "text"}
                ),
            )
            if response.usage is None:
                raise Exception("No usage data returned from OpenAI.")
            if response.choices[0].message.content is None:
                raise Exception("No content returned from OpenAI.")
            return CompletionResult(
                content=response.choices[0].message.content,
                tokens_used=response.usage.total_tokens,
            )
    elif endpoint == "chat_completion_parsed":
        if not messages:
            raise ValueError(
                "messages is required for the chat_completion_parsed endpoint."
            )
        # Handle the special case for o3-mini with reasoning_effort
        if model == "o3-mini" and reasoning_effort is not None:
            # Para o3-mini, não passamos temperature
            response = await async_client.with_options(
                timeout=timeout
            ).beta.chat.completions.parse(
                model=model,
                messages=messages,
                response_format=response_format,
                extra_headers={"X-Reasoning-Effort": reasoning_effort},
            )
        else:
            # Para outros modelos, passamos temperature normalmente
            if isinstance(temperature, NotGiven):
                raise ValueError(
                    "temperature is required for models other than o3-mini"
                )
            response = await async_client.with_options(
                timeout=timeout
            ).beta.chat.completions.parse(
                model=model,
                temperature=temperature,
                messages=messages,
                response_format=response_format,
            )

        if not response.choices or not response.choices[0].message.parsed:
            raise Exception("No parsed content returned from OpenAI.")
        if response.usage is None:
            raise Exception("No usage data returned from OpenAI.")
        return CompletionResult(
            content=response.choices[0].message.parsed,
            tokens_used=response.usage.total_tokens,
        )
    elif endpoint == "embeddings":
        if input_text is None:
            raise ValueError("input_text is required for the embeddings endpoint.")
        response = await async_client.embeddings.create(
            model=model,
            input=input_text,
            dimensions=dimensions,
        )
        if isinstance(input_text, str):
            return response.data[0].embedding
        else:
            return [item.embedding for item in response.data]
    else:
        raise ValueError(f"Unsupported endpoint: {endpoint}")


@overload
def mock_openai_request(
    *,
    endpoint: Literal["chat_completion"],
    model: str,
    temperature: float,
    messages: list[ChatCompletionMessageParam],
    json_mode: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
) -> CompletionResult[str]: ...


@overload
def mock_openai_request(
    *,
    endpoint: Literal["chat_completion_parsed"],
    model: str,  # Qualquer modelo exceto "o3-mini"
    temperature: float,
    messages: list[ChatCompletionMessageParam],
    response_format: type[ModelT],
    json_mode: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
    reasoning_effort: None = None,
) -> CompletionResult[ModelT]: ...


@overload
def mock_openai_request(
    *,
    endpoint: Literal["chat_completion_parsed"],
    model: Literal["o3-mini"],
    temperature: NotGiven = NOT_GIVEN,
    messages: list[ChatCompletionMessageParam],
    response_format: type[ModelT],
    reasoning_effort: Literal["low", "medium", "high"],
    json_mode: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
) -> CompletionResult[ModelT]: ...


@overload
def mock_openai_request(
    *,
    endpoint: Literal["embeddings"],
    model: str,
    input_text: str,
    dimensions: int | NotGiven = NOT_GIVEN,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[float]: ...


@overload
def mock_openai_request(
    *,
    endpoint: Literal["embeddings"],
    model: str,
    input_text: list[str],
    dimensions: int | NotGiven = NOT_GIVEN,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[list[float]]: ...


def mock_openai_request(
    *,
    endpoint: Literal["chat_completion", "chat_completion_parsed", "embeddings"],
    model: str,
    messages: list[ChatCompletionMessageParam] | None = None,
    response_format: type[ModelT] | type[NotGiven] = NotGiven,
    temperature: float | NotGiven = NOT_GIVEN,
    json_mode: bool = False,
    input_text: str | list[str] | None = None,
    dimensions: int | NotGiven = NOT_GIVEN,
    timeout: int = DEFAULT_TIMEOUT,
    reasoning_effort: Literal["low", "medium", "high"] | None = None,
) -> CompletionResult[ModelT] | CompletionResult[str] | list[float] | list[list[float]]:
    if endpoint == "chat_completion":
        if not messages:
            raise ValueError("messages is required for the chat_completion endpoint.")
        # Create a unique mock identifier
        mock_id = f"mock_{model}_{temperature}_{hash(str(messages))}"
        # Use json_mode to determine the output format
        content = (
            f'{{"content": "Mocked response for {mock_id}"}}'
            if json_mode
            else f"Mocked response for {mock_id}"
        )
        return CompletionResult(
            content=content,
            tokens_used=42,
        )
    elif endpoint == "chat_completion_parsed":
        if not messages:
            raise ValueError(
                "messages is required for the chat_completion_parsed endpoint."
            )

        def get_mock_value(field_info: Any) -> Any:
            annotation = field_info.annotation

            # Handle basic types
            if isinstance(annotation, type) and annotation is str:
                return "mocked_value"
            elif isinstance(annotation, type) and annotation is int:
                return 1
            elif isinstance(annotation, type) and annotation is float:
                return 1.0
            elif isinstance(annotation, type) and annotation is bool:
                return True

            # Handle lists
            if str(annotation).startswith("list"):
                inner_type = field_info.annotation.__args__[0]
                if hasattr(inner_type, "model_fields"):
                    return [mock_nested_model(inner_type)]
                return [
                    get_mock_value(type("FieldInfo", (), {"annotation": inner_type})())
                ]

            # Handle nested Pydantic models
            if hasattr(annotation, "model_fields"):
                return mock_nested_model(annotation)

            return "mocked_value"

        def mock_nested_model(model_class: type[BaseModel]) -> BaseModel:
            fields_dict = {}
            for field, field_info in model_class.model_fields.items():
                fields_dict[field] = get_mock_value(field_info)
            return model_class(**fields_dict)

        if issubclass(response_format, BaseModel):
            fields_dict = {}
            for field, field_info in response_format.model_fields.items():
                fields_dict[field] = get_mock_value(field_info)
            return CompletionResult(
                content=response_format(**fields_dict), tokens_used=42
            )
        else:
            raise ValueError("response_format must be a Pydantic model.")
    elif endpoint == "embeddings":
        if input_text is None:
            raise ValueError("input_text is required for the embeddings endpoint.")
        if isinstance(dimensions, NotGiven):
            dimensions = 3072  # Default OpenAI embedding dimension

        def generate_embedding() -> list[float]:
            return [random.random() for _ in range(dimensions)]

        if isinstance(input_text, str):
            return generate_embedding()
        else:
            return [generate_embedding() for _ in input_text]
    else:
        raise ValueError(f"Unsupported endpoint: {endpoint}")


@overload
async def mock_aopenai_request(
    *,
    endpoint: Literal["chat_completion"],
    model: str,
    temperature: float,
    messages: list[ChatCompletionMessageParam],
    json_mode: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
    stream: Literal[False],
) -> CompletionResult[str]: ...


@overload
def mock_aopenai_request(
    *,
    endpoint: Literal["chat_completion"],
    model: str,
    temperature: float,
    messages: list[ChatCompletionMessageParam],
    json_mode: Literal[False] = False,
    timeout: int = DEFAULT_TIMEOUT,
    stream: Literal[True],
) -> Coroutine[Any, Any, AsyncGenerator[str, None]]: ...


@overload
async def mock_aopenai_request(
    *,
    endpoint: Literal["chat_completion_parsed"],
    model: str,  # Qualquer modelo exceto "o3-mini"
    temperature: float,
    messages: list[ChatCompletionMessageParam],
    response_format: type[ModelT],
    json_mode: Literal[False] = False,
    timeout: int = DEFAULT_TIMEOUT,
    reasoning_effort: None = None,
) -> CompletionResult[ModelT]: ...


@overload
async def mock_aopenai_request(
    *,
    endpoint: Literal["chat_completion_parsed"],
    model: Literal["o3-mini"],
    temperature: NotGiven = NOT_GIVEN,
    messages: list[ChatCompletionMessageParam],
    response_format: type[ModelT],
    reasoning_effort: Literal["low", "medium", "high"],
    json_mode: Literal[False] = False,
    timeout: int = DEFAULT_TIMEOUT,
) -> CompletionResult[ModelT]: ...


@overload
async def mock_aopenai_request(
    *,
    endpoint: Literal["embeddings"],
    model: str,
    input_text: str,
    dimensions: int | NotGiven = NOT_GIVEN,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[float]: ...


@overload
async def mock_aopenai_request(
    *,
    endpoint: Literal["embeddings"],
    model: str,
    input_text: list[str],
    dimensions: int | NotGiven = NOT_GIVEN,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[list[float]]: ...


async def mock_aopenai_request(
    *,
    endpoint: Literal["chat_completion", "chat_completion_parsed", "embeddings"],
    model: str,
    temperature: float | NotGiven = NOT_GIVEN,
    messages: list[ChatCompletionMessageParam] | None = None,
    response_format: type[ModelT] | type[NotGiven] = NotGiven,
    json_mode: bool = False,
    input_text: str | list[str] | None = None,
    dimensions: int | NotGiven = NOT_GIVEN,
    timeout: int = DEFAULT_TIMEOUT,
    stream: bool = False,
    reasoning_effort: Literal["low", "medium", "high"] | None = None,
) -> (
    CompletionResult[ModelT]
    | CompletionResult[str]
    | AsyncGenerator[str, None]
    | list[float]
    | list[list[float]]
):
    if endpoint == "chat_completion":
        if not messages:
            raise ValueError("messages is required for the chat_completion endpoint.")

        if stream:
            mock_id = f"mock_stream_{model}_{temperature}_{hash(str(messages))}"

            async def generator() -> AsyncGenerator[str, None]:
                # Generate numbered chunks
                for i in range(1, 6):
                    yield f"Mocked chunk {i} for {mock_id}"

            return generator()
        else:
            mock_id = f"mock_{model}_{temperature}_{hash(str(messages))}"
            # Use json_mode to determine the output format
            content = (
                f'{{"content": "Mocked response for {mock_id}"}}'
                if json_mode
                else f"Mocked response for {mock_id}"
            )
            return CompletionResult(
                content=content,
                tokens_used=42,
            )
    elif endpoint == "chat_completion_parsed":
        if not messages:
            raise ValueError(
                "messages is required for the chat_completion_parsed endpoint."
            )

        def get_mock_value(field_info: Any) -> Any:
            annotation = field_info.annotation

            # Handle basic types
            if isinstance(annotation, type) and annotation is str:
                return "mocked_value"
            elif isinstance(annotation, type) and annotation is int:
                return 1
            elif isinstance(annotation, type) and annotation is float:
                return 1.0
            elif isinstance(annotation, type) and annotation is bool:
                return True

            # Handle lists
            if str(annotation).startswith("list"):
                inner_type = field_info.annotation.__args__[0]
                if hasattr(inner_type, "model_fields"):
                    return [mock_nested_model(inner_type)]
                return [
                    get_mock_value(type("FieldInfo", (), {"annotation": inner_type})())
                ]

            # Handle nested Pydantic models
            if hasattr(annotation, "model_fields"):
                return mock_nested_model(annotation)

            return "mocked_value"

        def mock_nested_model(model_class: type[BaseModel]) -> BaseModel:
            fields_dict = {}
            for field, field_info in model_class.model_fields.items():
                fields_dict[field] = get_mock_value(field_info)
            return model_class(**fields_dict)

        if issubclass(response_format, BaseModel):
            fields_dict = {}
            for field, field_info in response_format.model_fields.items():
                fields_dict[field] = get_mock_value(field_info)
            return CompletionResult(
                content=response_format(**fields_dict), tokens_used=42
            )
        else:
            raise ValueError("response_format must be a Pydantic model.")
    elif endpoint == "embeddings":
        if input_text is None:
            raise ValueError("input_text is required for the embeddings endpoint.")
        if isinstance(dimensions, NotGiven):
            dimensions = 3072

        def generate_embedding() -> list[float]:
            return [random.random() for _ in range(dimensions)]

        if isinstance(input_text, str):
            return generate_embedding()
        else:
            return [generate_embedding() for _ in input_text]
    else:
        raise ValueError(f"Unsupported endpoint: {endpoint}")
