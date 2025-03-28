import random
import string

from sqlalchemy import Connection, String, event, select
from sqlalchemy.orm import Mapped, Mapper, declared_attr, mapped_column

MAX_ATTEMPTS = 10


class CouldNotGenerateUniqueCodeError(Exception):
    """Exception raised when a unique code could not be generated."""


class HasCode:
    """Mixin that automatically adds and manages a unique sharing code."""

    @declared_attr
    @classmethod
    def code(cls) -> Mapped[str]:
        return mapped_column(String(10), unique=True)

    @classmethod
    def __declare_last__(cls) -> None:
        event.listen(cls, "before_insert", HasCode._set_code)

    @staticmethod
    def _set_code(
        mapper: Mapper[type["HasCode"]],
        connection: Connection,
        target: "HasCode",
    ) -> None:
        if not target.code:
            # Generate a unique code that doesn't exist in the database
            target.code = HasCode._generate_unique_code(connection, mapper.class_)

    @staticmethod
    def _generate_unique_code(
        connection: Connection,
        model_class: type["HasCode"],
        length: int = 5,
    ) -> str:
        chars = "".join(set(string.ascii_uppercase + string.digits) - set("IOQ01"))

        attempts = 0
        while attempts < MAX_ATTEMPTS:
            # Generate a random code
            code = "".join(random.choice(chars) for _ in range(length))

            # Check if code exists directly using the connection
            stmt = select(model_class.code).where(model_class.code == code)
            result = connection.execute(stmt)

            if not result.scalar():
                return code

            attempts += 1

        raise CouldNotGenerateUniqueCodeError()


def validate_code_format(code: str) -> None:
    if not code.isalnum() or len(code) != 5:
        raise InvalidCodeError()
