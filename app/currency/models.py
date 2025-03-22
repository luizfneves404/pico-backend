from enum import StrEnum
from typing import TYPE_CHECKING

from base import Base
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from users.models import User


class CurrencyType(StrEnum):
    PRICE = "price"
    REWARD = "reward"


class CurrencyAction(StrEnum):
    # User related actions
    USER_REFERRED_ANOTHER = "user_referred_another"
    ANOTHER_USER_REFERRED_ME = "another_user_referred_me"

    # Ranking related actions
    DYNAMIC_RANKING_REWARD = "dynamic_ranking_reward"
    SCHOOL_DYNAMIC_RANKING_REWARD = "school_dynamic_ranking_reward"

    # Quiz related actions
    CUSTOM_QUIZ_CREATION = "custom_quiz_creation"
    CUSTOM_QUIZ_JOIN = "custom_quiz_join"
    QUIZ_CREATION = "quiz_creation"
    QUIZ_JOIN = "quiz_join"

    # Duel related actions
    CUSTOM_DUEL_CREATION = "custom_duel_creation"
    CUSTOM_DUEL_JOIN = "custom_duel_join"
    DUEL_CREATION = "duel_creation"
    DUEL_JOIN = "duel_join"

    # Essay related actions
    ESSAY_CREATION = "essay_creation"

    # Challenge related actions
    CUSTOM_CHALLENGE_CREATION = "custom_challenge_creation"
    CUSTOM_CHALLENGE_JOIN = "custom_challenge_join"
    CUSTOM_CHALLENGE_COMMISSION = "custom_challenge_commission"
    CHALLENGE_CREATION = "challenge_creation"
    CHALLENGE_JOIN = "challenge_join"
    CHALLENGE_COMMISSION = "challenge_commission"


class Currency(Base):
    __table_args__ = (
        Index(
            "unique_default_currency_per_action_type",
            "action",
            "currency_type",
            "is_default",
            unique=True,
        ),
    )

    value: Mapped[int] = mapped_column(
        CheckConstraint("value >= 0", name="currency_currency_value_check"),
    )
    currency_type: Mapped[CurrencyType] = mapped_column()
    is_default: Mapped[bool] = mapped_column(Boolean)
    description: Mapped[str] = mapped_column(String(255))
    action: Mapped[CurrencyAction] = mapped_column()
    currency_transaction: Mapped[list["CurrencyTransaction"]] = relationship(
        back_populates="currency"
    )


class CurrencyTransaction(Base):
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    user: Mapped["User"] = relationship(back_populates="currency_transactions")
    description: Mapped[str] = mapped_column(String(255))
    object_id: Mapped[int | None] = mapped_column()
    content_type_id: Mapped[int | None] = mapped_column()
    currency_id: Mapped[int | None] = mapped_column()
    amount: Mapped[int | None] = mapped_column()
    currency: Mapped["Currency"] = relationship(back_populates="currency_transactions")
