from typing import Any, ClassVar, Sequence, Union

from sqlalchemy.orm import InstrumentedAttribute

from app.education.models import (
    Course,
    EducationInfo,
    EducationLevel,
    Institution,
    LevelStage,
)
from app.shared.admin import Admin


class InstitutionAdmin(Admin, model=Institution):
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
    ]
    column_searchable_list: ClassVar[
        Union[str, Sequence[Union[str, InstrumentedAttribute[Any]]]]
    ] = [Institution.name]
    column_sortable_list: ClassVar[
        Union[str, Sequence[Union[str, InstrumentedAttribute[Any]]]]
    ] = [Institution.id, Institution.name, Institution.user_submitted]

    form_columns = ["name", "user_submitted", "courses"]


class EducationLevelAdmin(Admin, model=EducationLevel):
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
    ]

    form_columns = [
        "name_i18n",
    ]


class LevelStageAdmin(Admin, model=LevelStage):
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
        "level_id",
        "country_code",
        "is_default",
    ]


class CourseModelAdmin(Admin, model=Course):
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
        "level_id",
        "user_submitted",
    ]


class EducationInfoAdmin(Admin, model=EducationInfo):
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

    form_columns = ["course", "institution", "stage"]
