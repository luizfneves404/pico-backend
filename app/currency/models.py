from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship

from app.base import Base

if TYPE_CHECKING:
    from app.users.models import User


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
    is_default: Mapped[bool] = mapped_column()
    description: Mapped[str] = mapped_column(String(255))
    action: Mapped[CurrencyAction] = mapped_column()
    currency_transaction: Mapped[list["CurrencyTransaction"]] = relationship(
        back_populates="currency"
    )


class EntityAssociation(Base):
    """Associates currency transactions with various entity types."""

    discriminator: Mapped[str] = mapped_column(String(50))
    """Refers to the type of parent entity."""

    __mapper_args__ = {"polymorphic_on": discriminator}

    currency_transactions: Mapped[list["CurrencyTransaction"]] = relationship(
        back_populates="entity_association"
    )


class CurrencyTransaction(Base):
    description: Mapped[str] = mapped_column(String(255))
    amount: Mapped[int | None] = mapped_column()

    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    user: Mapped["User"] = relationship()

    currency_id: Mapped[int | None] = mapped_column(ForeignKey("currency.id"))
    currency: Mapped["Currency"] = relationship()

    entity_association_id: Mapped[int | None] = mapped_column(
        ForeignKey("entity_association.id")
    )
    entity_association: Mapped["EntityAssociation"] = relationship(
        back_populates="currency_transactions"
    )

    entity = association_proxy("entity_association", "parent")


class HasCurrencyTransactions:
    """Mixin for entities that can have currency transactions."""

    @declared_attr
    @classmethod
    def entity_association_id(cls) -> Mapped[int | None]:
        return mapped_column(
            Integer, ForeignKey("entity_association.id"), nullable=True
        )

    @declared_attr
    @classmethod
    def entity_association(cls):
        name = cls.__name__
        discriminator = name.lower()

        # Create a specific association subclass for this entity type
        assoc_cls = type(
            f"{name}EntityAssociation",
            (EntityAssociation,),
            {
                "__tablename__": None,  # Don't create a new table
                "__mapper_args__": {"polymorphic_identity": discriminator},
            },
        )

        # Create an association proxy for convenient access to currency transactions
        cls.currency_transactions = association_proxy(
            "entity_association",
            "currency_transactions",
            creator=lambda transactions: assoc_cls(currency_transactions=transactions),
        )

        return relationship(assoc_cls, backref=backref("parent", uselist=False))
