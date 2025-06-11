from typing import Any, ClassVar, Sequence, Union

from sqlalchemy.orm import InstrumentedAttribute

from app.education.models import EducationInfo, Institution, School
from app.shared.admin import Admin


class SchoolAdmin(Admin, model=School):
    column_list = [School.id, School.name]
    column_searchable_list = [School.id, School.name]
    column_sortable_list = [School.id, School.name]
    column_details_list = [School.id, School.name]


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


class CourseAdmin(Admin, model=EducationInfo):
    icon = "fa-solid fa-book"

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
