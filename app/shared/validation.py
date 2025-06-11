from enum import Enum
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, EmailStr, StringConstraints
from pydantic.networks import validate_email
from pydantic_extra_types.phone_numbers import PhoneNumberValidator

from app.config import settings

StripWhitespaceStr = Annotated[str, StringConstraints(strip_whitespace=True)]


def validate_lowercase_email(value: EmailStr) -> EmailStr:
    email = validate_email(value)[1]
    return email.lower()


LowercaseEmailStr = Annotated[str, AfterValidator(validate_lowercase_email)]


CustomPhoneNumber = Annotated[
    str,
    PhoneNumberValidator(default_region=settings.default_phone_number_country),
]


class UnsetType(Enum):
    UNSET = "UNSET"


UNSET = UnsetType.UNSET
type_UNSET = Literal[UnsetType.UNSET]


class Location(BaseModel):
    latitude: float
    longitude: float
