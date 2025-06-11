from enum import StrEnum

from pydantic import BaseModel, Field

from app.education.models import Course, EducationLevel, Institution, LevelStage
from app.shared.validation import Location


class InstitutionType(StrEnum):
    SCHOOL = "school"
    COLLEGE = "college"


class InstitutionOut(BaseModel):
    id: int
    name: str
    institution_type: str
    country_code: str
    address: str
    city: str

    @classmethod
    def from_orm_model(cls, model: Institution) -> "InstitutionOut":
        return cls(
            id=model.id,
            name=model.name,
            institution_type=model.institution_type,
            country_code=model.country_code,
            address=model.address,
            city=model.city,
        )


class InstitutionIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    institution_type: InstitutionType = Field(..., min_length=1, max_length=50)
    country_code: str = Field(..., min_length=2, max_length=2)


class SearchInstitutionsRequest(BaseModel):
    name: str | None = Field(default=None)
    location: Location | None = Field(default=None)
    institution_type: InstitutionType


class CourseOut(BaseModel):
    id: int
    name: str
    level_id: int

    @classmethod
    def from_orm_model(cls, model: Course) -> "CourseOut":
        return cls(
            id=model.id,
            name=str(model.name),
            level_id=model.level_id,
        )


class LevelStageOut(BaseModel):
    id: int
    name: str
    country_code: str | None
    is_default: bool

    @classmethod
    def from_orm_model(cls, model: LevelStage) -> "LevelStageOut":
        return cls(
            id=model.id,
            name=model.name,
            country_code=model.country_code,
            is_default=model.is_default,
        )


class EducationLevelOut(BaseModel):
    id: int
    name: str
    stages: list[LevelStageOut]

    @classmethod
    def from_orm_model(cls, model: EducationLevel) -> "EducationLevelOut":
        return cls(
            id=model.id,
            name=str(model.name),
            stages=[LevelStageOut.from_orm_model(stage) for stage in model.stages],
        )
