import datetime
import enum
import logging
import re
from typing import Annotated, Any, Callable, Literal, cast

import sqlalchemy
from pydantic import BaseModel, Field, TypeAdapter
from sqlalchemy import TIMESTAMP, MetaData, event, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    declared_attr,
    has_inherited_table,
    mapped_column,
)
from sqlalchemy.sql.operators import OperatorType
from sqlalchemy.types import JSON, TypeDecorator

ASYNC_PARENT_FOREIGN_KEY_OPTIONS = "save-update, merge, expunge, delete, delete-orphan"


# Default naming convention for all indexes and constraints
# See why this is important and how it would save your time:
# https://alembic.sqlalchemy.org/en/latest/naming.html

logger = logging.getLogger(__name__)

auto_now_insert_timestamp = Annotated[
    datetime.datetime, mapped_column(server_default=func.now())
]

auto_now_update_timestamp = Annotated[
    datetime.datetime, mapped_column(server_default=func.now(), onupdate=func.now())
]


class RichText(BaseModel):
    text: str
    bold: bool
    italic: bool
    underline: bool
    strikethrough: bool
    link: str | None = None


class TextBlock(BaseModel):
    type: Literal["text"]
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


class ImageBlock(BaseModel):
    type: Literal["image"]
    file_id: str
    alt: str | None = None


ContentBlock = Annotated[TextBlock | ImageBlock, Field(discriminator="type")]


def camel_to_snake(name: str) -> str:
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    return name.lower()


class ContentBlockListType(TypeDecorator[list[ContentBlock]]):
    """Stores a list of ContentBlock models as JSONB in the DB"""

    impl = JSON
    cache_ok = True

    def process_bind_param(self, value: list[ContentBlock] | None, dialect: Any) -> Any:
        if value is None:
            return None
        return [block.model_dump() for block in value]  # Serialize each block

    def process_result_value(
        self, value: Any, dialect: Any
    ) -> list[ContentBlock] | None:
        if value is None:
            return None
        return TypeAdapter(list[ContentBlock]).validate_python(value)

    def coerce_compared_value(self, op: OperatorType | None, value: Any) -> Any:
        return self.impl.coerce_compared_value(op, value)  # type: ignore


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "all_column_names": lambda constraint, table: "_".join(
                [str(column.name) for column in cast(Any, constraint).columns]
            ),
            "ix": "ix__%(table_name)s__%(all_column_names)s",
            "uq": "uq__%(table_name)s__%(all_column_names)s",
            "ck": "ck__%(table_name)s__%(constraint_name)s",
            "fk": "fk__%(table_name)s__%(all_column_names)s__%(referred_table_name)s",
            "pk": "pk__%(table_name)s",
        }
    )
    type_annotation_map = {
        datetime.datetime: TIMESTAMP(timezone=True),
        enum.Enum: sqlalchemy.Enum(enum.Enum, length=50, native_enum=False),
    }

    @declared_attr.directive
    @classmethod
    def __tablename__(cls) -> str | None:
        if has_inherited_table(cls):
            return None
        return camel_to_snake(cls.__name__)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    created_at: Mapped[auto_now_insert_timestamp]


def register_rollback_action(session: AsyncSession, action: Callable[[], None]) -> None:
    """Registers an action to be performed if the session rolls back."""
    if "rollback_actions" not in session.info:
        session.info["rollback_actions"] = []
    # Use cast to make the type checker happy
    cast(list[Callable[[], None]], session.info["rollback_actions"]).append(action)


def after_transaction_end(session: Session, transaction: Any) -> None:
    """Called when a transaction ends; executes rollback actions if needed."""
    if transaction._parent is None:
        actions = cast(
            list[Callable[[], None]], session.info.pop("rollback_actions", [])
        )
        for action in actions:
            try:
                action()
            except Exception as e:
                logger.error(f"Rollback cleanup failed: {e}")


event.listen(Session, "after_transaction_end", after_transaction_end)
