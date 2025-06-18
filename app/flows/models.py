import logging
import string
import uuid
from enum import StrEnum
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    distinct,
    func,
    inspect,
    select,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.hybrid import hybrid_method, hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.base import (
    ASYNC_PARENT_FOREIGN_KEY_OPTIONS,
    Base,
)
from app.countries.models import Country
from app.files.models import File
from app.flows.db_types import ContentBlock, ContentBlockListType

if TYPE_CHECKING:
    from app.education.models import Course, EducationLevel
    from app.users.models import User


NUM_QUESTION_EMBEDDING_DIMENSIONS = 1024

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


class FlowTranscriptionBlock(Base, kw_only=True):
    flow_id: Mapped[int] = mapped_column(
        ForeignKey("flow.id", ondelete="CASCADE"), default=None
    )
    flow: Mapped["Flow"] = relationship(
        back_populates="transcription_blocks", lazy="raise_on_sql", default=None
    )

    block_text: Mapped[str] = mapped_column(Text, default="")
    block_number: Mapped[int] = mapped_column()
    title: Mapped[str] = mapped_column(Text, default="")

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


class FlowSourceType(StrEnum):
    OFFICIAL = "official"
    AI_GENERATED = "ai_generated"
    FULL = "full"


class Flow(Base, kw_only=True):
    title: Mapped[str] = mapped_column(Text)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("user.id"), default=None)
    created_by: Mapped["User"] = relationship(lazy="raise_on_sql", default=None)
    difficulty: Mapped[FlowDifficulty] = mapped_column()
    question_answer_type: Mapped[QuestionAnswerType] = mapped_column()
    source_type: Mapped[FlowSourceType] = mapped_column()
    flow_input_type: Mapped[FlowInputType] = (
        mapped_column()
    )  # determines input_topic vs transcription_blocks

    code: Mapped[uuid.UUID] = mapped_column(
        server_default=func.gen_random_uuid(), init=False
    )
    cover_image_id: Mapped[int | None] = mapped_column(
        ForeignKey("file.id"), default=None
    )
    cover_image: Mapped["File | None"] = relationship(lazy="raise_on_sql", default=None)
    action_link: Mapped[str] = mapped_column(Text, default="")
    action_text: Mapped[str] = mapped_column(Text, default="")
    max_num_questions: Mapped[int] = mapped_column(
        default=0
    )  # because we need to tell the frontend the total, in case we still havent finished doing all of them
    input_topic: Mapped[str] = mapped_column(Text, default="")

    major_tags: Mapped[list[str]] = mapped_column(
        postgresql.ARRAY(Text), default_factory=list
    )  # should be derived from questions tags + questions official source
    minor_tags: Mapped[list[str]] = mapped_column(
        postgresql.ARRAY(Text), default_factory=list
    )
    has_quantitative_questions: Mapped[bool] = mapped_column(default=False)

    transcription_blocks: Mapped[list["FlowTranscriptionBlock"]] = relationship(
        back_populates="flow",
        order_by="FlowTranscriptionBlock.block_number",
        cascade=ASYNC_PARENT_FOREIGN_KEY_OPTIONS,
        passive_deletes=True,
        lazy="raise_on_sql",
        default_factory=list,
    )

    elements: Mapped[list["FlowElement"]] = relationship(
        back_populates="flow",
        order_by="FlowElement.order",
        cascade=ASYNC_PARENT_FOREIGN_KEY_OPTIONS,
        passive_deletes=True,
        lazy="raise_on_sql",
        default_factory=list,
    )

    @hybrid_property
    def num_total_questions(self) -> int:
        """Count total questions for this flow."""
        return len(
            [element for element in self.elements if isinstance(element, FlowQuestion)]
        )

    @num_total_questions.inplace.expression
    @classmethod
    def _num_total_questions_expression(cls):
        """SQL expression for counting total questions"""
        return (
            select(func.count())
            .select_from(FlowElement)
            .where(
                FlowElement.flow_id == cls.id,
                FlowElement.element_type == "flow_question",
            )
        ).scalar_subquery()

    @hybrid_property
    def num_total_elements(self) -> int:
        """Count total elements for this flow."""
        return len(self.elements)

    @num_total_elements.inplace.expression
    @classmethod
    def _num_total_elements_expression(cls):
        """SQL expression for counting total elements"""
        return (
            select(func.count())
            .select_from(FlowElement)
            .where(FlowElement.flow_id == cls.id)
        ).scalar_subquery()

    @hybrid_property
    def num_total_answers(self) -> int:
        """Count total questions for this flow."""
        return sum(
            element.num_total_answers
            for element in self.elements
            if isinstance(element, FlowQuestion)
        )

    @num_total_answers.inplace.expression
    @classmethod
    def _num_total_answers_expression(cls):
        """SQL expression for counting total answers"""
        return (
            select(func.count())
            .select_from(FlowQuestionUser)
            .where(
                FlowQuestionUser.flow_element_id.in_(
                    select(FlowElement.id)
                    .select_from(FlowElement)
                    .where(FlowElement.flow_id == cls.id)
                ),
                (FlowQuestionUser.choice_id.is_not(None))
                | (FlowQuestionUser.submitted_text != ""),
            )
        ).scalar_subquery()

    @hybrid_method
    def num_user_total_answers(self, user_id: int) -> int:
        """Count total answers for this flow by a specific user."""
        return len(
            [
                element
                for element in self.elements
                if isinstance(element, FlowQuestion)
                and any(fqu.user_id == user_id for fqu in element.flow_question_users)
            ]
        )

    @num_user_total_answers.inplace.expression
    @classmethod
    def _num_user_total_answers_expression(cls, user_id: int):
        """SQL expression for counting total answers for a user"""
        return (
            select(func.count())
            .select_from(FlowQuestionUser)
            .where(
                FlowQuestionUser.flow_element_id.in_(
                    select(FlowElement.id)
                    .select_from(FlowElement)
                    .where(FlowElement.flow_id == cls.id)
                ),
                FlowQuestionUser.user_id == user_id,
                (FlowQuestionUser.choice_id.is_not(None))
                | (FlowQuestionUser.submitted_text != ""),
            )
        ).scalar_subquery()

    @hybrid_method
    def num_user_correct_answers(self, user_id: int) -> int:
        """Count correct answers for this flow by a specific user."""
        return len(
            [
                element
                for element in self.elements
                if isinstance(element, FlowQuestion)
                and any(
                    fqu.user_id == user_id
                    and fqu.choice is not None
                    and fqu.choice.is_correct
                    for fqu in element.flow_question_users
                )
            ]
        )

    @num_user_correct_answers.inplace.expression
    @classmethod
    def _num_user_correct_answers_expression(cls, user_id: int):
        """SQL expression for counting correct answers for a user"""
        return (
            select(func.count())
            .select_from(FlowQuestionUser)
            .where(
                FlowQuestionUser.flow_element_id.in_(
                    select(FlowElement.id)
                    .select_from(FlowElement)
                    .where(FlowElement.flow_id == cls.id)
                ),
                FlowQuestionUser.user_id == user_id,
                FlowQuestionUser.choice_id.is_not(None),
                FlowQuestionUser.choice.is_correct,
            )
        ).scalar_subquery()

    @hybrid_property
    def num_users_answered(self) -> int:
        """Count total users who answered at least one question for this flow."""
        flow_question_users = [
            fqu
            for element in self.elements
            if isinstance(element, FlowQuestion)
            for fqu in element.flow_question_users
        ]
        return len(
            {
                fqu.user_id
                for fqu in flow_question_users
                if fqu.choice_id is not None or fqu.submitted_text != ""
            }
        )

    @num_users_answered.inplace.expression
    @classmethod
    def _num_users_answered_expression(cls):
        """SQL expression for counting total users who answered at least one question for this flow."""
        return (
            select(func.count(distinct(FlowQuestionUser.user_id)))
            .select_from(FlowQuestionUser)
            .where(
                FlowQuestionUser.flow_element_id.in_(
                    select(FlowElement.id)
                    .select_from(FlowElement)
                    .where(FlowElement.flow_id == cls.id)
                ),
                (FlowQuestionUser.choice_id.is_not(None))
                | (FlowQuestionUser.submitted_text != ""),
            )
        ).scalar_subquery()


