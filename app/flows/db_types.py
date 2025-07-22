from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter
from sqlalchemy.sql.operators import OperatorType
from sqlalchemy.types import JSON, TypeDecorator


class ImageBlock(BaseModel):
    block_type: Literal[
        "image"
    ]  # didn't add as default because OpenAPI will render it as optional
    image_id: int
    alt: str | None = None


class RichText(BaseModel):
    text: str
    bold: bool
    italic: bool
    underline: bool
    strikethrough: bool
    link: str | None = None


class TextBlock(BaseModel):
    block_type: Literal[
        "text"
    ]  # didn't add as default because OpenAPI will render it as optional
    style: Literal[
        "paragraph",
        "heading1",
        "heading2",
        "heading3",
        "heading4",
        "heading5",
        "heading6",
    ]
    content: list[RichText]


ContentBlock = Annotated[TextBlock | ImageBlock, Field(discriminator="block_type")]


def validate_content_block_list(value: Any) -> list[ContentBlock]:
    return TypeAdapter(list[ContentBlock]).validate_python(value)


class ContentBlockListType(TypeDecorator[list[ContentBlock]]):
    """Stores a list of ContentBlock models as JSON in the DB"""

    impl = JSON
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        content_blocks = validate_content_block_list(value)
        return [block.model_dump(mode="json") for block in content_blocks]

    def process_result_value(
        self, value: Any, dialect: Any
    ) -> list[ContentBlock] | None:
        if value is None:
            return None
        return validate_content_block_list(value)

    def coerce_compared_value(self, op: OperatorType | None, value: Any) -> Any:
        return self.impl.coerce_compared_value(op, value)  # type: ignore
