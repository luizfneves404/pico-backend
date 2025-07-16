from enum import Enum
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, EmailStr, StringConstraints, TypeAdapter
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
        email_validator.EmailNotValidError: If the email address is not valid.
    """
    email = validate_email(value)[1]
    return email.lower()


LowercaseEmailStr = Annotated[str, AfterValidator(validate_lowercase_email)]


CustomPhoneNumber = Annotated[
    str,
    PhoneNumberValidator(default_region=settings.default_phone_number_country),
]

phone_number_adapter: TypeAdapter[CustomPhoneNumber] = TypeAdapter(CustomPhoneNumber)


class UnsetType(Enum):
    UNSET = "UNSET"


UNSET = UnsetType.UNSET
type_UNSET = Literal[UnsetType.UNSET]


class Location(BaseModel):
    latitude: float
    longitude: float


RoundedFloat = Annotated[float, AfterValidator(lambda x: round(x, 1))]
