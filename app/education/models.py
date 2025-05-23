from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.base import Base
from app.users.models import EducationLevel

if TYPE_CHECKING:
    pass


class Institution(Base):
    name: Mapped[str] = mapped_column(String(120))
    user_submitted: Mapped[bool] = mapped_column(default=False)
    institution_type: Mapped[str] = mapped_column(String(50))  # discriminator column
    inep_code: Mapped[str | None] = mapped_column(String(40), default="")

    __table_args__ = (
        Index(
            "unique_inep_code",
            "inep_code",
            unique=True,
            postgresql_where=inep_code != "",
        ),
    )

    __mapper_args__ = {
        "polymorphic_identity": "institution",
        "polymorphic_on": institution_type,
    }

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


class Education(Base):
    level: Mapped[EducationLevel] = mapped_column(default=EducationLevel.UNKNOWN)

    institution_id: Mapped[int | None] = mapped_column(ForeignKey("institution.id"))
    institution: Mapped["Institution | None"] = relationship(lazy="raise_on_sql")

    course_id: Mapped[int | None] = mapped_column(ForeignKey("course.id"))
    course: Mapped["Course | None"] = relationship(lazy="raise_on_sql")
