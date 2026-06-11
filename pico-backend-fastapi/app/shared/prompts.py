from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any, ClassVar, Protocol

from openai import NOT_GIVEN, NotGiven
from openai.types.responses import ResponseInputParam
from openai.types.shared_params.reasoning import Reasoning
from pydantic import BaseModel

from app.shared.openai_service import openai_service


class PromptLike[**P](Protocol):
    reasoning: ClassVar[Reasoning | None | NotGiven]
    temperature: ClassVar[float | NotGiven | None]

    def model(self) -> str: ...

    def build_input(self, *args: P.args, **kwargs: P.kwargs) -> ResponseInputParam: ...


class StructuredPromptLike[ModelT: BaseModel, **P](Protocol):
    reasoning: ClassVar[Reasoning | None | NotGiven]
    temperature: ClassVar[float | NotGiven | None]

    def response_model(self) -> type[ModelT]: ...

    def model(self) -> str: ...

    def build_input(self, *args: P.args, **kwargs: P.kwargs) -> ResponseInputParam: ...


class Prompt(ABC):
    """Abstract base class for prompts.
    I wanted to make the subclasses usable without instantiating (using classmethods or staticmethods for the methods), but i couldn't find a way to do it
    with good type safety. So subclass this, and then instantiate the subclass in order to call the AI methods.
    Don't add behavior exclusive to the instance, such as init methods or instance variables.
    """

    reasoning: ClassVar[Reasoning | None | NotGiven] = NOT_GIVEN
    temperature: ClassVar[float | NotGiven | None] = NOT_GIVEN

    @abstractmethod
    def model[**P](
        self,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def build_input[**P](self, *args: Any, **kwargs: Any) -> ResponseInputParam:
        raise NotImplementedError

    async def text[**P](self: PromptLike[P], *args: P.args, **kwargs: P.kwargs) -> str:
        return await openai_service.text(
            model=self.model(),
            input=self.build_input(*args, **kwargs),
            reasoning=self.reasoning,
            temperature=self.temperature,
        )

    async def text_stream[**P](
        self: PromptLike[P], *args: P.args, **kwargs: P.kwargs
    ) -> AsyncGenerator[str, None]:
        return await openai_service.text_stream(
            model=self.model(),
            temperature=self.temperature,
            input=self.build_input(*args, **kwargs),
            reasoning=self.reasoning,
        )


class StructuredPrompt[ModelT: BaseModel](Prompt, ABC):
    @abstractmethod
    def response_model[**P](self: StructuredPromptLike[ModelT, P]) -> type[ModelT]:
        raise NotImplementedError

    async def structured[**P](
        self: StructuredPromptLike[ModelT, P], *args: P.args, **kwargs: P.kwargs
    ) -> ModelT:
        return await openai_service.structured(
            model=self.model(),
            temperature=self.temperature,
            input=self.build_input(*args, **kwargs),
            reasoning=self.reasoning,
            response_model=self.response_model(),
        )
