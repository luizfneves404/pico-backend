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

from app.education.schemas import EducationIn, EducationOut
from app.shared.validation import (
    CustomPhoneNumber,
    LowercaseEmailStr,
    StripWhitespaceStr,
)
from app.users.models import SignupSource, User

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
    phone_number: CustomPhoneNumber
    email: LowercaseEmailStr


class UserIn(UserBase):
    password: PasswordStr
    referred_by_username: StripWhitespaceStr = Field(max_length=50, default="")
    current_education: EducationIn | None = Field(default=None)
    intended_education: EducationIn | None = Field(default=None)
    signup_source: SignupSource = Field(default=SignupSource.UNKNOWN)


class OtherUserOut(UserBase):
    id: int
    social_score: int
    xp_score: int
    current_education: EducationOut | None
    intended_education: EducationOut | None

    @classmethod
    def from_orm_model(cls, user: User) -> "OtherUserOut":
        return cls(
            id=user.id,
            username=user.username,
            phone_number=user.phone_number,
            email=user.email,
            current_education=EducationOut(
                level=user.current_education.level,
                institution_id=user.current_education.institution_id,
                course_id=user.current_education.course_id,
            )
            if user.current_education
            else None,
            intended_education=EducationOut(
                level=user.intended_education.level,
                institution_id=user.intended_education.institution_id,
                course_id=user.intended_education.course_id,
            )
            if user.intended_education
            else None,
            social_score=user.social_score,
            xp_score=user.xp_score,
        )


class UserOut(OtherUserOut):
    @classmethod
    def from_orm_model(cls, user: User) -> "UserOut":
        other_user = OtherUserOut.from_orm_model(user)
        return cls(
            id=other_user.id,
            username=other_user.username,
            phone_number=other_user.phone_number,
            email=other_user.email,
            current_education=other_user.current_education,
            intended_education=other_user.intended_education,
            social_score=other_user.social_score,
            xp_score=other_user.xp_score,
        )


class PasswordRequest(BaseModel):
    current_password: PasswordStr


class UsernameUpdateRequest(PasswordRequest):
    new_username: StripWhitespaceStr = Field(min_length=1, max_length=50)


class PasswordUpdateRequest(PasswordRequest):
    new_password: PasswordStr


class PhoneNumberUpdateRequest(PasswordRequest):
    new_phone_number: CustomPhoneNumber


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
    password: PasswordStr | None = None
    phone_number: CustomPhoneNumber | None = None
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
