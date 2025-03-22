import decimal
from typing import TYPE_CHECKING

from base import Base
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

    essays: Mapped[list["Essay"]] = relationship(back_populates="essay_topic")


class EssayType(Base):
    name: Mapped[str] = mapped_column(String(255), unique=True)

    feedback_categories: Mapped[list["FeedbackCategory"]] = relationship(
        back_populates="essay_type"
    )

    essays: Mapped[list["Essay"]] = relationship(back_populates="essay_type")


class Essay(Base):
    __table_args__ = (UniqueConstraint("author_id", "essay_topic_id"),)
    original_file: Mapped[str] = mapped_column(String(100))
    cleaned_text: Mapped[str] = mapped_column(Text)
    user_corrected_text: Mapped[str] = mapped_column(Text)

    essay_topic_id: Mapped[int] = mapped_column(ForeignKey("essay_topic.id"))
    essay_topic: Mapped["EssayTopic"] = relationship(back_populates="essays_essay")

    author_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    author: Mapped["User"] = relationship("User", back_populates="essays_essay")

    essay_type_id: Mapped[int] = mapped_column(ForeignKey("essay_type.id"))
    essay_type: Mapped["EssayType"] = relationship(back_populates="essays_essay")

    extracted_texts: Mapped[list["ExtractedText"]] = relationship(
        back_populates="essay"
    )
    feedbacks: Mapped[list["Feedback"]] = relationship(back_populates="essay")


class ExtractedText(Base):
    extraction_method: Mapped[str] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(Text)
    essay_id: Mapped[int] = mapped_column(ForeignKey("essay.id"))

    essay: Mapped["Essay"] = relationship("Essay", back_populates="extracted_texts")


class Feedback(Base):
    text: Mapped[str] = mapped_column(Text)
    feedback_category_id: Mapped[int] = mapped_column(
        ForeignKey("feedback_category.id")
    )
    essay_id: Mapped[int] = mapped_column(ForeignKey("essay.id"))
    grade: Mapped[decimal.Decimal | None] = mapped_column(Numeric(6, 2))

    essay: Mapped["Essay"] = relationship(back_populates="feedbacks")
    feedback_category: Mapped["FeedbackCategory"] = relationship(
        back_populates="feedbacks"
    )


class FeedbackCategory(Base):
    name: Mapped[str] = mapped_column(String(255))
    prompt_template: Mapped[str] = mapped_column(Text)
    temperature: Mapped[float] = mapped_column(Double(53))
    essay_type_id: Mapped[int] = mapped_column(ForeignKey("essay_type.id"))

    essay_type: Mapped["EssayType"] = relationship(back_populates="feedback_categories")
    feedbacks: Mapped[list["Feedback"]] = relationship(
        back_populates="feedback_category"
    )
