from enum import StrEnum
from typing import TYPE_CHECKING

from geoalchemy2 import Geography, WKBElement
from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint, inspect
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.base import Base
from app.users.models import User

if TYPE_CHECKING:
    from app.countries.models import Country


class AdministrativeCategory(StrEnum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class InstitutionType(StrEnum):
    SCHOOL = "school"
    COLLEGE = "college"


class Institution(Base, kw_only=True):
    """Represents an institution offering an education level."""

    name: Mapped[str] = mapped_column(String(120))
    country_id: Mapped[int] = mapped_column(ForeignKey("country.id"), default=None)
    country: Mapped["Country"] = relationship(lazy="raise_on_sql", default=None)
    level_id: Mapped[int] = mapped_column(
        ForeignKey("education_level.id"), default=None
    )
    level: Mapped["EducationLevel"] = relationship(
        lazy="raise_on_sql",
        back_populates="institutions",
        default=None,
    )
    institution_type: Mapped[InstitutionType] = mapped_column()
    user_submitted: Mapped[bool] = mapped_column()
    administrative_category: Mapped[AdministrativeCategory] = mapped_column()

    government_issued_code: Mapped[str] = mapped_column(String(50), default="")
    location: Mapped[WKBElement | None] = mapped_column(
        Geography(geometry_type="POINT", srid=4326), default=None
    )
    address: Mapped[str] = mapped_column(Text, default="")
    city: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (
        Index(
            "unique_government_code_per_country",
            "government_issued_code",
            "country_id",
            unique=True,
            postgresql_where=government_issued_code != "",
        ),
    )

    def __str__(self) -> str:
        return self.name


class Course(Base, kw_only=True):
    name_i18n: Mapped[dict[str, str]] = mapped_column(JSON)
    user_submitted: Mapped[bool] = mapped_column()
    level_id: Mapped[int] = mapped_column(
        ForeignKey("education_level.id"), default=None
    )

    level: Mapped["EducationLevel"] = relationship(
        lazy="raise_on_sql",
        back_populates="courses",
        default=None,
    )

    def __str__(self) -> str:
        return str(self.name_i18n["en"] if "en" in self.name_i18n else self.name_i18n)


class LevelStage(Base, kw_only=True):
    """Represents a stage of an education level.
    For example, "First grade" would be a stage of the "High School" level.
    """

    name: Mapped[str] = mapped_column(String(120))
    level_id: Mapped[int] = mapped_column(
        ForeignKey("education_level.id"), default=None
    )
    level: Mapped["EducationLevel"] = relationship(
        lazy="raise_on_sql",
        back_populates="stages",
        default=None,
    )

    country_id: Mapped[int | None] = mapped_column(
        ForeignKey("country.id"), default=None
    )
    country: Mapped["Country | None"] = relationship(lazy="raise_on_sql", default=None)
    is_default: Mapped[bool] = mapped_column(default=False)

    __table_args__ = (
        UniqueConstraint(
            "name",
            "level_id",
            "country_id",
            name="unique_level_stage_per_country",
        ),
    )

    def __str__(self) -> str:
        return str(self.name)


class EducationLevel(Base, kw_only=True):
    name_i18n: Mapped[dict[str, str]] = mapped_column(JSON)

    stages: Mapped[list["LevelStage"]] = relationship(
        back_populates="level",
        lazy="raise_on_sql",
        default_factory=list,
    )
    courses: Mapped[list["Course"]] = relationship(
        back_populates="level",
        lazy="raise_on_sql",
        default_factory=list,
    )
    institutions: Mapped[list["Institution"]] = relationship(
        back_populates="level",
        lazy="raise_on_sql",
        default_factory=list,
    )

    def __str__(self) -> str:
        return str(self.name_i18n["en"] if "en" in self.name_i18n else self.name_i18n)


class EducationInfo(Base, kw_only=True):
    level_id: Mapped[int] = mapped_column(
        ForeignKey("education_level.id"), default=None
    )
    level: Mapped["EducationLevel"] = relationship(
        lazy="raise_on_sql",
        default=None,
    )

    institution_id: Mapped[int | None] = mapped_column(
        ForeignKey("institution.id"), default=None
    )
    institution: Mapped["Institution | None"] = relationship(
        lazy="raise_on_sql",
        default=None,
    )
    stage_id: Mapped[int | None] = mapped_column(
        ForeignKey("level_stage.id"), default=None
    )
    stage: Mapped["LevelStage | None"] = relationship(
        lazy="raise_on_sql",
        default=None,
    )
    course_id: Mapped[int | None] = mapped_column(ForeignKey("course.id"), default=None)
    course: Mapped["Course | None"] = relationship(
        lazy="raise_on_sql",
        default=None,
    )
    current_education_user: Mapped["User | None"] = relationship(
        lazy="raise_on_sql",
        default=None,
        back_populates="current_education",
        foreign_keys=[User.current_education_id],
    )
    intended_education_user: Mapped["User | None"] = relationship(
        lazy="raise_on_sql",
        default=None,
        back_populates="intended_education",
        foreign_keys=[User.intended_education_id],
    )

    def __str__(self) -> str:
        insp = inspect(self)
        string = f"Education Info {self.id}"

        if "level" not in insp.unloaded:
            string += f" - {self.level.name_i18n['en'] if 'en' in self.level.name_i18n else self.level.name_i18n}"

        if "institution" not in insp.unloaded and self.institution:
            string += f" - {self.institution.name}"

        if "stage" not in insp.unloaded and self.stage:
            string += f" - {self.stage.name}"

        if "course" not in insp.unloaded and self.course:
            string += f" - {self.course.name_i18n['en'] if 'en' in self.course.name_i18n else self.course.name_i18n}"

        return string
