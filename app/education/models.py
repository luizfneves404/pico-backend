from enum import StrEnum
from typing import TYPE_CHECKING

from geoalchemy2 import Geography, WKBElement
from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.base import Base

if TYPE_CHECKING:
    from app.countries.models import Country


class AdministrativeCategory(StrEnum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class InstitutionType(StrEnum):
    INSTITUTION = "institution"
    SCHOOL = "school"
    COLLEGE = "college"


class Institution(Base):
    """Represents an institution offering an education level."""

    name: Mapped[str] = mapped_column(String(120))
    user_submitted: Mapped[bool] = mapped_column(default=False)
    institution_type: Mapped[InstitutionType] = mapped_column()
    government_issued_code: Mapped[str] = mapped_column(String(50), default="")
    country_code: Mapped[str] = mapped_column(ForeignKey("country.code"))
    country: Mapped["Country"] = relationship(lazy="raise_on_sql")
    location: Mapped[WKBElement | None] = mapped_column(
        Geography(geometry_type="POINT", srid=4326)
    )
    address: Mapped[str] = mapped_column(Text, default="")
    city: Mapped[str] = mapped_column(Text, default="")
    administrative_category: Mapped[AdministrativeCategory] = mapped_column(
        String(50), default=AdministrativeCategory.UNKNOWN
    )
    level_id: Mapped[int] = mapped_column(ForeignKey("education_level.id"))
    level: Mapped["EducationLevel"] = relationship(
        lazy="raise_on_sql",
        back_populates="institutions",
    )

    __mapper_args__ = {
        "polymorphic_identity": InstitutionType.INSTITUTION,
        "polymorphic_on": institution_type,
    }

    __table_args__ = (
        Index(
            "unique_government_code_per_country",
            "government_issued_code",
            "country_code",
            unique=True,
            postgresql_where=government_issued_code != "",
        ),
    )

    def __str__(self) -> str:
        return self.name


class School(Institution):
    __mapper_args__ = {
        "polymorphic_identity": InstitutionType.SCHOOL,
    }


class College(Institution):
    __mapper_args__ = {
        "polymorphic_identity": InstitutionType.COLLEGE,
    }


class Course(Base):
    name_i18n: Mapped[dict[str, str]] = mapped_column(JSON)
    user_submitted: Mapped[bool] = mapped_column(default=False)

    level_id: Mapped[int] = mapped_column(ForeignKey("education_level.id"))
    level: Mapped["EducationLevel"] = relationship(
        lazy="raise_on_sql",
        back_populates="courses",
    )

    def __str__(self) -> str:
        return str(self.name_i18n)


class LevelStage(Base):
    """Represents a stage of an education level.
    For example, "First grade" would be a stage of the "High School" level.
    """

    name: Mapped[str] = mapped_column(String(120))

    country_code: Mapped[str | None] = mapped_column(ForeignKey("country.code"))
    country: Mapped["Country | None"] = relationship(lazy="raise_on_sql")

    level_id: Mapped[int] = mapped_column(ForeignKey("education_level.id"))
    level: Mapped["EducationLevel"] = relationship(
        lazy="raise_on_sql",
        back_populates="stages",
    )

    is_default: Mapped[bool] = mapped_column(default=False)

    __table_args__ = (
        UniqueConstraint(
            "name",
            "level_id",
            "country_code",
            name="unique_level_stage_per_country",
        ),
    )


class EducationLevel(Base):
    name_i18n: Mapped[dict[str, str]] = mapped_column(JSON)
    stages: Mapped[list["LevelStage"]] = relationship(
        back_populates="level",
        lazy="raise_on_sql",
    )
    courses: Mapped[list["Course"]] = relationship(
        back_populates="level",
        lazy="raise_on_sql",
    )

    institutions: Mapped[list["Institution"]] = relationship(
        back_populates="level",
        lazy="raise_on_sql",
    )


class EducationInfo(Base):
    level_id: Mapped[int] = mapped_column(
        ForeignKey("education_level.id", ondelete="SET NULL")
    )
    level: Mapped["EducationLevel"] = relationship(lazy="raise_on_sql")

    institution_id: Mapped[int | None] = mapped_column(ForeignKey("institution.id"))
    institution: Mapped["Institution | None"] = relationship(lazy="raise_on_sql")

    stage_id: Mapped[int | None] = mapped_column(ForeignKey("level_stage.id"))
    stage: Mapped["LevelStage | None"] = relationship(lazy="raise_on_sql")

    course_id: Mapped[int | None] = mapped_column(ForeignKey("course.id"))
    course: Mapped["Course | None"] = relationship(lazy="raise_on_sql")
