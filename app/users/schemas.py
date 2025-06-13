import re
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

from app.education.schemas import Location
from app.shared.validation import (
    UNSET,
    CustomPhoneNumber,
    LowercaseEmailStr,
    StripWhitespaceStr,
    type_UNSET,
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


def validate_username_field(value: str) -> str:
    """
    Validate that the username fits the normalization rules.

    Args:
        value: The username string to validate.

    Returns:
        The original username string if valid.

    Raises:
        ValueError: If the username does not fit the normalization rules.
    """
    # Username must only contain a-z, A-Z, 0-9, and underscores, and no spaces or accents
    if not re.fullmatch(r"[a-z0-9_]+", value):
        raise ValueError("Username contains invalid characters or format")
    return value


UsernameStr = Annotated[str, AfterValidator(validate_username_field)]


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


class SocialTokenRequest(BaseModel):
    """Base schema for social authentication requests."""

    id_token: str
    signup_source: SignupSource
    referred_by_username: UsernameStr | Literal[""]


class GoogleAuthRequest(SocialTokenRequest):
    """Request schema for Google social authentication."""

    pass


class AppleAuthRequest(SocialTokenRequest):
    """Request schema for Apple social authentication."""

    name: StripWhitespaceStr


class UserBase(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True, from_attributes=True)
    name: StripWhitespaceStr = Field(min_length=1, max_length=150)
    username: UsernameStr = Field(min_length=1, max_length=50)
    phone_number: CustomPhoneNumber | Literal[""]
    email: LowercaseEmailStr


class UserIn(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True, from_attributes=True)
    name: StripWhitespaceStr = Field(min_length=1, max_length=150)
    email: LowercaseEmailStr
    password: PasswordStr
    referred_by_username: UsernameStr | Literal[""]
    signup_source: SignupSource = Field(default=SignupSource.UNKNOWN)


class EducationInfoOut(BaseModel):
    level_id: int
    stage_id: int | None
    institution_id: int | None
    course_id: int | None

    model_config = ConfigDict(from_attributes=True)


class OtherUserOut(UserBase):
    id: int
    social_score: int
    xp_score: int
    current_education: EducationInfoOut | None
    intended_education: EducationInfoOut | None

    @classmethod
    def from_orm_model(cls, user: User) -> "OtherUserOut":
        return cls(
            id=user.id,
            name=user.name,
            username=user.username,
            phone_number=user.phone_number,
            email=user.email,
            current_education=EducationInfoOut(
                level_id=user.current_education.level_id,
                stage_id=user.current_education.stage_id,
                institution_id=user.current_education.institution_id,
                course_id=user.current_education.course_id,
            )
            if user.current_education
            else None,
            intended_education=EducationInfoOut(
                level_id=user.intended_education.level_id,
                stage_id=user.intended_education.stage_id,
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
            name=other_user.name,
            username=other_user.username,
            phone_number=other_user.phone_number,
            email=other_user.email,
            current_education=other_user.current_education,
            intended_education=other_user.intended_education,
            social_score=other_user.social_score,
            xp_score=other_user.xp_score,
        )


class SentinelUserOut(BaseModel):
    id: int
    username: StripWhitespaceStr
    email: LowercaseEmailStr
    phone_number: CustomPhoneNumber | Literal[""]


class PasswordRequest(BaseModel):
    current_password: PasswordStr


class RawPhoneNumbersIn(BaseModel):
    phone_numbers: list[str]


class UserInRanking(BaseModel):
    id: int
    username: str
    rank: int
    current_education: EducationInfoOut | None
    score: RoundedFloat
    total_answers: int
    correct_answers: int


class UserIdsIn(BaseModel):
    user_ids: list[int]


class OnlineInfo(BaseModel):
    id: int
    is_online: bool
    last_online: AwareDatetime | None


class EducationInfoIn(BaseModel):
    level_id: int | type_UNSET = UNSET
    stage_id: int | type_UNSET = UNSET
    institution_id: int | type_UNSET = UNSET
    course_id: int | type_UNSET = UNSET


# New unified update schemas
class UserUpdate(BaseModel):
    """Unified user update schema with optional fields."""

    model_config = ConfigDict(coerce_numbers_to_str=True)

    name: StripWhitespaceStr | type_UNSET = Field(UNSET, min_length=1, max_length=150)
    username: UsernameStr | type_UNSET = Field(UNSET, min_length=1, max_length=50)
    password: PasswordStr | type_UNSET = UNSET
    phone_number: CustomPhoneNumber | type_UNSET = UNSET
    email: LowercaseEmailStr | type_UNSET = UNSET
    current_education: EducationInfoIn | type_UNSET = UNSET
    intended_education: EducationInfoIn | type_UNSET = UNSET
    country_code: str | type_UNSET = Field(UNSET, max_length=2)
    location: Location | type_UNSET = UNSET


class UserUpdateRequest(BaseModel):
    """Request wrapper for user updates with optional password verification."""

    updates: UserUpdate
    current_password: PasswordStr | None = None


class UserPartialUpdateResponse(BaseModel):
    """Response showing what fields were updated."""

    updated_fields: list[str]
    user: UserOut
