from config import settings
from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)
from pydantic_extra_types.phone_numbers import PhoneNumber
from users.models import EducationLevel

PhoneNumber.default_region_code = settings.default_phone_number_country


class TokenRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access: str
    refresh: str


class RefreshRequest(BaseModel):
    refresh: str


class VerifyRequest(BaseModel):
    token: str


class UserBase(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True, from_attributes=True)

    username: str = Field(max_length=50)

    phone_number: PhoneNumber
    email: EmailStr
    school: str = Field(
        max_length=120,
        default="",
    )
    school_id: int | None = Field(default=None)
    chosen_college: str = Field(
        max_length=120,
        default="",
    )
    chosen_course: str = Field(
        max_length=120,
        default="",
    )
    commitment: int = Field(default=20)

    @field_validator("chosen_college", "chosen_course", "school", mode="before")
    @classmethod
    def validate_name_field(cls, value):
        if isinstance(value, dict) and "name" in value:
            return value["name"]
        elif hasattr(value, "name"):
            return value.name
        elif isinstance(value, str):
            return value
        elif value is None:
            return ""
        raise ValueError(
            "Field must be a string or an object with a 'name' field or None"
        )


class UserIn(UserBase):
    password: str = Field(max_length=255)
    referred_by_username: str = Field(max_length=50, default="")
    education_level: EducationLevel = Field(
        default=EducationLevel.UNKNOWN,
    )


class UserOut(UserBase):
    id: int
    referral_count: int
    education_level: EducationLevel
