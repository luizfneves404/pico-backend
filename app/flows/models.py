import logging
import os
import string
import tempfile
import uuid
from contextlib import contextmanager
from enum import StrEnum
from typing import TYPE_CHECKING, Iterator, Protocol

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.base import (
    ASYNC_PARENT_FOREIGN_KEY_OPTIONS,
    Base,
    ContentBlock,
    ContentBlockListType,
)
from app.files.models import File

if TYPE_CHECKING:
    from app.users.models import User


NUM_QUESTION_EMBEDDING_DIMENSIONS = 1024

FLOW_ELEMENT_POLYMORPHIC_IDENTITY = "flow_element"
FLOW_QUESTION_POLYMORPHIC_IDENTITY = "question"

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

STARTING_DUEL_SCORE = 500

logger = logging.getLogger(__name__)


class FlowTranscriptionBlock(Base):
    flow_id: Mapped[int] = mapped_column(ForeignKey("flow.id", ondelete="CASCADE"))
    flow: Mapped["Flow"] = relationship(
        back_populates="transcription_blocks", lazy="raise_on_sql"
    )

    block_text: Mapped[str] = mapped_column(Text, default="")
    block_number: Mapped[int] = mapped_column()

    __table_args__ = (UniqueConstraint("flow_id", "block_number"),)


class FlowQuestionAnswerType(StrEnum):
    ALL = "all"
    MULTIPLE_CHOICE = "multiple_choice"
    OPEN_ENDED = "open_ended"


class QuestionAnswerType(StrEnum):
    MULTIPLE_CHOICE = "multiple_choice"
    OPEN_ENDED = "open_ended"


class FlowInputType(StrEnum):
    TOPIC = "topic"
    FILES = "files"
    USER_DATA = "user_data"


class FlowDifficulty(StrEnum):
    ALL = "Todos"
    EASY = "Fácil"
    MEDIUM = "Médio"
    HARD = "Difícil"


class Flow(Base):
    code: Mapped[uuid.UUID] = mapped_column(server_default=func.gen_random_uuid())
    title: Mapped[str] = mapped_column(Text)
    cover_image_id: Mapped[int | None] = mapped_column(ForeignKey("file.id"))
    cover_image: Mapped["File | None"] = relationship(lazy="raise_on_sql")
    created_by_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    created_by: Mapped["User"] = relationship(lazy="raise_on_sql")

    query: Mapped[str] = mapped_column(Text)
    area: Mapped[str] = mapped_column(Text)
    source_filter: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[FlowDifficulty] = mapped_column()
    question_answer_type: Mapped[QuestionAnswerType] = mapped_column()

    flow_input_type: Mapped[FlowInputType] = mapped_column()
    input_topic: Mapped[str] = mapped_column(Text, default="")

    transcription_blocks: Mapped[list["FlowTranscriptionBlock"]] = relationship(
        back_populates="flow",
        order_by="FlowTranscriptionBlock.block_number",
        cascade=ASYNC_PARENT_FOREIGN_KEY_OPTIONS,
        passive_deletes=True,
    )

    elements: Mapped[list["FlowElement"]] = relationship(
        back_populates="flow",
        order_by="FlowElement.order",
        cascade=ASYNC_PARENT_FOREIGN_KEY_OPTIONS,
        passive_deletes=True,
    )


class FlowElement(Base):
    flow_id: Mapped[int] = mapped_column(
        ForeignKey("flow.id", ondelete="CASCADE"),
    )
    flow: Mapped[Flow] = relationship(back_populates="elements")

    order: Mapped[int] = mapped_column()
    element_type: Mapped[str] = mapped_column(Text)

    question_id: Mapped[int | None] = mapped_column(
        ForeignKey("question.id", ondelete="CASCADE")
    )

    __table_args__ = (
        UniqueConstraint("flow_id", "order"),
        UniqueConstraint("flow_id", "question_id"),
        CheckConstraint(
            "(element_type = 'question' AND question_id IS NOT NULL)",
            name="ck_flowelement_exactly_one_payload",
        ),
    )

    __mapper_args__ = {
        "polymorphic_on": element_type,
        "polymorphic_identity": FLOW_ELEMENT_POLYMORPHIC_IDENTITY,
    }


class QuestionSourceType(StrEnum):
    OFFICIAL = "official"
    AI_GENERATED = "ai_generated"


class QuestionDifficulty(StrEnum):
    EASY = "Fácil"
    MEDIUM = "Médio"
    HARD = "Difícil"


