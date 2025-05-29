from typing import Annotated

from pydantic import AfterValidator, EmailStr, StringConstraints
from pydantic.networks import validate_email
from pydantic_extra_types.phone_numbers import PhoneNumber, PhoneNumberValidator

from app.config import settings

StripWhitespaceStr = Annotated[str, StringConstraints(strip_whitespace=True)]


def validate_lowercase_email(value: EmailStr) -> EmailStr:
    email = validate_email(value)[1]
    return email.lower()


LowercaseEmailStr = Annotated[str, AfterValidator(validate_lowercase_email)]


CustomPhoneNumber = Annotated[
    str | PhoneNumber,
    PhoneNumberValidator(default_region=settings.default_phone_number_country),
]
