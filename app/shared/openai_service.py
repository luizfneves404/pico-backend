import logging
import random
from collections.abc import AsyncGenerator
from typing import (
    Any,
    Literal,
    Protocol,
    TypeVar,
    overload,
)

from openai import NOT_GIVEN, AsyncOpenAI, NotGiven
from openai.types.responses import ResponseInputParam
from openai.types.shared_params.reasoning import Reasoning
from pydantic import BaseModel

from app.config import settings

DEFAULT_TIMEOUT = 4 * 60
DEFAULT_IMAGE_GENERATION_TIMEOUT = 90

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)


class OpenAIServiceError(Exception):
    pass


class AbstractOpenAIService(Protocol):
    async def text(
        self,
        *,
        model: str,
        input: ResponseInputParam,  # noqa: A002
        temperature: float | NotGiven | None,
        reasoning: Reasoning | NotGiven | None,
    ) -> str: ...

    async def text_stream(
        self,
        *,
        model: str,
        input: ResponseInputParam,  # noqa: A002
        temperature: float | NotGiven | None,
        reasoning: Reasoning | NotGiven | None,
    ) -> AsyncGenerator[str, None]: ...

    async def structured(
        self,
        *,
        model: str,
        input: ResponseInputParam,  # noqa: A002
        response_model: type[ModelT],
        temperature: float | NotGiven | None,
        reasoning: Reasoning | NotGiven | None,
    ) -> ModelT: ...

    @overload
    async def embed(
        self, *, model: str, input: str, dimensions: int
    ) -> list[float]: ...
    @overload
    async def embed(
        self, *, model: str, input: list[str], dimensions: int
    ) -> list[list[float]]: ...
    async def embed(
        self,
        *,
        model: str,
        input: str | list[str],  # noqa: A002
        dimensions: int,
    ) -> list[float] | list[list[float]]: ...

    async def generate_image(
        self,
        *,
        prompt: str,
        size: Literal["1024x1024", "1536x1024", "1024x1536"] = "1024x1024",
        quality: Literal["low", "medium", "high", "auto"] = "low",
        image_format: Literal["png", "jpeg", "webp"] = "jpeg",
    ) -> str: ...


class RealOpenAIService(AbstractOpenAIService):
    def __init__(self, client: AsyncOpenAI):
        self.client = client

    async def text(
        self,
        *,
        model: str,
        input: ResponseInputParam,  # noqa: A002
        temperature: float | NotGiven | None = NOT_GIVEN,
        reasoning: Reasoning | NotGiven | None = NOT_GIVEN,
    ) -> str:
        response = await self.client.responses.create(
            model=model,
            input=input,
            temperature=temperature,
            reasoning=reasoning,
        )
        content = response.output_text
        return content

    async def text_stream(
        self,
        *,
        model: str,
        input: ResponseInputParam,  # noqa: A002
        temperature: float | NotGiven | None,
        reasoning: Reasoning | NotGiven | None,
    ) -> AsyncGenerator[str, None]:
        stream = self.client.responses.stream(
            model=model,
            input=input,
            temperature=temperature,
            reasoning=reasoning,
        )
        async with stream as events:
            async for event in events:
                if event.type == "response.output_text.delta":
                    if event.delta:
                        yield event.delta
                elif event.type == "response.failed" and event.response.error:
                    raise OpenAIServiceError(
                        "OpenAI API error when streaming: "
                        f"{event.response.error.code} - {event.response.error.message}"
                    )

    async def structured(
        self,
        *,
        model: str,
        input: ResponseInputParam,  # noqa: A002
        response_model: type[ModelT],
        temperature: float | NotGiven | None,
        reasoning: Reasoning | NotGiven | None,
    ) -> ModelT:
        response = await self.client.responses.parse(
            model=model,
            input=input,
            text_format=response_model,
            temperature=temperature,
            reasoning=reasoning,
        )
        parsed = response.output_parsed
        if not parsed:
            raise OpenAIServiceError(
                "No structured content returned from OpenAI Responses API."
            )
        return parsed

    @overload
    async def embed(
        self, *, model: str, input: str, dimensions: int
    ) -> list[float]: ...
    @overload
    async def embed(
        self, *, model: str, input: list[str], dimensions: int
    ) -> list[list[float]]: ...
    async def embed(
        self,
        *,
        model: str,
        input: str | list[str],  # noqa: A002
        dimensions: int,
    ) -> list[float] | list[list[float]]:
        response = await self.client.embeddings.create(
            model=model,
            input=input,
            dimensions=dimensions,
        )
        if isinstance(input, str):
            return response.data[0].embedding
        return [item.embedding for item in response.data]

    async def generate_image(
        self,
        *,
        prompt: str,
        size: Literal["1024x1024", "1536x1024", "1024x1536"] = "1024x1024",
        quality: Literal["low", "medium", "high", "auto"] = "low",
        image_format: Literal["png", "jpeg", "webp"] = "jpeg",
    ) -> str:
        result = await self.client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size=size,
            quality=quality,
            output_format=image_format,
            n=1,
            timeout=DEFAULT_IMAGE_GENERATION_TIMEOUT,
        )

        # Return appropriate format based on request
        if not result.data:
            raise ValueError("No data returned from OpenAI image generation")

        # gpt-image-1 returns base64 data
        b64_data = result.data[0].b64_json
        if b64_data is None:
            raise ValueError("No base64 data returned from OpenAI image generation")
        return b64_data


