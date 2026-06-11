from typing import ClassVar

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from geoalchemy2 import WKTElement
from pydantic import BaseModel, Field
from sqladmin import action
from sqlalchemy import select

from app.arq_client import enqueue_job
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
    full_name: str | None = None
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

    column_list = (
        Institution.id,
        Institution.name,
        Institution.full_name,
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
    )
    column_searchable_list = (
        Institution.name,
        Institution.full_name,
        Institution.address,
        Institution.city,
    )
    column_sortable_list = (
        Institution.id,
        Institution.name,
        Institution.user_submitted,
        Institution.address,
        Institution.city,
    )

    form_columns = (
        Institution.name,
        Institution.full_name,
        Institution.user_submitted,
        Institution.institution_type,
        Institution.country,
        Institution.level,
        Institution.administrative_category,
        Institution.government_issued_code,
        Institution.location,
        Institution.address,
        Institution.city,
    )

    can_import = True
    import_schema = InstitutionImportSchema
    import_template_data: ClassVar = {
        "name": "Arlekia University",
        "full_name": "Universidade Arlekia - Centro de Ensino Superior e Tecnologia",
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
                full_name=validated_data.full_name
                or validated_data.name,  # Default to name if not provided
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

    @action(
        name="determine_display_name",
        label="Determinar nome de exibição",
        confirmation_message="Tem certeza que quer gerar nomes de exibição usando OpenAI para as instituições selecionadas?",
        add_in_detail=False,
        add_in_list=True,
    )
    async def determine_display_name(self, request: Request) -> RedirectResponse:
        """Enqueue per-institution display name generation tasks."""
        pks_str = request.query_params.get("pks", "")

        ids: list[int]
        if pks_str == "__all__":
            # Fetch all institution ids matching desired filter (non-empty full_name)
            results = await self._run_arbitrary_query(
                select(Institution.id).where(Institution.full_name != "")
            )
            ids = [result[0] for result in results]
        else:
            try:
                ids = [int(pk) for pk in pks_str.split(",") if pk]
            except ValueError as e:
                raise HTTPException(
                    status_code=400, detail="Invalid primary key format."
                ) from e

        if not ids:
            referer = request.headers.get("Referer")
            return RedirectResponse(
                referer or request.url_for("admin:list", identity=self.identity)
            )

        for inst_id in ids:
            await enqueue_job(
                "task_determine_institution_display_name", institution_id=inst_id
            )

        referer = request.headers.get("Referer")
        return RedirectResponse(
            referer or request.url_for("admin:list", identity=self.identity)
        )


class EducationLevelImportSchema(BaseModel):
    name_i18n: str = Field(
        title="Internationalized Name",
        description="A dictionary mapping language codes (e.g., 'en', 'es') to the course name.",
        examples=[
            {"en": "High School", "es": "Educación Secundaria"},
        ],
    )


class EducationLevelAdmin(CustomModelView, model=EducationLevel):
    icon = "fa-solid fa-layer-group"

    column_list = (
        EducationLevel.id,
        EducationLevel.name_i18n,
        EducationLevel.created_at,
    )
    column_searchable_list = (EducationLevel.name_i18n,)
    column_sortable_list = (
        EducationLevel.id,
        EducationLevel.name_i18n,
        EducationLevel.created_at,
    )
    column_details_list = (
        EducationLevel.id,
        EducationLevel.name_i18n,
        EducationLevel.created_at,
        EducationLevel.stages,
    )

    form_columns = (
        "name_i18n",
        "stages",
    )


class LevelStageImportSchema(BaseModel):
    name: str
    level_id: int
    country_id: int
    is_default: bool


class LevelStageAdmin(CustomModelView, model=LevelStage):
    icon = "fa-solid fa-stairs"

    column_list = (
        LevelStage.id,
        LevelStage.name,
        LevelStage.level,
        LevelStage.country,
        LevelStage.is_default,
        LevelStage.created_at,
    )
    column_searchable_list = (LevelStage.name,)
    column_sortable_list = (
        LevelStage.id,
        LevelStage.name,
        LevelStage.is_default,
        LevelStage.created_at,
    )
    column_details_list = (
        LevelStage.id,
        LevelStage.name,
        LevelStage.level,
        LevelStage.country,
        LevelStage.is_default,
        LevelStage.created_at,
    )

    form_columns = (
        "name",
        "level",
        "country",
        "is_default",
    )


class CourseImportSchema(BaseModel):
    name_i18n: str = Field(
        title="Internationalized Name",
        description="A dictionary mapping language codes (e.g., 'en', 'es') to the course name.",
        examples=[
            {"en": "Introduction to Python", "es": "Introducción a Python"},
        ],
    )
    level_id: int
    user_submitted: bool


class CourseAdmin(CustomModelView, model=Course):
    icon = "fa-solid fa-book-open"

    column_list = (
        Course.id,
        Course.name_i18n,
        Course.level,
        Course.user_submitted,
        Course.created_at,
    )
    column_searchable_list = (Course.name_i18n,)
    column_sortable_list = (
        Course.id,
        Course.name_i18n,
        Course.user_submitted,
        Course.created_at,
    )
    column_details_list = (
        Course.id,
        Course.name_i18n,
        Course.level,
        Course.user_submitted,
        Course.created_at,
    )

    form_columns = (
        "name_i18n",
        "level",
        "user_submitted",
    )


class EducationInfoImportSchema(BaseModel):
    level: int
    course: int
    institution: int
    stage: int


class EducationInfoAdmin(CustomModelView, model=EducationInfo):
    icon = "fa-solid fa-graduation-cap"

    column_list = (
        EducationInfo.id,
        EducationInfo.course,
        EducationInfo.institution,
        EducationInfo.stage,
        EducationInfo.level,
    )
    column_searchable_list = (
        EducationInfo.course,
        EducationInfo.institution,
        EducationInfo.stage,
        EducationInfo.level,
    )
    column_sortable_list = (
        EducationInfo.id,
        EducationInfo.course,
        EducationInfo.institution,
        EducationInfo.stage,
    )

    form_columns = (
        EducationInfo.level,
        EducationInfo.course,
        EducationInfo.institution,
        EducationInfo.stage,
    )
