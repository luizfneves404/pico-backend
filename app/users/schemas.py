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
from app.shared.validation import LowercaseEmailStr, StripWhitespaceStr
from app.users.models import EducationLevel, SignupSource

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
    school_id: int | None = Field(default=None)
    commitment: int = Field(default=20)
    education_level: EducationLevel = Field(
        default=EducationLevel.UNKNOWN,
    )
    signup_source: SignupSource = Field(
        default=SignupSource.UNKNOWN,
    )


class UserIn(UserBase):
    password: PasswordStr
    referred_by_username: StripWhitespaceStr = Field(max_length=50, default="")
    chosen_college: StripWhitespaceStr = Field(
        max_length=120,
        default="",
    )
    chosen_course: StripWhitespaceStr = Field(
        max_length=120,
        default="",
    )


class UserOut(UserBase):
    id: int
    referral_count: int
    chosen_college: ObjectName = Field(
        max_length=120,
    )
    chosen_course: ObjectName = Field(
        max_length=120,
    )


class OtherUserOut(BaseModel):
    id: int
    username: StripWhitespaceStr
    email: LowercaseEmailStr
    phone_number: PhoneNumber
    school_id: int | None


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


class SchoolUpdateRequest(BaseModel):
    new_school_id: int | None


class CollegeUpdateRequest(BaseModel):
    new_chosen_college: StripWhitespaceStr = Field(max_length=120)


class CourseUpdateRequest(BaseModel):
    new_chosen_course: StripWhitespaceStr = Field(max_length=120)


class CommitmentUpdateRequest(BaseModel):
    commitment: int


class EducationLevelUpdateRequest(BaseModel):
    education_level: EducationLevel


class UserStatsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: StripWhitespaceStr
    school_id: int | None = None
    chosen_college: ObjectName
    chosen_course: ObjectName
    education_level: EducationLevel
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
    dynamic_score: RoundedFloat
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
    school_id: int | None = Field(default=None)
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
