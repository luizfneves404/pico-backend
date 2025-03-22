import logging
import os
import string
import tempfile
from contextlib import contextmanager
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Iterator, Protocol

from base import Base, auto_now_insert_timestamp
from files.models import File
from shared.code_generation import HasCode
from sqlalchemy import (
    CheckConstraint,
    Computed,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from tournaments.models import Tournament
    from users.models import User

logger = logging.getLogger(__name__)

ENEM_AREAS = {
    "Ciências Humanas": [
        "Filosofia",
        "Geografia",
        "História",
        "Sociologia",
    ],
    "Ciências da Natureza": [
        "Biologia",
        "Física",
        "Química",
    ],
    "Linguagens": [
        "Inglês",
        "Português",
        "Espanhol",
    ],
    "Matemática": ["Matemática"],
}

SUBJECT_TO_AREA = {
    subject: area for area, subjects in ENEM_AREAS.items() for subject in subjects
}

CUSTOM_SOURCE = "Custom"


class QuestionType(StrEnum):
    MULTIPLE_CHOICE = "multiple_choice"
    OPEN_ENDED = "open_ended"
    ALL = "all"
    NOT_APPLICABLE = ""


class QuizType(StrEnum):
    QUERY_BASED = "query"
    PERSONALIZED = "personalized"
    CUSTOM = "custom"
    NOT_APPLICABLE = ""


class QuestionSelectionMethod(StrEnum):
    RANDOM_OFFICIAL = "random_official"
    QUERY_OFFICIAL = "query_official"
    USER_GENERATED = "user_generated"
    NOT_APPLICABLE = ""


class DuelTurnPhase(StrEnum):
    ATTACK = "attack"
    DEFENSE = "defense"


class DuelStatus(StrEnum):
    NOT_APPLICABLE = ""
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class UserInfo(Base):
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    user: Mapped["User"] = relationship("User", back_populates="user_info")
    math_score: Mapped[float | None] = mapped_column()
    language_score: Mapped[float | None] = mapped_column()
    humanities_score: Mapped[float | None] = mapped_column()
    science_score: Mapped[float | None] = mapped_column()
    average_score: Mapped[float] = mapped_column(
        Computed("(math_score + language_score + humanities_score + science_score) / 4")
    )
    dynamic_score: Mapped[float] = mapped_column()
    duel_score: Mapped[float] = mapped_column()


class Session(Base, HasCode):
    __mapper_args__ = {
        "polymorphic_on": "session_type",
        "polymorphic_identity": "session",
    }

    session_type: Mapped[str] = mapped_column(String(20))
    query: Mapped[str] = mapped_column(String(255), default="")
    area: Mapped[str] = mapped_column(String(255), default="")
    source_filter: Mapped[str] = mapped_column(String(255), default="")
    difficulty: Mapped[str] = mapped_column(String(50), default="")

    file_id: Mapped[int | None] = mapped_column(ForeignKey("file.id"))
    file: Mapped["File | None"] = relationship()
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    created_by: Mapped["User | None"] = relationship(
        back_populates="sessions_created",
        foreign_keys=[created_by_id],
        lazy="raise_on_sql",
    )
    parent_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("session.id"),
    )
    parent_session: Mapped["Session | None"] = relationship(
        "Session", remote_side=[Base.id], lazy="raise_on_sql"
    )

    questions: Mapped[list["Question"]] = relationship(
        "Question",
        secondary="session_question",
        back_populates="sessions",
        viewonly=True,
        lazy="raise_on_sql",
    )

    def __str__(self) -> str:
        return f"{self.session_type.capitalize()} object ({self.id})"


class Quiz(Session):
    __mapper_args__ = {"polymorphic_identity": "quiz"}

    question_type: Mapped[QuestionType] = mapped_column(
        default=QuestionType.NOT_APPLICABLE
    )
    quiz_type: Mapped[QuizType] = mapped_column(default=QuizType.NOT_APPLICABLE)

    @property
    def title(self) -> str:
        area = self.area if self.area else "<area indefinida>"
        query = self.query if self.query else "<Assunto indefinido>"
        return f"{self.session_type.capitalize()} - Area: {area}, Assunto: {query}"

    @property
    def content_str(self) -> str:
        return f"{self.session_type.capitalize()}: {self.query}##{self.area}"


class JoinableSession(Session):
    __mapper_args__ = {"polymorphic_abstract": True}

    is_fast: Mapped[bool] = mapped_column(default=True)
    selection_method: Mapped[QuestionSelectionMethod] = mapped_column(
        default=QuestionSelectionMethod.NOT_APPLICABLE
    )
    participants: Mapped[list["User"]] = relationship(
        "User",
        secondary="session_participation",
        back_populates="sessions_participated",
        viewonly=True,
    )