class Question(Base):
    content_blocks: Mapped[list[ContentBlock]] = mapped_column(
        ContentBlockListType, default=[]
    )

    is_active: Mapped[bool] = mapped_column(default=True)

    subject: Mapped[str] = mapped_column(String(255), default="")
    category: Mapped[str] = mapped_column(String(100), default="")
    subcategory: Mapped[str] = mapped_column(String(100), default="")

    caderno: Mapped[str] = mapped_column(String(255), default="")
    caderno_number: Mapped[int | None] = mapped_column()
    difficulty: Mapped[QuestionDifficulty] = mapped_column()
    parameter_a: Mapped[float | None] = mapped_column()
    parameter_b: Mapped[float | None] = mapped_column()
    parameter_c: Mapped[float | None] = mapped_column()

    answer_text: Mapped[str] = mapped_column(Text, default="")
    answer_image_id: Mapped[int | None] = mapped_column(ForeignKey("file.id"))
    answer_image: Mapped["File | None"] = relationship(
        lazy="raise_on_sql", foreign_keys=[answer_image_id]
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(NUM_QUESTION_EMBEDDING_DIMENSIONS)
    )

    source_type: Mapped[QuestionSourceType] = mapped_column()
    official_source: Mapped[str] = mapped_column(
        default=""
    )  # add constraint according to source type
    source_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id")
    )  # add constraint according to source type
    source_user: Mapped["User | None"] = relationship(lazy="raise_on_sql")

    answer_type: Mapped[QuestionAnswerType] = mapped_column()

    flows: Mapped[list["Flow"]] = relationship(
        lazy="raise_on_sql",
        secondary="flow_element",
        viewonly=True,
    )

    flow_questions: Mapped[list["FlowQuestion"]] = relationship(
        back_populates="question",
        lazy="raise_on_sql",
        cascade=ASYNC_PARENT_FOREIGN_KEY_OPTIONS,
        passive_deletes=True,
    )

    choices: Mapped[list["Choice"]] = relationship(
        back_populates="question",
        order_by="Choice.order",
        lazy="raise_on_sql",
        cascade=ASYNC_PARENT_FOREIGN_KEY_OPTIONS,
        passive_deletes=True,
    )

    __table_args__ = (
        Index(
            "question_embedding_index",
            embedding,
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 200},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
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


class FlowQuestion(FlowElement):
    __mapper_args__ = {"polymorphic_identity": FLOW_QUESTION_POLYMORPHIC_IDENTITY}

    question: Mapped["Question"] = relationship(lazy="raise_on_sql")

    users_answered: Mapped[list["User"]] = relationship(
        secondary="flow_question_user", viewonly=True, lazy="raise_on_sql"
    )

    flow_question_users: Mapped[list["FlowQuestionUser"]] = relationship(
        back_populates="flow_question",
        lazy="raise_on_sql",
        cascade=ASYNC_PARENT_FOREIGN_KEY_OPTIONS,
        passive_deletes=True,
    )


class Choice(Base):
    image_id: Mapped[int | None] = mapped_column(ForeignKey("file.id"))
    image: Mapped["File | None"] = relationship(lazy="raise_on_sql")
    text: Mapped[str] = mapped_column(Text, default="")
    is_correct: Mapped[bool] = mapped_column(default=False)
    order: Mapped[int] = mapped_column(
        CheckConstraint("order >= 0", name="choice_order_check"),
    )

    question_id: Mapped[int] = mapped_column(
        ForeignKey("question.id", ondelete="CASCADE")
    )
    question: Mapped["Question"] = relationship(
        back_populates="choices", lazy="raise_on_sql"
    )

    __table_args__ = (UniqueConstraint("question_id", "order"),)

    def __str__(self) -> str:
        return self.text


class FlowQuestionUser(Base):
    flow_element_id: Mapped[int] = mapped_column(
        ForeignKey("flow_element.id", ondelete="CASCADE")
    )
    flow_question: Mapped[FlowQuestion] = relationship(
        back_populates="flow_question_users", lazy="raise_on_sql"
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    user: Mapped["User"] = relationship(lazy="raise_on_sql")

    choice_id: Mapped[int | None] = mapped_column(ForeignKey("choice.id"))
    choice: Mapped["Choice | None"] = relationship(lazy="raise_on_sql")

    submitted_text: Mapped[str] = mapped_column(Text, default="")

    feedback: Mapped[str] = mapped_column(Text, default="")
    grade: Mapped[float | None]

    __table_args__ = (
        UniqueConstraint("flow_element_id", "user_id"),
        CheckConstraint(
            """
            (choice_id IS NOT NULL AND submitted_text = '') OR
            (choice_id IS NULL AND submitted_text != '')
            """,
            name="check_flow_question_user_answer_valid_states",
        ),
    )


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
