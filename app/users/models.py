from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from base import Base
from sqlalchemy import CheckConstraint, ForeignKey, Index, func, select
from sqlalchemy.orm import Mapped, aliased, deferred, mapped_column, relationship

if TYPE_CHECKING:
    from chatrooms.models import Chatroom, Membership, Message


class EducationLevel(Enum):
    MIDDLE_SCHOOL = "MS"
    FIRST_YEAR_HIGH_SCHOOL = "FYHS"
    SECOND_YEAR_HIGH_SCHOOL = "SYHS"
    THIRD_YEAR_HIGH_SCHOOL = "TYHS"
    HIGH_SCHOOL_COMPLETE = "HSG"
    COLLEGE = "COL"
    UNKNOWN = ""


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    username: Mapped[str] = mapped_column(unique=True)
    email: Mapped[str] = mapped_column(unique=True)
    phone_number: Mapped[str] = mapped_column(unique=True)
    hashed_password: Mapped[str]
    school_id: Mapped[int | None] = mapped_column(
        ForeignKey("school.id"), nullable=True
    )
    school: Mapped["School"] = relationship(back_populates="users", lazy="raise_on_sql")

    education_level: Mapped[EducationLevel] = mapped_column(
        default=EducationLevel.UNKNOWN
    )  # no need for create_constraint=True since it is using a native enum, which already constrains

    chosen_college_id: Mapped[int | None] = mapped_column(
        ForeignKey("college.id"), nullable=True
    )
    chosen_college: Mapped["College"] = relationship(
        back_populates="users", lazy="raise_on_sql"
    )

    chosen_course_id: Mapped[int | None] = mapped_column(
        ForeignKey("course.id"), nullable=True
    )
    chosen_course: Mapped["Course"] = relationship(
        back_populates="users", lazy="raise_on_sql"
    )

    is_premium: Mapped[bool] = mapped_column(default=False)

    referred_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id"), nullable=True
    )
    referred_by: Mapped["User"] = relationship(
        remote_side=[id], back_populates="referrals", lazy="raise_on_sql"
    )
    referrals: Mapped[list["User"]] = relationship(
        back_populates="referred_by", lazy="raise_on_sql"
    )

    commitment: Mapped[int] = mapped_column(default=20)

    balance: Mapped[int] = mapped_column(default=0)

    is_bot: Mapped[bool] = mapped_column(default=False)
    bot_difficulty: Mapped[float | None] = mapped_column(nullable=True, default=None)

    chatrooms: Mapped[list["Chatroom"]] = relationship(
        back_populates="members",
        secondary="membership",
        viewonly=True,
        lazy="raise_on_sql",
    )
    membership_set: Mapped[list["Membership"]] = relationship(
        back_populates="user", lazy="raise_on_sql"
    )
    messages: Mapped[list["Message"]] = relationship(
        back_populates="sender", lazy="raise_on_sql"
    )

    __table_args__ = (
        CheckConstraint(
            # either is not bot and doesnt have bot_difficulty
            "is_bot = False AND bot_difficulty IS NULL OR "
            # or is bot and has bot difficulty
            "is_bot = True AND bot_difficulty IS NOT NULL",
            name="bot_difficulty_check",
        ),
        Index("ix_user_username_lower", func.lower(username), unique=True),
    )


class School(Base):
    __tablename__ = "school"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column()
    users: Mapped[list["User"]] = relationship(
        back_populates="school", lazy="raise_on_sql"
    )


class CourseCollege(Base):
    __tablename__ = "course_college"

    course_id: Mapped[int] = mapped_column(ForeignKey("course.id"), primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("college.id"), primary_key=True)


class College(Base):
    __tablename__ = "college"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column()
    courses: Mapped[list["Course"]] = relationship(
        back_populates="colleges", secondary="course_college", lazy="raise_on_sql"
    )
    users: Mapped[list["User"]] = relationship(
        back_populates="chosen_college", lazy="raise_on_sql"
    )


class Course(Base):
    __tablename__ = "course"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column()
    colleges: Mapped[list["College"]] = relationship(
        back_populates="courses", secondary="course_college", lazy="raise_on_sql"
    )
    users: Mapped[list["User"]] = relationship(
        back_populates="chosen_course", lazy="raise_on_sql"
    )


def init():
    referral = aliased(User)
    User.referral_count = deferred(
        select(func.count(referral.id).label("referral_count"))
        .where(referral.referred_by_id == User.id)
        .scalar_subquery(),
        raiseload=True,
    )
