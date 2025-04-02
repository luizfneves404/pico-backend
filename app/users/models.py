from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    ScalarSelect,
    String,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, aliased, mapped_column, relationship

from app.base import Base
from app.currency.models import HasCurrencyTransactions
from app.quiz.models import Session

if TYPE_CHECKING:
    from essays.models import Essay
    from tournaments.models import Tournament, TournamentParticipation

    from app.chat.models import UserWebSocketInfo
    from app.quiz.models import JoinableSession, UserInfo
    from app.schools.models import School


class EducationLevel(StrEnum):
    MIDDLE_SCHOOL = "MS"
    FIRST_YEAR_HIGH_SCHOOL = "FYHS"
    SECOND_YEAR_HIGH_SCHOOL = "SYHS"
    THIRD_YEAR_HIGH_SCHOOL = "TYHS"
    HIGH_SCHOOL_COMPLETE = "HSG"
    COLLEGE = "COL"
    UNKNOWN = ""


class SignupSource(StrEnum):
    REFERRAL = "referral"
    SOCIAL = "social"
    INTERNET = "internet"
    TEACHER = "teacher"
    EVENT = "event"
    OTHER = "other"
    UNKNOWN = ""


class User(Base, HasCurrencyTransactions):
    username: Mapped[str] = mapped_column(String(50), unique=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    phone_number: Mapped[str] = mapped_column(String(25), unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_superuser: Mapped[bool] = mapped_column(default=False)

    education_level: Mapped[EducationLevel] = mapped_column(
        default=EducationLevel.UNKNOWN
    )
    is_premium: Mapped[bool] = mapped_column(default=False)

    commitment: Mapped[int] = mapped_column(default=20)

    balance: Mapped[int] = mapped_column(
        CheckConstraint("balance >= 0", name="user_balance_check"), default=0
    )

    is_bot: Mapped[bool] = mapped_column(default=False)
    bot_difficulty: Mapped[float | None] = mapped_column(default=None)

    signup_source: Mapped[SignupSource] = mapped_column(default=SignupSource.UNKNOWN)

    school_id: Mapped[int | None] = mapped_column(ForeignKey("school.id"))
    school: Mapped["School | None"] = relationship(
        back_populates="users", lazy="raise_on_sql"
    )

    chosen_college_id: Mapped[int | None] = mapped_column(
        ForeignKey("college.id"),
    )
    chosen_college: Mapped["College | None"] = relationship(
        back_populates="users", lazy="raise_on_sql"
    )

    chosen_course_id: Mapped[int | None] = mapped_column(
        ForeignKey("course.id"),
    )
    chosen_course: Mapped["Course | None"] = relationship(
        back_populates="users", lazy="raise_on_sql"
    )

    referred_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id"),
    )
    referred_by: Mapped["User | None"] = relationship(
        foreign_keys=[referred_by_id],
        remote_side="User.id",
        back_populates="referrals",
        lazy="raise_on_sql",
    )
    referrals: Mapped[list["User"]] = relationship(
        back_populates="referred_by",
        foreign_keys=[referred_by_id],
        lazy="raise_on_sql",
    )

    user_info: Mapped["UserInfo"] = relationship(
        back_populates="user",
        lazy="raise_on_sql",
        cascade="save-update, merge, expunge, delete, delete-orphan",
        passive_deletes=True,
    )
    sessions_created: Mapped[list["Session"]] = relationship(
        back_populates="created_by",
        foreign_keys=[Session.created_by_id],
        lazy="raise_on_sql",
    )
    sessions_participated: Mapped[list["JoinableSession"]] = relationship(
        back_populates="participants",
        secondary="session_participation",
        lazy="raise_on_sql",
        viewonly=True,
    )

    essays: Mapped[list["Essay"]] = relationship(
        back_populates="author",
        lazy="raise_on_sql",
        cascade="save-update, merge, expunge, delete, delete-orphan",
        passive_deletes=True,
    )

    user_websocket_info: Mapped["UserWebSocketInfo"] = relationship(
        back_populates="user",
        lazy="raise_on_sql",
        cascade="save-update, merge, expunge, delete, delete-orphan",
        passive_deletes=True,
    )

    tournaments_participating: Mapped[list["Tournament"]] = relationship(
        back_populates="participants",
        secondary="tournament_participation",
        lazy="raise_on_sql",
        viewonly=True,
    )

    tournament_participations: Mapped[list["TournamentParticipation"]] = relationship(
        back_populates="user",
        lazy="raise_on_sql",
        cascade="save-update, merge, expunge, delete, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint(
            # either is not bot and doesnt have bot_difficulty
            "is_bot = False AND bot_difficulty IS NULL OR "
            # or is bot and has bot difficulty
            "is_bot = True AND bot_difficulty IS NOT NULL",
            name="bot_difficulty_check",
        ),
        Index(
            "ix_user_username_lower",
            func.lower(username),
            unique=True,
        ),  # the username is stored as it comes (should be trimmed though), but we use this index to make queries case insensitive and disallow duplicates
        Index("ix_user_email_lower", func.lower(email), unique=True),
    )

    @hybrid_property
    def referral_count(self) -> int:
        return len(self.referrals)

    @referral_count.inplace.expression
    @classmethod
    def _referral_count_expression(cls) -> ScalarSelect[int]:
        """Return a SQL expression for the count when used in a query."""
        # Create an alias for the User table to use in the subquery
        ReferredUser = aliased(User, name="referred_users")

        # Build the subquery with explicit FROM clause and correlation
        referral_count = (
            select(func.count())
            .select_from(ReferredUser)
            .where(ReferredUser.referred_by_id == cls.id)
            .scalar_subquery()
        )

        return referral_count

    def __str__(self):
        return self.username


class CourseCollege(Base):
    __table_args__ = (UniqueConstraint("course_id", "college_id"),)

    course_id: Mapped[int] = mapped_column(ForeignKey("course.id", ondelete="CASCADE"))
    college_id: Mapped[int] = mapped_column(
        ForeignKey("college.id", ondelete="CASCADE")
    )


class College(Base):
    name: Mapped[str] = mapped_column(unique=True)
    user_submitted: Mapped[bool] = mapped_column()
    courses: Mapped[list["Course"]] = relationship(
        back_populates="colleges", secondary="course_college", lazy="raise_on_sql"
    )
    users: Mapped[list["User"]] = relationship(
        back_populates="chosen_college", lazy="raise_on_sql"
    )

    def __str__(self):
        return self.name


class Course(Base):
    name: Mapped[str] = mapped_column(unique=True)
    user_submitted: Mapped[bool] = mapped_column()
    colleges: Mapped[list["College"]] = relationship(
        back_populates="courses", secondary="course_college", lazy="raise_on_sql"
    )
    users: Mapped[list["User"]] = relationship(
        back_populates="chosen_course", lazy="raise_on_sql"
    )

    def __str__(self):
        return self.name
