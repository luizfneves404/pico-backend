from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    EmailStr,
    SecretStr,
    StringConstraints,
    TypeAdapter,
)
from pydantic.json_schema import SkipJsonSchema
from pydantic.networks import validate_email
from pydantic_extra_types.phone_numbers import PhoneNumberValidator

from app.config import settings

StripWhitespaceStr = Annotated[str, StringConstraints(strip_whitespace=True)]


def validate_lowercase_email(value: EmailStr) -> EmailStr:
    """Validate an email address and return the lowercase version.

    Args:
        value (EmailStr): The email address to validate.

    Returns:
        EmailStr: The lowercase version of the email address.
    Raises:
        ValueError: If the email address is not valid.
    """
    email = validate_email(value)[1]
    return email.lower()


LowercaseEmailStr = Annotated[
    str, AfterValidator(validate_lowercase_email), StringConstraints(max_length=255)
]


CustomPhoneNumber = Annotated[
    str,
    PhoneNumberValidator(default_region=settings.default_phone_number_country),
    StringConstraints(max_length=25),
]

phone_number_adapter: TypeAdapter[CustomPhoneNumber] = TypeAdapter(CustomPhoneNumber)


class _UnsetType(Enum):
    UNSET = "__unset__"


Unset = SkipJsonSchema[Literal[_UnsetType.UNSET]]

UnsetDefault: Unset = _UnsetType.UNSET


def check_for_unset(value: Any) -> Any:
    """Raises a ValueError if the input is '__unset__'."""
    if value == "__unset__":
        raise ValueError("'__unset__' is not an allowed input value")
    return value


class Location(BaseModel):
    latitude: float
    longitude: float


RoundedFloat = Annotated[float, AfterValidator(lambda x: round(x, 1))]
UsernameStr = Annotated[
    str, StringConstraints(min_length=1, max_length=50, pattern=r"^[a-z0-9_]+$")
]
CountryCodeStr = Annotated[str, StringConstraints(max_length=2)]
PasswordStr = Annotated[SecretStr, StringConstraints(min_length=1, max_length=255)]
