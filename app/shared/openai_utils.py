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
from openai import NOT_GIVEN, AsyncOpenAI, NotGiven
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

# Models that support reasoning_effort parameter
REASONING_EFFORT_MODELS = ["o3-mini", "o3", "o4-mini"]

logger = logging.getLogger(__name__)

T = TypeVar("T")

ModelT = TypeVar("ModelT", bound=BaseModel)

FEEDBACK_MODEL = "gpt-4o"

FEEDBACK_TIMEOUT = 90

async_client = AsyncOpenAI(
    api_key=settings.openai_api_key,
    timeout=DEFAULT_TIMEOUT,
    max_retries=DEFAULT_MAX_RETRIES,
)


class CompletionResult(BaseModel, Generic[T]):
    content: T
    tokens_used: int


@overload
async def _openai_request(
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
def _openai_request(
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
async def _openai_request(
    *,
    endpoint: Literal["chat_completion_parsed"],
    model: str,  # Qualquer modelo que não suporte reasoning_effort
    temperature: float,
    messages: list[ChatCompletionMessageParam],
    response_format: type[ModelT],
    json_mode: Literal[False] = False,
    timeout: int = DEFAULT_TIMEOUT,
    reasoning_effort: None = None,
) -> CompletionResult[ModelT]: ...


@overload
async def _openai_request(
    *,
    endpoint: Literal["chat_completion_parsed"],
    model: str,  # Modelos que suportam reasoning_effort
    temperature: NotGiven = NOT_GIVEN,
    messages: list[ChatCompletionMessageParam],
    response_format: type[ModelT],
    reasoning_effort: Literal["low", "medium", "high"],
    json_mode: Literal[False] = False,
    timeout: int = DEFAULT_TIMEOUT,
) -> CompletionResult[ModelT]: ...


@overload
async def _openai_request(
    *,
    endpoint: Literal["embeddings"],
    model: str,
    input_text: str,
    dimensions: int | NotGiven = NOT_GIVEN,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[float]: ...


@overload
async def _openai_request(
    *,
    endpoint: Literal["embeddings"],
    model: str,
    input_text: list[str],
    dimensions: int | NotGiven = NOT_GIVEN,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[list[float]]: ...


async def _openai_request(
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
    logger.debug("Official OpenAI request happening...")
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
        # Handle models that support reasoning_effort
        if model in REASONING_EFFORT_MODELS and reasoning_effort is not None:
            # Para modelos com reasoning_effort, não passamos temperature
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
                    f"temperature is required for models that don't support reasoning_effort. Model: {model}"
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
async def _mock_openai_request(
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
def _mock_openai_request(
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
async def _mock_openai_request(
    *,
    endpoint: Literal["chat_completion_parsed"],
    model: str,  # Qualquer modelo que não suporte reasoning_effort
    temperature: float,
    messages: list[ChatCompletionMessageParam],
    response_format: type[ModelT],
    json_mode: Literal[False] = False,
    timeout: int = DEFAULT_TIMEOUT,
    reasoning_effort: None = None,
) -> CompletionResult[ModelT]: ...


@overload
async def _mock_openai_request(
    *,
    endpoint: Literal["chat_completion_parsed"],
    model: str,  # Modelos que suportam reasoning_effort
    temperature: NotGiven = NOT_GIVEN,
    messages: list[ChatCompletionMessageParam],
    response_format: type[ModelT],
    reasoning_effort: Literal["low", "medium", "high"],
    json_mode: Literal[False] = False,
    timeout: int = DEFAULT_TIMEOUT,
) -> CompletionResult[ModelT]: ...


@overload
async def _mock_openai_request(
    *,
    endpoint: Literal["embeddings"],
    model: str,
    input_text: str,
    dimensions: int | NotGiven = NOT_GIVEN,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[float]: ...


@overload
async def _mock_openai_request(
    *,
    endpoint: Literal["embeddings"],
    model: str,
    input_text: list[str],
    dimensions: int | NotGiven = NOT_GIVEN,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[list[float]]: ...


async def _mock_openai_request(
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
    logger.debug("Mocked OpenAI request...")
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


openai_request = _mock_openai_request if settings.mock_openai else _openai_request

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
                        sanitized_message["content"][idx]["image_url"][
                            "url"
                        ] = "[IMAGE]"
        sanitized_messages.append(sanitized_message)
    return sanitized_messages


#############################################
# Chat Completions
#############################################


@overload
async def get_completion(
    model: str,
    temperature: float,
    messages: list[ChatCompletionMessageParam],
    json_mode: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
    reasoning_effort: None = None,
) -> CompletionResult[str]: ...


@overload
async def get_completion(
    model: str,
    temperature: None,
    messages: list[ChatCompletionMessageParam],
    json_mode: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
    *,
    reasoning_effort: Literal["low", "medium", "high"],
) -> CompletionResult[str]: ...


async def get_completion(
    model: str,
    temperature: float | None,
    messages: list[ChatCompletionMessageParam],
    json_mode: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
    reasoning_effort: Literal["low", "medium", "high"] | None = None,
) -> CompletionResult[str]:
    """
    Asynchronous chat completion with optional reasoning effort support.

    Args:
        model: Model name to use
        temperature: Temperature for randomness (ignored for reasoning models when reasoning_effort is used)
        messages: Chat messages
        json_mode: Whether to use JSON mode
        timeout: Request timeout
        reasoning_effort: Optional reasoning effort for supported models (o3, o3-mini, o4-mini)

    Returns:
        CompletionResult with string content
    """
    # Handle reasoning effort models
    if model in REASONING_EFFORT_MODELS and reasoning_effort is not None:
        if temperature is not None:
            logger.warning(
                f"temperature is ignored for reasoning models with reasoning_effort: {REASONING_EFFORT_MODELS}"
            )

        logger.info(
            "Calling async chat completion with reasoning effort: model=%s, reasoning_effort=%s, messages=%s",
            model,
            reasoning_effort,
            sanitize_messages_for_log(messages),
        )

        # For reasoning models, we need to use the regular chat completion endpoint
        # with reasoning effort header
        response = await async_client.with_options(
            timeout=timeout
        ).chat.completions.create(
            model=model,
            messages=messages,
            response_format=(
                {"type": "json_object"} if json_mode else {"type": "text"}
            ),
            extra_headers={"X-Reasoning-Effort": reasoning_effort},
        )

        if response.usage is None:
            raise Exception("No usage data returned from OpenAI.")
        if response.choices[0].message.content is None:
            raise Exception("No content returned from OpenAI.")

        return CompletionResult(
            content=response.choices[0].message.content,
            tokens_used=response.usage.total_tokens,
        )

    # Regular completion (original behavior)
    else:
        if temperature is None:
            raise ValueError("temperature is required for regular completions")

        logger.info(
            "Calling async chat completion with model=%s, temperature=%.2f, messages=%s",
            model,
            temperature,
            sanitize_messages_for_log(messages),
        )
        return await openai_request(
            endpoint="chat_completion",
            model=model,
            temperature=temperature,
            messages=messages,
            json_mode=json_mode,
            timeout=timeout,
            stream=False,
        )


async def get_completion_parsed(
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
    if model in REASONING_EFFORT_MODELS:
        if reasoning_effort is None:
            raise ValueError(
                f"Models {REASONING_EFFORT_MODELS} must have reasoning_effort parameter"
            )
        if temperature is not None:
            logger.warning(
                f"temperature is ignored for reasoning models: {REASONING_EFFORT_MODELS}"
            )

        return await openai_request(
            endpoint="chat_completion_parsed",
            model=model,
            temperature=NOT_GIVEN,
            messages=messages,
            response_format=response_format,
            json_mode=False,
            timeout=timeout,
            reasoning_effort=reasoning_effort,
        )
    else:
        if temperature is None:
            raise ValueError(
                f"temperature is required for models that don't support reasoning_effort. Model: {model}"
            )

        return await openai_request(
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
    generator = await openai_request(
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


async def jsonify_info(
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
    response = await openai_request(
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


async def get_feedback(
    system_message: str,
    user_message: str,
    temperature: float,
) -> dict[str, Any]:
    """
    Retrieves feedback and extracts a numeric grade from the response.
    """
    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message},
    ]
    logger.info(
        "Getting feedback with model=%s, temperature=%.2f, messages=%s",
        FEEDBACK_MODEL,
        temperature,
        sanitize_messages_for_log(messages),
    )
    response = await openai_request(
        endpoint="chat_completion",
        model=FEEDBACK_MODEL,
        temperature=temperature,
        messages=messages,
        json_mode=False,
        timeout=90,
        stream=False,
    )
    grade = jsonify_info(response.content, "nota", "grade", float, 0.0)
    logger.debug("Generated feedback with grade=%.2f", grade)
    return {"feedback": response.content, "grade": grade}


async def get_grade(feedback_text: str) -> int:
    """
    Asynchronously extracts a numeric grade from feedback text.
    """
    logger.info("Extracting grade from feedback text")
    grade = await jsonify_info(feedback_text, "nota", "grade", int, 0)
    logger.debug("Extracted grade=%d", grade)
    return grade


#############################################
# Image Transcription
#############################################


async def transcribe_image(image_url: str) -> str:
    """
    Generates a transcription for an image using OpenAI's vision model.
    """
    logger.info("Transcribing image with model=gpt-4.1-nano")
    response = await openai_request(
        endpoint="chat_completion",
        model="gpt-4.1-nano",
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
            "Async computing embeddings for %d texts with model=%s. The first 100 characters of the first text are: %s",
            len(text),
            EMBEDDING_MODEL,
            text[0][:100],
        )
        total: list[list[float]] = []
        for group in group_text_chunks(text):
            for item in group:
                validate_input(item, EMBEDDING_MODEL)
            response = await openai_request(
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
            "Async computing embedding for single text with model=%s. The first 100 characters of the text are: %s",
            EMBEDDING_MODEL,
            text[:100],
        )
        validate_input(text, EMBEDDING_MODEL)
        result = await openai_request(
            endpoint="embeddings",
            model=EMBEDDING_MODEL,
            input_text=text,
            dimensions=NUMBER_OF_EMBEDDING_DIMENSIONS,
            timeout=DEFAULT_TIMEOUT,
        )
        logger.debug("Successfully computed embedding for single text")
        return result


def validate_input(input_item: str, model: str):
    num_tokens = count_tokens(input_item, model)
    if num_tokens > MAX_TOKENS_FOR_EMBEDDING_MODEL:
        raise ValueError(
            f"Input text exceeds the max token limit of {MAX_TOKENS_FOR_EMBEDDING_MODEL}"
        )


def group_text_chunks(input_list: list[str]) -> Generator[list[str], None, None]:
    """Group text chunks based on token and array length limits so that separate requests can be made"""
    group: list[str] = []
    current_tokens: int = 0
    for item in input_list:
        item_tokens = count_tokens(item, EMBEDDING_MODEL)
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

encoding_cache: dict[str, tiktoken.Encoding] = {}


def count_tokens(text: str, model: str) -> int:
    if model not in encoding_cache:
        encoding_cache[model] = tiktoken.encoding_for_model(model)
    encoding = encoding_cache[model]
    return len(encoding.encode(text))


#############################################
# Image Generation
#############################################


async def generate_image(
    prompt: str,
    model: str = "dall-e-2",
    size: str = "1024x1024",
    quality: str = "standard",
    format: str = "url",
) -> str:
    result = await async_client.images.generate(
        model=model,  # type: ignore
        prompt=prompt,
        size=size,  # type: ignore
        quality=quality,  # type: ignore
        response_format=format,  # type: ignore
        n=1,
    )

    # Return appropriate format based on request
    if not result.data:
        raise ValueError("No data returned from OpenAI image generation")
    if not result.data[0]:
        raise ValueError("No data returned from OpenAI image generation")
    if format == "url":
        url = result.data[0].url
        if url is None:
            raise ValueError("No URL returned from OpenAI image generation")
        return url
    else:  # b64_json
        b64_data = result.data[0].b64_json
        if b64_data is None:
            raise ValueError("No base64 data returned from OpenAI image generation")
        return b64_data
