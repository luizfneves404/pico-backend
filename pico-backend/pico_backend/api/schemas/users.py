from typing import Literal

from api.models import EducationLevel, SignupSource
from ninja import Schema
from pydantic import (
    AliasChoices,
    AwareDatetime,
    ConfigDict,
    Field,
    field_validator,
)
from pydantic_extra_types.phone_numbers import PhoneNumber
from shared.validation import LowercaseEmailStr

PhoneNumber.default_region_code = "BR"


class EmailIn(Schema):
    email: LowercaseEmailStr


class SimpleUserOut(Schema):
    id: int
    username: str


class UserBase(Schema):
    model_config = ConfigDict(coerce_numbers_to_str=True, from_attributes=True)

    username: str = Field(max_length=50)
    phone_number: PhoneNumber
    email: LowercaseEmailStr
    school: str = Field(
        max_length=120,
        validation_alias=AliasChoices("school.name", "school"),
        default="",
    )
    school_id: int | None = Field(default=None)
    chosen_college: str = Field(
        max_length=120,
        default="",
        validation_alias=AliasChoices("chosen_college.name", "chosen_college"),
    )
    chosen_course: str = Field(
        max_length=120,
        default="",
        validation_alias=AliasChoices("chosen_course.name", "chosen_course"),
    )
    commitment: int = Field(default=20)
    signup_source: SignupSource = Field(default=SignupSource.UNKNOWN)
    education_level: EducationLevel = Field(
        default=EducationLevel.UNKNOWN,
    )


class UserIn(UserBase):
    password: str = Field(max_length=255)
    referred_by_username: str = Field(max_length=50, default="")


class UserOut(UserBase):
    id: int
    referral_count: int
    balance: int


class OtherUserOut(Schema):
    id: int
    username: str
    email: LowercaseEmailStr
    phone_number: PhoneNumber
    school: str = Field(max_length=120)  # deprecated
    school_id: int | None


class CurrentPasswordIn(Schema):
    current_password: str


class NewSchoolIn(Schema):
    new_school: str = Field(max_length=120, default="")
    new_school_id: int | None = Field(default=None)


class NewChosenCollegeIn(Schema):
    new_chosen_college: str = Field(
        max_length=120,
    )


class NewChosenCourseIn(Schema):
    new_chosen_course: str = Field(
        max_length=120,
    )


class ReferredByIn(Schema):
    new_referred_by_username: str = Field(max_length=50)


class CommitmentIn(Schema):
    commitment: int


class EducationLevelIn(Schema):
    education_level: EducationLevel


class UsernameIn(Schema):
    username: str = Field(max_length=50)


class RawPhoneNumbersIn(Schema):
    phone_numbers: list[str]


class PhoneNumberIn(Schema):
    phone_number: PhoneNumber


class UserStatsOut(Schema):
    id: int
    username: str
    school: str = Field(max_length=120, default="")
    school_id: int | None = Field(default=None)
    chosen_college: str = Field(
        max_length=120,
        default="",
        validation_alias=AliasChoices("chosen_college.name", "chosen_college"),
    )
    chosen_course: str = Field(
        max_length=120,
        default="",
        validation_alias=AliasChoices("chosen_course.name", "chosen_course"),
    )
    education_level: EducationLevel
    streak: int
    done_today: bool
    score: float
    percentage_score: float
    area_expected_scores: dict[
        Literal[
            "Matemática", "Linguagem", "Ciências Humanas", "Ciências da Natureza"
        ],  # deveria ser Linguagens, mas o front ta esperando errado
        float,
    ]
    total_answers: int
    correct_answers: int

    @field_validator("score")
    @classmethod
    def validate_score(cls, v: float):
        return round(v, 1)

    @field_validator("area_expected_scores")
    @classmethod
    def validate_area_expected_scores(cls, v: dict[str, float]):
        return {key: round(value, 1) for key, value in v.items()}

    @field_validator("percentage_score")
    @classmethod
    def validate_percentage_score(cls, v: float):
        return round(v, 1)


class SubcategoryPerformance(Schema):
    total_answers: int
    correct_answers: int


class UserMeStatsOut(Schema):
    id: int
    username: str
    streak: int
    done_today: bool
    score: float
    percentage_score: float
    dynamic_score: float
    area_expected_scores: dict[
        Literal[
            "Matemática", "Linguagem", "Ciências Humanas", "Ciências da Natureza"
        ],  # deveria ser Linguagens, mas o front ta esperando errado
        float,
    ]
    total_answers: int
    correct_answers: int
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

    @field_validator("score")
    @classmethod
    def validate_score(cls, v: float):
        return round(v, 1)

    @field_validator("area_expected_scores")
    @classmethod
    def validate_area_expected_scores(cls, v: dict[str, float]):
        return {key: round(value, 1) for key, value in v.items()}

    @field_validator("percentage_score")
    @classmethod
    def validate_percentage_score(cls, v: float):
        return round(v, 1)

    @field_validator("dynamic_score")
    @classmethod
    def validate_dynamic_score(cls, v: float):
        return round(v, 1)


class UserInRanking(Schema):
    id: int
    username: str
    rank: int
    school: str = Field(max_length=120, default="")
    school_id: int | None = Field(default=None)
    score: float
    total_answers: int
    correct_answers: int

    @field_validator("score")
    @classmethod
    def validate_score(cls, v: float):
        return round(v, 1)


class UserIdsIn(Schema):
    user_ids: list[int]


class OnlineInfo(Schema):
    id: int
    is_online: bool
    last_online: AwareDatetime | None


class BalanceOut(Schema):
    balance: int
