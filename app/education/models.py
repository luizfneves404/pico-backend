from enum import StrEnum

from geoalchemy2 import Geography, WKBElement
from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.base import Base


class AdministrativeCategory(StrEnum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"


class Institution(Base):
    name: Mapped[str] = mapped_column(String(120))
    user_submitted: Mapped[bool] = mapped_column(default=False)
    institution_type: Mapped[str] = mapped_column(String(50))  # discriminator column
    inep_code: Mapped[str] = mapped_column(String(40), default="")
    location: Mapped[WKBElement | None] = mapped_column(
        Geography(geometry_type="POINT", srid=4326)
    )
    administrative_category: Mapped[AdministrativeCategory | None] = mapped_column(
        String(50)
    )

    __mapper_args__ = {
        "polymorphic_identity": "institution",
        "polymorphic_on": institution_type,
    }

    __table_args__ = (
        Index(
            "unique_inep_code",
            "inep_code",
            unique=True,
            postgresql_where=inep_code != "",
        ),
    )

    def __str__(self) -> str:
        return self.name


class School(Institution):
    __mapper_args__ = {
        "polymorphic_identity": "school",
    }


class College(Institution):
    courses: Mapped[list["Course"]] = relationship(
        back_populates="colleges", secondary="course_college", lazy="raise_on_sql"
    )

    __mapper_args__ = {
        "polymorphic_identity": "college",
    }


class CourseCollege(Base):
    __table_args__ = (UniqueConstraint("course_id", "college_id"),)

    course_id: Mapped[int] = mapped_column(ForeignKey("course.id", ondelete="CASCADE"))
    college_id: Mapped[int] = mapped_column(
        ForeignKey("institution.id", ondelete="CASCADE")
    )


class Course(Base):
    name: Mapped[str] = mapped_column(String(120))
    user_submitted: Mapped[bool] = mapped_column(default=False)
    colleges: Mapped[list["College"]] = relationship(
        back_populates="courses", secondary="course_college", lazy="raise_on_sql"
    )

    def __str__(self) -> str:
        return self.name


class EducationLevel(StrEnum):
    MIDDLE_SCHOOL = "MS"
    FIRST_GRADE_HIGH_SCHOOL = "FGHS"
    SECOND_GRADE_HIGH_SCHOOL = "SGHS"
    THIRD_GRADE_HIGH_SCHOOL = "TGHS"
    HIGH_SCHOOL_COMPLETE = "HSG"
    COLLEGE = "COL"
    OTHER = "OTHER"
    UNKNOWN = ""


class Education(Base):
    level: Mapped[EducationLevel] = mapped_column(default=EducationLevel.UNKNOWN)

    institution_id: Mapped[int | None] = mapped_column(ForeignKey("institution.id"))
    institution: Mapped["Institution | None"] = relationship(lazy="raise_on_sql")

    course_id: Mapped[int | None] = mapped_column(ForeignKey("course.id"))
    course: Mapped["Course | None"] = relationship(lazy="raise_on_sql")