class MockOpenAIService(AbstractOpenAIService):
    async def text(
        self,
        *,
        model: str,
        input: ResponseInputParam,  # noqa: A002
        temperature: float | NotGiven | None,
        reasoning: Reasoning | NotGiven | None,
    ) -> str:
        mock_id = f"mock_{model}_{temperature}_{hash(str(input))}"
        return f"Mocked response for {mock_id}"

    async def text_stream(
        self,
        *,
        model: str,
        input: ResponseInputParam,  # noqa: A002
        temperature: float | NotGiven | None,
        reasoning: Reasoning | NotGiven | None,
    ) -> AsyncGenerator[str, None]:
        mock_id = f"mock_stream_{model}_{temperature}_{hash(str(input))}"
        for i in range(1, 6):
            yield f"Mocked chunk {i} for {mock_id}"

    async def structured(
        self,
        *,
        model: str,
        input: ResponseInputParam,  # noqa: A002
        response_model: type[ModelT],
        temperature: float | NotGiven | None,
        reasoning: Reasoning | NotGiven | None,
    ) -> ModelT:
        def mock_value(field_info: Any) -> Any:
            annotation = field_info.annotation
            if isinstance(annotation, type) and annotation is str:
                return "mock"
            if isinstance(annotation, type) and annotation is int:
                return 1
            if isinstance(annotation, type) and annotation is float:
                return 1.0
            if isinstance(annotation, type) and annotation is bool:
                return True
            if str(annotation).startswith("list"):
                inner_type = field_info.annotation.__args__[0]
                if hasattr(inner_type, "model_fields"):
                    return [build(inner_type)]
                return [mock_value(type("FieldInfo", (), {"annotation": inner_type})())]
            if hasattr(annotation, "model_fields"):
                return build(annotation)  # type: ignore
            return "mock"

        def build(model_cls: type[ModelT]) -> ModelT:
            values: dict[str, Any] = {}
            for fname, finfo in model_cls.model_fields.items():
                values[fname] = mock_value(finfo)
            return model_cls(**values)

        return build(response_model)

    @overload
    async def embed(
        self, *, model: str, input: str, dimensions: int
    ) -> list[float]: ...
    @overload
    async def embed(
        self, *, model: str, input: list[str], dimensions: int
    ) -> list[list[float]]: ...
    async def embed(
        self,
        *,
        model: str,
        input: str | list[str],  # noqa: A002
        dimensions: int,
    ) -> list[float] | list[list[float]]:
        def gen() -> list[float]:
            return [random.random() for _ in range(dimensions)]

        if isinstance(input, str):
            return gen()
        return [gen() for _ in input]

    async def generate_image(
        self,
        *,
        prompt: str,
        size: Literal["1024x1024", "1536x1024", "1024x1536"] = "1024x1024",
        quality: Literal["low", "medium", "high", "auto"] = "low",
        image_format: Literal["png", "jpeg", "webp"] = "jpeg",
    ) -> str:
        mock_id = f"mock_image_{prompt}_{size}_{quality}_{image_format}"
        return f"Mocked base 64 string for {mock_id}"


openai_service: AbstractOpenAIService = (
    MockOpenAIService()
    if settings.mock_openai
    else RealOpenAIService(
        AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=DEFAULT_TIMEOUT,
        )
    )
)
