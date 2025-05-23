from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    ScalarSelect,
    String,
    func,
    select,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, aliased, mapped_column, relationship

from app.base import ASYNC_PARENT_FOREIGN_KEY_OPTIONS, Base
from app.currency.models import HasCurrencyTransactions
from app.flows.models import Flow

if TYPE_CHECKING:
    from app.chat.models import UserWebsocketInfo
    from app.education.models import Education
    from app.fcm.models import FCMDevice

STARTING_BALANCE = 1000


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

    is_premium: Mapped[bool] = mapped_column(default=False)

    balance: Mapped[int] = mapped_column(
        CheckConstraint("balance >= 0", name="user_balance_check"),
        default=STARTING_BALANCE,
    )

    is_bot: Mapped[bool] = mapped_column(default=False)
    bot_difficulty: Mapped[float | None] = mapped_column(default=None)

    signup_source: Mapped[SignupSource] = mapped_column(default=SignupSource.UNKNOWN)

    current_education_id: Mapped[int | None] = mapped_column(ForeignKey("education.id"))
    current_education: Mapped["Education | None"] = relationship(
        foreign_keys=[current_education_id], lazy="raise_on_sql"
    )

    intended_education_id: Mapped[int | None] = mapped_column(
        ForeignKey("education.id")
    )
    intended_education: Mapped["Education | None"] = relationship(
        foreign_keys=[intended_education_id], lazy="raise_on_sql"
    )

    # referral fields
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

    profile: Mapped["UserProfile"] = relationship(
        back_populates="user",
        lazy="raise_on_sql",
        cascade=ASYNC_PARENT_FOREIGN_KEY_OPTIONS,
        passive_deletes=True,
    )
    flows_created: Mapped[list["Flow"]] = relationship(
        back_populates="created_by",
        foreign_keys=[Flow.created_by_id],
        lazy="raise_on_sql",
    )

    user_websocket_info: Mapped["UserWebsocketInfo"] = relationship(
        back_populates="user",
        lazy="raise_on_sql",
        cascade=ASYNC_PARENT_FOREIGN_KEY_OPTIONS,
        passive_deletes=True,
    )

    fcm_device: Mapped["FCMDevice"] = relationship(
        back_populates="user",
        lazy="raise_on_sql",
        cascade=ASYNC_PARENT_FOREIGN_KEY_OPTIONS,
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

    @property
    def social_score(self) -> int:
        """Access social_score from profile."""
        return self.profile.social_score

    @property
    def xp_score(self) -> int:
        """Access xp_score from profile."""
        return self.profile.xp_score


class UserProfile(Base):
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), unique=True
    )
    user: Mapped["User"] = relationship(
        back_populates="profile",
    )
    social_score: Mapped[int] = mapped_column(default=0)
    xp_score: Mapped[int] = mapped_column(default=0)