class FlowElement(Base, kw_only=True):
    order: Mapped[int] = mapped_column(
        CheckConstraint("order >= 0", name="flow_element_order_check"),
    )
    element_type: Mapped[str] = mapped_column(Text)
    flow_id: Mapped[int] = mapped_column(
        ForeignKey("flow.id", ondelete="CASCADE"), default=None
    )
    flow: Mapped[Flow] = relationship(
        back_populates="elements", lazy="raise_on_sql", default=None
    )

    question_id: Mapped[int | None] = mapped_column(
        ForeignKey("question.id", ondelete="CASCADE"), default=None
    )

    __table_args__ = (
        UniqueConstraint("flow_id", "order"),
        UniqueConstraint("flow_id", "question_id"),
        CheckConstraint(
            "(element_type = 'flow_question' AND question_id IS NOT NULL)",
            name="ck_flowelement_exactly_one_payload",
        ),
    )

    __mapper_args__ = {
        "polymorphic_on": element_type,
        "polymorphic_identity": "flow_element",
    }


class QuestionSourceType(StrEnum):
    OFFICIAL = "official"
    AI_GENERATED = "ai_generated"


class QuestionDifficulty(StrEnum):
    EASY = "Fácil"
    MEDIUM = "Médio"
    HARD = "Difícil"


