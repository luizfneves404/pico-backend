from enum import StrEnum
from typing import TYPE_CHECKING

from geoalchemy2 import Geography, WKBElement
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
from app.flows.models import Flow

if TYPE_CHECKING:
    from app.community.models import Community
    from app.countries.models import Country
    from app.education.models import EducationInfo
    from app.fcm.models import FCMDevice
    from app.ws.models import UserOnlineInfo


class SignupSource(StrEnum):
    REFERRAL = "referral"
    SOCIAL = "social"
    INTERNET = "internet"
    TEACHER = "teacher"
    EVENT = "event"
    OTHER = "other"
    UNKNOWN = ""


class User(Base, kw_only=True):
    name: Mapped[str] = mapped_column(String(150))
    username: Mapped[str] = mapped_column(String(50), unique=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    phone_number: Mapped[str] = mapped_column(String(25), default="")
    hashed_password: Mapped[str] = mapped_column(String(255), default="")
    google_id: Mapped[str] = mapped_column(String(255), server_default="")
    apple_id: Mapped[str] = mapped_column(String(255), server_default="")

    is_superuser: Mapped[bool] = mapped_column(default=False)

    is_bot: Mapped[bool] = mapped_column(default=False)
    bot_difficulty: Mapped[float | None] = mapped_column(default=None)

    signup_source: Mapped[SignupSource] = mapped_column(default=SignupSource.UNKNOWN)

    current_education_id: Mapped[int | None] = mapped_column(
        ForeignKey("education_info.id"), default=None
    )
    current_education: Mapped["EducationInfo | None"] = relationship(
        foreign_keys=[current_education_id],
        lazy="raise_on_sql",
        default=None,
    )

    intended_education_id: Mapped[int | None] = mapped_column(
        ForeignKey("education_info.id"), default=None
    )
    intended_education: Mapped["EducationInfo | None"] = relationship(
        foreign_keys=[intended_education_id],
        lazy="raise_on_sql",
        default=None,
    )

    country_code: Mapped[str | None] = mapped_column(
        ForeignKey("country.code"), default=None
    )
    country: Mapped["Country | None"] = relationship(
        foreign_keys=[country_code], lazy="raise_on_sql", default=None
    )

    location: Mapped[WKBElement | None] = mapped_column(
        Geography(geometry_type="POINT", srid=4326), default=None
    )

    social_score: Mapped[int] = mapped_column(default=0)
    xp_score: Mapped[int] = mapped_column(default=0)

    # referral fields
    referred_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id"), default=None
    )
    referred_by: Mapped["User | None"] = relationship(
        foreign_keys=[referred_by_id],
        remote_side="User.id",
        back_populates="referrals",
        lazy="raise_on_sql",
        default=None,
    )
    referrals: Mapped[list["User"]] = relationship(
        back_populates="referred_by",
        foreign_keys=[referred_by_id],
        lazy="raise_on_sql",
        default_factory=list,
    )

    flows_created: Mapped[list["Flow"]] = relationship(
        back_populates="created_by",
        foreign_keys=[Flow.created_by_id],
        lazy="raise_on_sql",
        default_factory=list,
    )

    user_online_info: Mapped["UserOnlineInfo"] = relationship(
        back_populates="user",
        lazy="raise_on_sql",
        cascade=ASYNC_PARENT_FOREIGN_KEY_OPTIONS,
        passive_deletes=True,
        default=None,
    )

    fcm_device: Mapped["FCMDevice"] = relationship(
        back_populates="user",
        lazy="raise_on_sql",
        cascade=ASYNC_PARENT_FOREIGN_KEY_OPTIONS,
        passive_deletes=True,
        default=None,
    )

    communities: Mapped[list["Community"]] = relationship(
        back_populates="users",
        lazy="raise_on_sql",
        secondary="community_user",
        default_factory=list,
    )

    __table_args__ = (
        CheckConstraint(
            # either is not bot and doesnt have bot_difficulty
            "is_bot = False AND bot_difficulty IS NULL OR "
            # or is bot and has bot difficulty
            "is_bot = True AND bot_difficulty IS NOT NULL",
            name="bot_difficulty_check",
        ),
        CheckConstraint(
            "(google_id != '' AND apple_id = '' AND hashed_password = '') OR "
            "(google_id = '' AND apple_id != '' AND hashed_password = '') OR "
            "(google_id = '' AND apple_id = '' AND hashed_password != '') OR "
            "(google_id = '' AND apple_id = '' AND hashed_password = '')",  # this one cannot login
            name="google_or_apple_or_password_exclusive_check",
        ),
        Index("ix_user_email_lower", func.lower(email), unique=True),
        Index(
            "unique_google_id",
            "google_id",
            unique=True,
            postgresql_where=google_id != "",
        ),
        Index(
            "unique_apple_id",
            "apple_id",
            unique=True,
            postgresql_where=apple_id != "",
        ),
        Index(
            "unique_current_education_id",
            "current_education_id",
            unique=True,
            postgresql_where=current_education_id.is_(None),
        ),
        Index(
            "unique_intended_education_id",
            "intended_education_id",
            unique=True,
            postgresql_where=intended_education_id.is_(None),
        ),
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