class Duel(JoinableSession):
    __mapper_args__ = {"polymorphic_identity": "duel"}

    n_questions_per_round: Mapped[int | None] = mapped_column()
    duel_status: Mapped[DuelStatus] = mapped_column(default=DuelStatus.NOT_APPLICABLE)

    current_turn_id: Mapped[int | None] = mapped_column(
        ForeignKey("turn.id", use_alter=True)
    )
    current_turn: Mapped["Turn | None"] = relationship(
        foreign_keys=[current_turn_id], lazy="raise_on_sql"
    )

    winner_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    winner: Mapped["User | None"] = relationship(
        foreign_keys=[winner_id], lazy="raise_on_sql"
    )

    tournament_id: Mapped[int | None] = mapped_column(ForeignKey("tournament.id"))
    tournament: Mapped["Tournament | None"] = relationship(
        foreign_keys=[tournament_id], lazy="raise_on_sql", back_populates="duels"
    )

    @property
    def current_turn_user(self):
        return self.current_turn.user if self.current_turn else None

    @property
    def current_turn_round(self):
        return self.current_turn.round if self.current_turn else None

    @property
    def current_turn_start_time(self):
        return self.current_turn.start_time if self.current_turn else None

    @property
    def current_turn_phase(self):
        return self.current_turn.phase if self.current_turn else None


class Challenge(JoinableSession):
    __mapper_args__ = {"polymorphic_identity": "challenge"}

    start_time: Mapped[datetime | None] = mapped_column()
    end_time: Mapped[datetime | None] = mapped_column()


class Round(Base):
    duel_id: Mapped[int] = mapped_column(ForeignKey("session.id"))
    query: Mapped[str] = mapped_column(Text, default="")

    duel: Mapped["Duel"] = relationship(foreign_keys=[duel_id])
    users: Mapped[list["User"]] = relationship(
        "User", secondary="turn", viewonly=True, lazy="raise_on_sql"
    )
    turns: Mapped[list["Turn"]] = relationship("Turn", back_populates="round")


