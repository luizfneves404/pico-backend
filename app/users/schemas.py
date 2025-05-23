from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    SecretStr,
    StringConstraints,
    computed_field,
)
from pydantic_extra_types.phone_numbers import PhoneNumber

from app.config import settings
from app.education.schemas import EducationIn, EducationOut
from app.shared.validation import LowercaseEmailStr, StripWhitespaceStr
from app.users.models import SignupSource

PhoneNumber.default_region_code = settings.default_phone_number_country

PasswordStr = Annotated[SecretStr, StringConstraints(max_length=255)]

RoundedFloat = Annotated[float, AfterValidator(lambda x: round(x, 1))]


def validate_name_field(value: Any) -> str:
    if isinstance(value, dict):
        if "name" in value and isinstance(value["name"], str):
            return value["name"]
        raise ValueError(
            "Field must be a string or an object with a 'name' field or None"
        )
    elif hasattr(value, "name") and isinstance(getattr(value, "name"), str):
        return getattr(value, "name")
    elif value is None:
        return ""
    raise ValueError("Field must be a string or an object with a 'name' field or None")


ObjectName = Annotated[str, BeforeValidator(validate_name_field)]


class TokenRequest(BaseModel):
    username: StripWhitespaceStr
    password: PasswordStr


class TokenResponse(BaseModel):
    access: str
    refresh: str
    # oauth2 scheme expects these:
    token_type: Literal["bearer"] = "bearer"

    @computed_field
    @property
    def access_token(self) -> str:
        return self.access


class RefreshRequest(BaseModel):
    refresh: str


class VerifyRequest(BaseModel):
    token: str


class UserBase(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True, from_attributes=True)

    username: StripWhitespaceStr = Field(min_length=1, max_length=50)
    phone_number: PhoneNumber
    email: LowercaseEmailStr


class UserIn(UserBase):
    password: PasswordStr
    referred_by_username: StripWhitespaceStr = Field(max_length=50, default="")
    current_education: EducationIn | None = Field(default=None)
    intended_education: EducationIn | None = Field(default=None)
    signup_source: SignupSource = Field(default=SignupSource.UNKNOWN)


class UserOut(UserBase):
    id: int
    social_score: int
    xp_score: int
    current_education: EducationOut | None
    intended_education: EducationOut | None


class OtherUserOut(UserBase):
    id: int
    social_score: int
    xp_score: int
    current_education: EducationOut | None
    intended_education: EducationOut | None


class PasswordRequest(BaseModel):
    current_password: PasswordStr


class UsernameUpdateRequest(PasswordRequest):
    new_username: StripWhitespaceStr = Field(min_length=1, max_length=50)


class PasswordUpdateRequest(PasswordRequest):
    new_password: PasswordStr


class PhoneNumberUpdateRequest(PasswordRequest):
    new_phone_number: PhoneNumber


class EmailUpdateRequest(PasswordRequest):
    new_email: LowercaseEmailStr


class EducationUpdateRequest(BaseModel):
    education: EducationIn


class UserStatsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: StripWhitespaceStr
    current_education: EducationOut | None
    intended_education: EducationOut | None
    streak: int
    done_today: bool
    total_answers: int
    correct_answers: int
    area_expected_scores: dict[
        Literal["Matemática", "Linguagem", "Ciências Humanas", "Ciências da Natureza"],
        RoundedFloat,
    ]
    score: RoundedFloat
    percentage_score: RoundedFloat


class SubcategoryPerformance(BaseModel):
    total_answers: int
    correct_answers: int


class UserStatsMeResponse(UserStatsResponse):
    subject_performance: dict[
        Literal[
            "Matemática",
            "Linguagens",
            "Ciências Humanas",
            "Ciências da Natureza",
            "Outros",
        ],
        dict[str, dict[str, dict[str, SubcategoryPerformance]]],
    ]


class RawPhoneNumbersIn(BaseModel):
    phone_numbers: list[str]


class UserInRanking(BaseModel):
    id: int
    username: str
    rank: int
    current_education: EducationOut | None
    score: RoundedFloat
    total_answers: int
    correct_answers: int


class UserIdsIn(BaseModel):
    user_ids: list[int]


class OnlineInfo(BaseModel):
    id: int
    is_online: bool
    last_online: AwareDatetime | None


class BalanceOut(BaseModel):
    balance: int


# New unified update schemas
class UserUpdate(BaseModel):
    """Unified user update schema with optional fields."""

    model_config = ConfigDict(coerce_numbers_to_str=True)

    username: StripWhitespaceStr | None = Field(None, min_length=1, max_length=50)
    phone_number: PhoneNumber | None = None
    email: LowercaseEmailStr | None = None
    current_education: EducationIn | None = None
    intended_education: EducationIn | None = None


class UserUpdateRequest(BaseModel):
    """Request wrapper for user updates with optional password verification."""

    updates: UserUpdate
    current_password: PasswordStr | None = None


class UserPartialUpdateResponse(BaseModel):
    """Response showing what fields were updated."""

    updated_fields: list[str]
    user: UserOut


class UserUpdatePermissions(BaseModel):
    """Configuration for which fields require password verification."""

    requires_password: list[str] = ["username", "phone_number", "email"]
    allows_anonymous: list[str] = [
        "current_education",
        "intended_education",
    ]
