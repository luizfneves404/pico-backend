from typing import Any, ClassVar, Sequence, Union

from geoalchemy2 import WKTElement
from pydantic import BaseModel
from sqlalchemy.orm import InstrumentedAttribute

from app.education.models import (
    AdministrativeCategory,
    Course,
    EducationInfo,
    EducationLevel,
    Institution,
    InstitutionType,
    LevelStage,
)
from app.shared.admin import CustomModelView


class InstitutionImportSchema(BaseModel):
    name: str
    user_submitted: bool
    institution_type: InstitutionType
    government_issued_code: str | None
    country_id: int
    level_id: int
    administrative_category: AdministrativeCategory
    latitude: float | None
    longitude: float | None
    address: str | None
    city: str | None


class InstitutionAdmin(CustomModelView, model=Institution):
    icon = "fa-solid fa-university"

    column_list: ClassVar[
        Union[str, Sequence[Union[str, InstrumentedAttribute[Any]]]]
    ] = [
        Institution.id,
        Institution.name,
        Institution.user_submitted,
        Institution.institution_type,
        Institution.country,
        Institution.level,
        Institution.administrative_category,
        Institution.government_issued_code,
        Institution.location,
        Institution.created_at,
        Institution.address,
        Institution.city,
    ]
    column_searchable_list: ClassVar[
        Union[str, Sequence[Union[str, InstrumentedAttribute[Any]]]]
    ] = [Institution.name, Institution.address, Institution.city]
    column_sortable_list: ClassVar[
        Union[str, Sequence[Union[str, InstrumentedAttribute[Any]]]]
    ] = [
        Institution.id,
        Institution.name,
        Institution.user_submitted,
        Institution.address,
        Institution.city,
    ]

    form_columns = [
        Institution.name,
        Institution.user_submitted,
        Institution.institution_type,
        Institution.country,
        Institution.level,
        Institution.administrative_category,
        Institution.government_issued_code,
        Institution.location,
        Institution.address,
        Institution.city,
    ]

    can_import = True
    import_schema = InstitutionImportSchema
    import_template_data = {
        "name": "Arlekia University",
        "user_submitted": True,
        "institution_type": "college",
        "country_id": 1,
        "level_id": 1,
        "administrative_category": "PUBLIC",
        "government_issued_code": "1234567890",
        "latitude": 12.34567890,
        "longitude": 12.34567890,
        "address": "Rua das Flores, 123",
        "city": "São Paulo",
    }

    async def to_orm_model(
        self, validated_data_list: list[InstitutionImportSchema]
    ) -> list[Institution]:
        return [
            Institution(
                name=validated_data.name,
                user_submitted=validated_data.user_submitted,
                institution_type=validated_data.institution_type,
                country_id=validated_data.country_id,
                level_id=validated_data.level_id,
                administrative_category=validated_data.administrative_category,
                government_issued_code=validated_data.government_issued_code or "",
                location=WKTElement(
                    f"POINT({validated_data.longitude} {validated_data.latitude})"
                )
                if validated_data.latitude and validated_data.longitude
                else None,  # type: ignore # this should work according to geoalchemy2
                address=validated_data.address or "",
                city=validated_data.city or "",
            )
            for validated_data in validated_data_list
        ]


class EducationLevelImportSchema(BaseModel):
    name_i18n: str


class EducationLevelAdmin(CustomModelView, model=EducationLevel):
    icon = "fa-solid fa-layer-group"

    column_list = [
        EducationLevel.id,
        EducationLevel.name_i18n,
        EducationLevel.created_at,
    ]
    column_searchable_list = [
        EducationLevel.name_i18n,
    ]
    column_sortable_list = [
        EducationLevel.id,
        EducationLevel.name_i18n,
        EducationLevel.created_at,
    ]
    column_details_list = [
        EducationLevel.id,
        EducationLevel.name_i18n,
        EducationLevel.created_at,
        EducationLevel.stages,
    ]

    form_columns = ["name_i18n", "stages"]


class LevelStageImportSchema(BaseModel):
    name: str
    level_id: int
    country_id: int
    is_default: bool


class LevelStageAdmin(CustomModelView, model=LevelStage):
    icon = "fa-solid fa-stairs"

    column_list = [
        LevelStage.id,
        LevelStage.name,
        LevelStage.level,
        LevelStage.country,
        LevelStage.is_default,
        LevelStage.created_at,
    ]
    column_searchable_list = [
        LevelStage.name,
    ]
    column_sortable_list = [
        LevelStage.id,
        LevelStage.name,
        LevelStage.is_default,
        LevelStage.created_at,
    ]
    column_details_list = [
        LevelStage.id,
        LevelStage.name,
        LevelStage.level,
        LevelStage.country,
        LevelStage.is_default,
        LevelStage.created_at,
    ]

    form_columns = [
        "name",
        "level",
        "country",
        "is_default",
    ]


class CourseImportSchema(BaseModel):
    name_i18n: str
    level_id: int
    user_submitted: bool


class CourseAdmin(CustomModelView, model=Course):
    icon = "fa-solid fa-book-open"

    column_list = [
        Course.id,
        Course.name_i18n,
        Course.level,
        Course.user_submitted,
        Course.created_at,
    ]
    column_searchable_list = [
        Course.name_i18n,
    ]
    column_sortable_list = [
        Course.id,
        Course.name_i18n,
        Course.user_submitted,
        Course.created_at,
    ]
    column_details_list = [
        Course.id,
        Course.name_i18n,
        Course.level,
        Course.user_submitted,
        Course.created_at,
    ]

    form_columns = [
        "name_i18n",
        "level",
        "user_submitted",
    ]


class EducationInfoImportSchema(BaseModel):
    level: int
    course: int
    institution: int
    stage: int


class EducationInfoAdmin(CustomModelView, model=EducationInfo):
    icon = "fa-solid fa-graduation-cap"

    column_list: ClassVar[
        Union[str, Sequence[Union[str, InstrumentedAttribute[Any]]]]
    ] = [
        EducationInfo.id,
        EducationInfo.course,
        EducationInfo.institution,
        EducationInfo.stage,
        EducationInfo.level,
    ]
    column_searchable_list: ClassVar[
        Union[str, Sequence[Union[str, InstrumentedAttribute[Any]]]]
    ] = [
        EducationInfo.course,
        EducationInfo.institution,
        EducationInfo.stage,
        EducationInfo.level,
    ]
    column_sortable_list: ClassVar[
        Union[str, Sequence[Union[str, InstrumentedAttribute[Any]]]]
    ] = [
        EducationInfo.id,
        EducationInfo.course,
        EducationInfo.institution,
        EducationInfo.stage,
    ]

    form_columns = [
        EducationInfo.level,
        EducationInfo.course,
        EducationInfo.institution,
        EducationInfo.stage,
    ]