class Turn(Base):
    round_id: Mapped[int] = mapped_column(ForeignKey("round.id"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    phase: Mapped[DuelTurnPhase] = mapped_column()
    start_time: Mapped[datetime | None] = mapped_column()

    round: Mapped["Round"] = relationship("Round", back_populates="turns")
    user: Mapped["User | None"] = relationship("User")


class SessionParticipation(Base):
    session_id: Mapped[int] = mapped_column(ForeignKey("session.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    confirmed: Mapped[bool] = mapped_column(default=False)
    duel_score_change: Mapped[float | None]

    session: Mapped["Session"] = relationship("Session")
    user: Mapped["User | None"] = relationship("User")


class Question(Base):
    is_active: Mapped[bool] = mapped_column(default=True)
    allow_resubmit: Mapped[bool] = mapped_column(default=False)
    subject: Mapped[str] = mapped_column(String(255), default="")
    extra_embedding_text: Mapped[str] = mapped_column(Text, default="")
    text: Mapped[str] = mapped_column(Text, default="")
    image_id: Mapped[int | None] = mapped_column(ForeignKey("file.id"))
    image: Mapped["File | None"] = relationship(foreign_keys=[image_id])
    video_url: Mapped[str] = mapped_column(String(255), default="")
    answer_text: Mapped[str] = mapped_column(Text, default="")
    answer_image_id: Mapped[int | None] = mapped_column(ForeignKey("file.id"))
    answer_image: Mapped["File | None"] = relationship(foreign_keys=[answer_image_id])
    """ embedding: Mapped[list[float] | None] = (
        mapped_column()
    )  # Vector field would need custom type """
    source: Mapped[str] = mapped_column(String(100), default="")
    caderno: Mapped[str] = mapped_column(String(255), default="")
    caderno_number: Mapped[int | None] = mapped_column()
    difficulty: Mapped[str] = mapped_column(String(10), default="")
    parameter_a: Mapped[float | None] = mapped_column()
    parameter_b: Mapped[float | None] = mapped_column()
    parameter_c: Mapped[float | None] = mapped_column()
    category: Mapped[str] = mapped_column(String(100), default="")
    subcategory: Mapped[str] = mapped_column(String(100), default="")
    is_fast: Mapped[bool] = mapped_column(default=False)

    sessions: Mapped[list["Session"]] = relationship(
        "Session",
        secondary="session_question",
        back_populates="questions",
        viewonly=True,
    )
    choices: Mapped[list["Choice"]] = relationship(
        "Choice", back_populates="question", order_by="Choice.order"
    )

    @property
    def area(self) -> str | None:
        return SUBJECT_TO_AREA.get(self.subject, None)

    @property
    def text_with_source_and_subject(self) -> str:
        parts: list[str] = []

        if self.source:
            parts.append(self.source)

        if self.subject:
            parts.append(self.subject)

        prefix = ""
        if parts:
            prefix = f"({' - '.join(parts)}) "

        text = self.text if self.text else "No text available"

        return f"{prefix}{text}"

    @property
    def text_with_source_and_subject_with_extra(self) -> str:
        parts: list[str] = []

        if self.source:
            parts.append(self.source)

        if self.subject:
            parts.append(self.subject)

        prefix = ""
        if parts:
            prefix = f"({' - '.join(parts)})"

        if self.extra_embedding_text:
            prefix = f"{prefix} {self.extra_embedding_text}"

        text = self.text if self.text else "No text available"

        return f"{prefix}\n\n{text}"

    @property
    def choices_text(self) -> str:
        choices_text: list[str] = []
        for j, choice in enumerate(self.choices):
            if choice.text:
                choices_text.append(f"{string.ascii_uppercase[j]}) {choice.text}")
            else:
                return ""
        return "\n".join(choices_text)

    @property
    def full_text(self) -> str:
        return f"{self.text_with_source_and_subject}\n\n{self.choices_text}"

    @property
    def full_text_with_extra(self) -> str:
        return f"{self.text_with_source_and_subject_with_extra}\n\n{self.choices_text}"

    def __str__(self) -> str:
        return self.text if self.text else f"id: {self.id}"


class Choice(Base):
    question_id: Mapped[int] = mapped_column(ForeignKey("question.id"))
    image_id: Mapped[int | None] = mapped_column(ForeignKey("file.id"))
    image: Mapped["File | None"] = relationship()
    text: Mapped[str] = mapped_column(Text, default="")
    is_correct: Mapped[bool] = mapped_column(default=False)
    order: Mapped[int] = mapped_column(
        CheckConstraint("order >= 0", name="choice_order_check"), index=True
    )

    question: Mapped["Question"] = relationship("Question", back_populates="choices")

    def __str__(self) -> str:
        return self.text


class SessionQuestion(Base):
    __table_args__ = (UniqueConstraint("session_id", "question_id"),)
    session_id: Mapped[int] = mapped_column(ForeignKey("session.id"))
    question_id: Mapped[int] = mapped_column(ForeignKey("question.id"))
    order: Mapped[int] = mapped_column(
        CheckConstraint("order >= 0", name="session_question_order_check"),
        index=True,
    )

    session: Mapped["Session"] = relationship("Session")
    question: Mapped["Question"] = relationship("Question")
    users_answered: Mapped[list["User"]] = relationship(
        secondary="session_question_user", viewonly=True, lazy="raise_on_sql"
    )


class SessionQuestionUser(Base):
    session_question_id: Mapped[int] = mapped_column(ForeignKey("session_question.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    choice_id: Mapped[int | None] = mapped_column(ForeignKey("choice.id"))
    submitted_text: Mapped[str] = mapped_column(Text, default="")
    timestamp: Mapped[auto_now_insert_timestamp]
    feedback: Mapped[str] = mapped_column(Text, default="")
    grade: Mapped[float | None]
    timed_out: Mapped[bool] = mapped_column(default=False)

    session_question: Mapped["SessionQuestion"] = relationship("SessionQuestion")
    user: Mapped["User | None"] = relationship("User")
    choice: Mapped["Choice | None"] = relationship("Choice")

    @property
    def is_correct(self) -> bool:
        return self.choice.is_correct if self.choice else False

    @property
    def session(self):
        return self.session_question.session

    @property
    def question(self):
        return self.session_question.question

    @property
    def question_text(self) -> str:
        return self.question.text

    @property
    def question_subject(self) -> str:
        return self.question.subject

    @property
    def question_category(self) -> str:
        return self.question.category

    @property
    def question_subcategory(self) -> str:
        return self.question.subcategory


class FieldFile(Protocol):
    name: str
    size: int

    def chunks(self) -> Iterator[bytes]: ...


@contextmanager
def open_field_file_as_temp(field_file: FieldFile) -> Iterator[str]:
    file_path = ""
    try:
        _, file_extension = os.path.splitext(field_file.name)

        temp_file = tempfile.NamedTemporaryFile(
            mode="r+b", delete=False, suffix=file_extension
        )

        logger.debug(f"Writing {field_file.size} bytes to temp file...")

        for chunk in field_file.chunks():
            temp_file.write(chunk)

        logger.debug(f"Finished writing {field_file.size} bytes to temp file")

        temp_file.close()

        file_path = temp_file.name

        yield file_path

    finally:
        try:
            os.remove(file_path)
            logger.debug("Cleaned up temporary file for field_file")
        except UnboundLocalError:
            logger.debug(
                "UnboundLocalError: file_path is not defined, so no cleanup needed"
            )
