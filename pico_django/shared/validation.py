from pydantic import EmailStr
from pydantic.networks import validate_email


class LowercaseEmailStr(EmailStr):
    @classmethod
    def validate(cls, value: EmailStr) -> EmailStr:
        email = validate_email(value)[1]
        return email.lower()
