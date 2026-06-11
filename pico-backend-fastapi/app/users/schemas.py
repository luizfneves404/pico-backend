from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
)

from app.education.schemas import Location
from app.shared.validation import (
    CountryCodeStr,
    CustomPhoneNumber,
    LowercaseEmailStr,
    PasswordStr,
    StripWhitespaceStr,
    Unset,
    UnsetDefault,
    UsernameStr,
)
from app.users.models import SignupSource, User

NameStr = Annotated[StripWhitespaceStr, StringConstraints(min_length=1, max_length=150)]


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"]


class RefreshRequest(BaseModel):
    refresh_token: str


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

    name: NameStr | None = None


class UserBase(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True, from_attributes=True)
    name: NameStr
    username: UsernameStr
    phone_number: CustomPhoneNumber | Literal[""]
    email: LowercaseEmailStr


class UserIn(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True, from_attributes=True)
    name: NameStr
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
    instagram_account: str
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
            instagram_account=user.instagram_account,
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
            instagram_account=other_user.instagram_account,
            current_education=other_user.current_education,
            intended_education=other_user.intended_education,
            social_score=other_user.social_score,
            xp_score=other_user.xp_score,
        )


class SentinelUserOut(BaseModel):
    id: int
    username: UsernameStr
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
    score: int


class UserIdsIn(BaseModel):
    user_ids: list[int]


class EducationInfoIn(BaseModel):
    level_id: int | Unset = UnsetDefault
    stage_id: int | Unset = UnsetDefault
    institution_id: int | Unset = UnsetDefault
    course_id: int | Unset = UnsetDefault


# New unified update schemas
class UserUpdate(BaseModel):
    """Unified user update schema with optional fields."""

    model_config = ConfigDict(coerce_numbers_to_str=True)

    name: NameStr | Unset = UnsetDefault
    username: UsernameStr | Unset = UnsetDefault
    password: PasswordStr | Unset = UnsetDefault
    phone_number: CustomPhoneNumber | Unset = UnsetDefault
    email: LowercaseEmailStr | Unset = UnsetDefault
    instagram_account: str | Unset = UnsetDefault
    current_education: EducationInfoIn | Unset = UnsetDefault
    intended_education: EducationInfoIn | Unset = UnsetDefault
    country_code: CountryCodeStr | Unset = UnsetDefault
    location: Location | Unset = UnsetDefault


class UserUpdateRequest(BaseModel):
    """Request wrapper for user updates with optional password verification."""

    updates: UserUpdate
    current_password: PasswordStr | None = None


class UserPartialUpdateResponse(BaseModel):
    """Response showing what fields were updated."""

    updated_fields: list[str]
    user: UserOut


class UserFieldValidationRequest(BaseModel):
    field_name: Literal["username", "email", "phone_number"]
    field_value: str


class UserFieldValidationResponse(BaseModel):
    is_valid: bool
    validated_value: str | None


class OnlineInfo(BaseModel):
    id: int
    is_online: bool
    last_online: AwareDatetime | None


class PasswordResetRequest(BaseModel):
    email: LowercaseEmailStr


class PasswordResetResponse(BaseModel):
    message: str
