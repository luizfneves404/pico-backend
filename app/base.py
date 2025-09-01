import datetime
import enum
import logging
import re
from collections.abc import Callable
from typing import Annotated, Any, cast

import sqlalchemy
from sqlalchemy import TIMESTAMP, MetaData, event, func, inspect, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import (
    MANYTOONE,
    DeclarativeBase,
    Mapped,
    MappedAsDataclass,
    Session,
    SessionTransaction,
    declared_attr,
    has_inherited_table,
    mapped_column,
)

ASYNC_PARENT_FOREIGN_KEY_OPTIONS = "save-update, merge, expunge, delete, delete-orphan"


# Default naming convention for all indexes and constraints
# See why this is important and how it would save your time:
# https://alembic.sqlalchemy.org/en/latest/naming.html

logger = logging.getLogger(__name__)

auto_now_insert_timestamp = Annotated[
    datetime.datetime, mapped_column(server_default=func.clock_timestamp())
]

auto_now_update_timestamp = Annotated[
    datetime.datetime,
    mapped_column(
        server_default=func.clock_timestamp(), onupdate=func.clock_timestamp()
    ),
]


def camel_to_snake(name: str) -> str:
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    return name.lower()


class Base(MappedAsDataclass, DeclarativeBase, kw_only=True):
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
        enum.Enum: sqlalchemy.Enum(
            enum.Enum, length=50, native_enum=False, create_constraint=True
        ),
    }

    @declared_attr.directive
    @classmethod
    def __tablename__(cls) -> str | None:
        if has_inherited_table(cls):
            return None
        return camel_to_snake(cls.__name__)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, default=None)
    created_at: Mapped[auto_now_insert_timestamp] = mapped_column(init=False)

    def __post_init__(self):
        for m2o_rel in (
            r for r in inspect(self).mapper.relationships if r.direction is MANYTOONE
        ):
            if self.__dict__.get(m2o_rel.key, False) is None:
                self.__dict__.pop(m2o_rel.key, None)


def register_rollback_action(session: AsyncSession, action: Callable[[], None]) -> None:
    """Registers an action to be performed if the session rolls back."""
    if "rollback_actions" not in session.info:
        session.info["rollback_actions"] = []
    # Use cast to make the type checker happy
    cast(list[Callable[[], None]], session.info["rollback_actions"]).append(action)


def handle_after_soft_rollback(
    session: AsyncSession, previous_transaction: SessionTransaction
) -> None:
    actions = cast(list[Callable[[], None]], session.info.pop("rollback_actions", []))
    for action in actions:
        try:
            action()
        except Exception as e:
            logger.error(f"Rollback cleanup failed: {e}")


event.listen(Session, "after_soft_rollback", handle_after_soft_rollback)


async def resync_autoincrement(session: AsyncSession, model_class: type[Base]) -> None:
    """Sets the autoincrement sequence to the maximum value of the id.
    When inserting rows with manual ids (not set by the database), you have to call this so that,
    next time you insert a row using automatic id, it will start from the correct id.
    """
    table_name = model_class.__tablename__
    pk_column = model_class.id.key
    if not table_name or not pk_column:
        raise ValueError("Table name or primary key column not found")
    await session.execute(
        text(f"""
        SELECT setval(
            pg_get_serial_sequence(:table_name, :pk_column),
            COALESCE((SELECT MAX({model_class.id.key}) FROM {table_name}), 1)
        )
    """),
        {"table_name": table_name, "pk_column": pk_column},
    )