class Question(Base, kw_only=True):
    difficulty: Mapped[QuestionDifficulty] = mapped_column()
    source_type: Mapped[QuestionSourceType] = mapped_column()
    answer_type: Mapped[QuestionAnswerType] = mapped_column()
    content_blocks: Mapped[list[ContentBlock]] = mapped_column(
        ContentBlockListType,
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    is_quantitative: Mapped[bool] = mapped_column(default=False)

    major_tags: Mapped[list[str]] = mapped_column(
        postgresql.ARRAY(Text), insert_default=list
    )
    minor_tags: Mapped[list[str]] = mapped_column(
        postgresql.ARRAY(Text), insert_default=list
    )
    answer_content_blocks: Mapped[list[ContentBlock]] = mapped_column(
        ContentBlockListType, insert_default=list
    )

    parameter_a: Mapped[float | None] = mapped_column(default=None)
    parameter_b: Mapped[float | None] = mapped_column(default=None)
    parameter_c: Mapped[float | None] = mapped_column(default=None)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(NUM_QUESTION_EMBEDDING_DIMENSIONS), default=None
    )
    official_source_id: Mapped[int | None] = mapped_column(
        ForeignKey("official_question_source.id"), default=None
    )
    source_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id"), default=None
    )  # add constraint according to source type

    official_source: Mapped["OfficialQuestionSource | None"] = relationship(
        lazy="raise_on_sql", foreign_keys=[official_source_id], default=None
    )
    source_user: Mapped["User | None"] = relationship(lazy="raise_on_sql", default=None)

    flows: Mapped[list["Flow"]] = relationship(
        lazy="raise_on_sql",
        secondary="flow_element",
        viewonly=True,
        default_factory=list,
    )

    flow_questions: Mapped[list["FlowQuestion"]] = relationship(
        back_populates="question",
        lazy="raise_on_sql",
        cascade=ASYNC_PARENT_FOREIGN_KEY_OPTIONS,
        passive_deletes=True,
        default_factory=list,
    )

    choices: Mapped[list["Choice"]] = relationship(
        back_populates="question",
        order_by="Choice.order",
        lazy="raise_on_sql",
        cascade=ASYNC_PARENT_FOREIGN_KEY_OPTIONS,
        passive_deletes=True,
        default_factory=list,
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
    def choices_text(self) -> str:
        choices_text: list[str] = []
        for j, choice in enumerate(self.choices):
            if choice.text:
                choices_text.append(f"{string.ascii_uppercase[j]}) {choice.text}")
            else:
                return ""
        return "\n".join(choices_text)

    @property
    def correct_choice_id(self) -> int | None:
        return next(choice.id for choice in self.choices if choice.is_correct)

    def __str__(self) -> str:
        question_insp = inspect(self)
        if (
            "official_source" not in question_insp.unloaded
            and self.official_source_id
            and self.official_source
        ):
            official_source_insp = inspect(self.official_source)
            if "exam" not in official_source_insp.unloaded:
                return f"Question {self.id} - {self.official_source.exam.name} - {self.official_source.year}"
        return f"Question {self.id}"


class QuestionArea(Base, kw_only=True):
    name: Mapped[str] = mapped_column(Text)
    education_level_id: Mapped[int] = mapped_column(
        ForeignKey("education_level.id"), default=None
    )
    education_level: Mapped["EducationLevel"] = relationship(
        lazy="raise_on_sql", default=None
    )
    country_id: Mapped[int] = mapped_column(ForeignKey("country.id"), default=None)
    country: Mapped["Country"] = relationship(lazy="raise_on_sql", default=None)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("course.id"), default=None)
    course: Mapped["Course | None"] = relationship(lazy="raise_on_sql", default=None)
    tags: Mapped[list[str]] = mapped_column(
        postgresql.ARRAY(Text), default_factory=list
    )


