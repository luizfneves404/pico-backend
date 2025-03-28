import decimal
from typing import TYPE_CHECKING

from base import Base
from currency.models import HasCurrencyTransactions
from sqlalchemy import (
    Double,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.users.models import User


class EssayTopic(Base):
    name: Mapped[str] = mapped_column(String(255), unique=True)

    essays: Mapped[list["Essay"]] = relationship(
        back_populates="essay_topic", lazy="raise_on_sql"
    )


class EssayType(Base):
    name: Mapped[str] = mapped_column(String(255), unique=True)

    feedback_categories: Mapped[list["FeedbackCategory"]] = relationship(
        back_populates="essay_type"
    )

    essays: Mapped[list["Essay"]] = relationship(
        back_populates="essay_type", lazy="raise_on_sql"
    )


class Essay(Base, HasCurrencyTransactions):
    __table_args__ = (UniqueConstraint("author_id", "essay_topic_id"),)
    original_file: Mapped[str] = mapped_column(String(100))
    cleaned_text: Mapped[str] = mapped_column(Text)
    user_corrected_text: Mapped[str] = mapped_column(Text)

    essay_topic_id: Mapped[int] = mapped_column(ForeignKey("essay_topic.id"))
    essay_topic: Mapped["EssayTopic"] = relationship(back_populates="essays")

    author_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    author: Mapped["User"] = relationship(back_populates="essays")

    essay_type_id: Mapped[int] = mapped_column(ForeignKey("essay_type.id"))
    essay_type: Mapped["EssayType"] = relationship(back_populates="essays")

    extracted_texts: Mapped[list["ExtractedText"]] = relationship(
        back_populates="essay",
        lazy="raise_on_sql",
        cascade="save-update, merge, expunge, delete, delete-orphan",
        passive_deletes=True,
    )
    feedbacks: Mapped[list["Feedback"]] = relationship(
        back_populates="essay",
        lazy="raise_on_sql",
        cascade="save-update, merge, expunge, delete, delete-orphan",
        passive_deletes=True,
    )


class ExtractedText(Base):
    extraction_method: Mapped[str] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(Text)
    essay_id: Mapped[int] = mapped_column(ForeignKey("essay.id", ondelete="CASCADE"))
    essay: Mapped["Essay"] = relationship(back_populates="extracted_texts")


class Feedback(Base):
    text: Mapped[str] = mapped_column(Text)
    grade: Mapped[decimal.Decimal | None] = mapped_column(Numeric(6, 2))

    feedback_category_id: Mapped[int] = mapped_column(
        ForeignKey("feedback_category.id")
    )
    feedback_category: Mapped["FeedbackCategory"] = relationship(
        back_populates="feedbacks"
    )
    essay_id: Mapped[int] = mapped_column(ForeignKey("essay.id", ondelete="CASCADE"))
    essay: Mapped["Essay"] = relationship(back_populates="feedbacks")


class FeedbackCategory(Base):
    name: Mapped[str] = mapped_column(String(255))
    prompt_template: Mapped[str] = mapped_column(Text)
    temperature: Mapped[float] = mapped_column(Double(53))

    essay_type_id: Mapped[int] = mapped_column(ForeignKey("essay_type.id"))
    essay_type: Mapped["EssayType"] = relationship(back_populates="feedback_categories")
    feedbacks: Mapped[list["Feedback"]] = relationship(
        back_populates="feedback_category"
    )
