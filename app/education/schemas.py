from pydantic import BaseModel, ConfigDict, Field

from app.users.models import EducationLevel


class InstitutionOut(BaseModel):
    id: int
    name: str
    institution_type: str
    user_submitted: bool
    model_config = ConfigDict(from_attributes=True)


class InstitutionIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


class SchoolOut(InstitutionOut):
    inep_code: str


class SchoolIn(InstitutionIn):
    inep_code: str = Field(default="", max_length=40)


class CollegeOut(InstitutionOut):
    pass


class CollegeIn(InstitutionIn):
    pass


class CourseOut(BaseModel):
    id: int
    name: str
    user_submitted: bool

    model_config = ConfigDict(from_attributes=True)


class CourseIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


class EducationOut(BaseModel):
    level: EducationLevel
    institution_id: int | None
    course_id: int | None
    model_config = ConfigDict(from_attributes=True)


class EducationIn(BaseModel):
    level: EducationLevel = Field(default=EducationLevel.UNKNOWN)
    institution_id: int | None = Field(default=None)
    course_id: int | None = Field(default=None)