class Exam(Base, kw_only=True):
    """
    Represents an exam (bancada in portuguese)
    """

    name: Mapped[str] = mapped_column(Text)

    country_id: Mapped[int] = mapped_column(ForeignKey("country.id"), default=None)
    country: Mapped["Country"] = relationship(lazy="raise_on_sql", default=None)

    education_level_id: Mapped[int] = mapped_column(
        ForeignKey("education_level.id"), default=None
    )
    education_level: Mapped["EducationLevel"] = relationship(
        lazy="raise_on_sql", default=None
    )

    course_id: Mapped[int | None] = mapped_column(ForeignKey("course.id"), default=None)
    course: Mapped["Course | None"] = relationship(lazy="raise_on_sql", default=None)

    def __str__(self) -> str:
        return self.name


class OfficialQuestionSource(Base, kw_only=True):
    year: Mapped[int] = mapped_column()

    exam_id: Mapped[int] = mapped_column(
        ForeignKey("exam.id", ondelete="CASCADE"), default=None
    )
    exam: Mapped["Exam"] = relationship(lazy="raise_on_sql", default=None)

    def __str__(self) -> str:
        insp = inspect(self)
        return (
            f"{self.exam.name} - {self.year}"
            if "exam" not in insp.unloaded
            else f"Exam {self.exam_id} - {self.year}"
        )


class FlowQuestion(FlowElement):
    __mapper_args__ = {"polymorphic_identity": "flow_question"}

    question: Mapped["Question"] = relationship(lazy="raise_on_sql", default=None)

    users_answered: Mapped[list["User"]] = relationship(
        secondary="flow_question_user",
        viewonly=True,
        lazy="raise_on_sql",
        init=False,
    )

    flow_question_users: Mapped[list["FlowQuestionUser"]] = relationship(
        back_populates="flow_question",
        lazy="raise_on_sql",
        cascade=ASYNC_PARENT_FOREIGN_KEY_OPTIONS,
        passive_deletes=True,
        default_factory=list,
    )

    answers: Mapped[list["FlowQuestionUser"]] = relationship(
        lazy="raise_on_sql",
        viewonly=True,
        primaryjoin="and_(FlowQuestionUser.flow_element_id == FlowQuestion.id, or_(FlowQuestionUser.choice_id != None, FlowQuestionUser.submitted_text != ''))",
        init=False,
    )

    multiple_choice_answers: Mapped[list["FlowQuestionUser"]] = relationship(
        lazy="raise_on_sql",
        viewonly=True,
        primaryjoin="and_(FlowQuestionUser.flow_element_id == FlowQuestion.id, FlowQuestionUser.choice_id != None)",
        init=False,
    )

    @hybrid_property
    def num_total_answers(self) -> int:
        """Count total answers for this flow question.

        This hybrid property provides:
        - Python-level computation when flow_question_users is already loaded
        - SQL-level computation when used in queries

        Examples:
            # Python-level (when relationship is loaded)
            flow_question = session.get(FlowQuestion, 1)
            count = flow_question.num_total_answers  # No extra DB query

            # SQL-level (in queries)
            results = session.query(FlowQuestion).filter(
                FlowQuestion.num_total_answers > 5
            ).all()
        """
        return len(
            [
                fqu
                for fqu in self.flow_question_users
                if fqu.choice_id is not None or fqu.submitted_text
            ]
        )

    @num_total_answers.inplace.expression
    @classmethod
    def _num_total_answers_expression(cls):
        """SQL expression for counting total answers"""

        return (
            select(func.count())
            .select_from(FlowQuestionUser)
            .where(
                FlowQuestionUser.flow_element_id == cls.id,
                (FlowQuestionUser.choice_id.is_not(None))
                | (FlowQuestionUser.submitted_text != ""),
            )
        ).scalar_subquery()

    @hybrid_property
    def num_users_answered(self) -> int:
        """Count total users who answered the question."""
        return len(
            {
                fqu.user_id
                for fqu in self.flow_question_users
                if fqu.choice_id is not None or fqu.submitted_text != ""
            }
        )

    @num_users_answered.inplace.expression
    @classmethod
    def _num_users_answered_expression(cls):
        """SQL expression for counting total users who answered the question."""
        return (
            select(func.count(distinct(FlowQuestionUser.user_id)))
            .select_from(FlowQuestionUser)
            .where(FlowQuestionUser.flow_element_id == cls.id)
        ).scalar_subquery()


