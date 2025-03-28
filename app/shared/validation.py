from typing import Annotated

from pydantic import EmailStr, StringConstraints
from pydantic.networks import validate_email

StripWhitespaceStr = Annotated[str, StringConstraints(strip_whitespace=True)]


class LowercaseEmailStr(EmailStr):
    """
    Validate email addresses and convert them to lowercase. It already strips whitespace because the validate_email does that.

    Args:
        EmailStr (str): The email address to validate.

    Returns:
        LowercaseEmailStr: The validated and converted email address.
    """

    @classmethod
    def validate(cls, value: EmailStr) -> EmailStr:
        email = validate_email(value)[1]
        return email.lower()