class Choice(Base, kw_only=True):
    order: Mapped[int] = mapped_column(
        CheckConstraint("order >= 0", name="choice_order_check"),
    )
    is_correct: Mapped[bool] = mapped_column()
    question_id: Mapped[int] = mapped_column(
        ForeignKey("question.id", ondelete="CASCADE"), default=None
    )
    question: Mapped["Question"] = relationship(
        back_populates="choices", lazy="raise_on_sql", default=None
    )
    image_id: Mapped[int | None] = mapped_column(ForeignKey("file.id"), default=None)
    image: Mapped["File | None"] = relationship(lazy="raise_on_sql", default=None)
    text: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (UniqueConstraint("question_id", "order"),)

    def __str__(self) -> str:
        return self.text


class FlowQuestionUser(Base, kw_only=True):
    """This stores information about a user's relationship to a flow question.

    An answer exists when either:
    - choice_id IS NOT NULL (multiple choice answer)
    - submitted_text != '' (open-ended answer)
    """

    flow_element_id: Mapped[int] = mapped_column(
        ForeignKey("flow_element.id", ondelete="CASCADE"), default=None
    )
    flow_question: Mapped[FlowQuestion] = relationship(
        back_populates="flow_question_users", lazy="raise_on_sql", default=None
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), default=None
    )
    user: Mapped["User"] = relationship(lazy="raise_on_sql", default=None)

    grade: Mapped[float | None] = mapped_column(default=None)

    choice_id: Mapped[int | None] = mapped_column(ForeignKey("choice.id"), default=None)
    choice: Mapped["Choice | None"] = relationship(lazy="raise_on_sql", default=None)

    submitted_text: Mapped[str] = mapped_column(Text, default="")

    feedback: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (
        UniqueConstraint("flow_element_id", "user_id"),
        CheckConstraint(
            """
            (choice_id IS NOT NULL AND submitted_text = '') OR
            (choice_id IS NULL AND submitted_text != '') OR
            (choice_id IS NULL AND submitted_text = '')
            """,
            name="check_flow_question_user_answer_valid_states",
        ),
    )


class FlowUserFeed(Base, kw_only=True):
    """Tracks when a user has seen a flow in their feed to prevent duplicates"""

    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), default=None
    )
    user: Mapped["User"] = relationship(lazy="raise_on_sql", default=None)

    flow_id: Mapped[int] = mapped_column(
        ForeignKey("flow.id", ondelete="CASCADE"), default=None
    )
    flow: Mapped[Flow] = relationship(lazy="raise_on_sql", default=None)

    __table_args__ = (UniqueConstraint("user_id", "flow_id"),)


class CampaignType(StrEnum):
    EXTERNAL = "external"
    INSTITUTION = "institution"
    INTENDED_EDUCATION = "intended_education"
    REFERRALS = "referrals"
    FLOW = "flow"
    ADD_PHONE_NUMBER = "add_phone_number"


class Campaign(Base, kw_only=True):
    """
    Represents a campaign with optional images, external link, and type.

    Attributes:
        name: The name of the campaign.
        text: The main text content of the campaign.
        external_link: A URL for an external link associated with the campaign.
        external_link_text: The text to display for the external link.
        image1_id: The ID of the first image file, or None.
        image1: The first image file object, or None.
        image2_id: The ID of the second image file, or None.
        image2: The second image file object, or None.
        probability: The probability value associated with the campaign.
        campaign_type: The type of the campaign.
    """

    campaign_type: Mapped[CampaignType]
    name: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    external_link: Mapped[str] = mapped_column(Text)
    external_link_text: Mapped[str] = mapped_column(Text)

    probability: Mapped[float] = mapped_column()

    image1_id: Mapped[int | None] = mapped_column(ForeignKey("file.id"), default=None)
    image1: Mapped["File | None"] = relationship(
        lazy="raise_on_sql", foreign_keys=[image1_id], default=None
    )

    image2_id: Mapped[int | None] = mapped_column(ForeignKey("file.id"), default=None)
    image2: Mapped["File | None"] = relationship(
        lazy="raise_on_sql", foreign_keys=[image2_id], default=None
    )
