import logging
from enum import StrEnum
from typing import Annotated, Self

from api.schemas.users import SimpleUserOut
from ninja import Schema
from pydantic import (
    AwareDatetime,
    BeforeValidator,
    Field,
    computed_field,
    field_serializer,
    field_validator,
    model_validator,
)
from quiz.models import (
    QuestionDensity,
    QuestionSelectionMethod,
    QuestionType,
    QuizType,
    SelectionSource,
)

logger = logging.getLogger(__name__)


class ChoiceOut(Schema):
    id: int
    text: str
    image: str | None
    is_correct: bool

    @field_serializer("image")
    def serialize_image(self, image: str, _info) -> str | None:
        return None if image == "" else image


class BaseQuestionOut(Schema):
    id: int
    allow_resubmit: bool
    subject: str
    text: str
    answer_text: str
    answer_image: str | None
    image: str | None
    video_url: str
    source: str
    difficulty: str
    category: str
    subcategory: str

    @field_serializer("image")
    def serialize_image(self, image: str, _info) -> str | None:
        return None if image == "" else image

    @field_serializer("answer_image")
    def serialize_answer_image(self, answer_image: str, _info) -> str | None:
        return None if answer_image == "" else answer_image


class SimpleQuestionOut(BaseQuestionOut):
    choices: list[ChoiceOut]


class SimpleQuestionOutForUser(SimpleQuestionOut):
    answer_choice_id: (
        int | None
    )  # if there is no answer, then None. if its open_ended, then the None as well
    submitted_text: (
        str | None
    )  # if there is no answer, then None. no text, it will be empty string
    feedback: (
        str | None
    )  # if there is no answer, then None. no feedback, it will be empty string
    grade: float | None  # if there is no grade, it will be None


class DetailedChoiceOut(ChoiceOut):
    percentage_users_answered: float


class DetailedQuestionOut(BaseQuestionOut):
    detailed_choices: list[DetailedChoiceOut]


class Section(Schema):
    name: QuestionSelectionMethod
    num_questions: int


class UserInQuizRanking(Schema):
    id: int
    username: str
    rank: int
    school: str = Field(max_length=120, default="")
    school_id: int | None = Field(default=None)
    total_answers: int
    correct_answers: int


class QuizOut(Schema):
    id: int
    code: str
    created_at: AwareDatetime
    source_filter: str
    difficulty: str
    latest_answered_at: AwareDatetime | None
    quiz_type: QuizType  # deprecated
    query: str
    area: str
    total_questions_answered: int = 0
    parent_quiz_id: int | None = Field(alias="parent_session_id")
    questions_and_answers: list[SimpleQuestionOutForUser]
    title: str
    ranking: list[UserInQuizRanking]
    created_by: SimpleUserOut
    selection_source: SelectionSource
    topic: str
    sections: list[Section]
    selection_method: QuestionSelectionMethod

    @model_validator(mode="after")
    def set_total_questions_answered(self) -> Self:
        self.total_questions_answered = len(
            [q for q in self.questions_and_answers if q.answer_choice_id is not None]
        )
        return self


class QuizAnswerOut(Schema):
    choice_id: int | None
    submitted_text: str | None
    feedback: str | None
    grade: float | None
    user: SimpleUserOut


class QuizQuestionOut(SimpleQuestionOut):
    answers: list[QuizAnswerOut]


class OtherUserQuizOut(Schema):
    id: int
    code: str
    title: str
    created_by: SimpleUserOut
    created_at: AwareDatetime
    selection_source: SelectionSource
    selection_method: QuestionSelectionMethod
    topic: str
    area: str
    source_filter: str
    difficulty: str
    latest_answered_at: AwareDatetime


class SubmitAnswersQuizOut(QuizOut):
    score_increase: float
    area_expected_score_increases: dict[str, float]

    @field_validator("score_increase")
    @classmethod
    def validate_score_increase(cls, v: float):
        return round(v, 1)

    @field_validator("area_expected_score_increases")
    @classmethod
    def validate_area_expected_score_increases(cls, v: dict[str, float]):
        return {key: round(value, 1) for key, value in v.items()}


class Difficulty(StrEnum):
    ALL = ""
    EASY = "Fácil"
    MEDIUM = "Média"
    HARD = "Difícil"


class QuestionTypeIn(StrEnum):
    MULTIPLE_CHOICE = "multiple_choice"
    OPEN_ENDED = "open_ended"


class QuizIn(Schema):
    query: str = Field(max_length=1000)
    n_questions: int
    selection_method: QuestionSelectionMethod = QuestionSelectionMethod.QUERY_OFFICIAL
    selection_source: SelectionSource = SelectionSource.TOPIC
    area: str = Field(max_length=255, default="")
    source_filter: str = Field(max_length=255, default="")
    difficulty: Difficulty = Field(default=Difficulty.ALL)
    question_type: QuestionType = QuestionType.MULTIPLE_CHOICE
    parent_quiz_id: int | None = Field(default=None)


class AddQuestionsToQuizIn(Schema):
    selection_method: QuestionSelectionMethod
    n_questions: int
    question_density: QuestionDensity  # number of questions per block
    area: str = Field(default="", max_length=255)
    source_filter: str = Field(default="", max_length=255)
    difficulty: Difficulty = Field(default=Difficulty.ALL)
    question_type: QuestionType = QuestionType.MULTIPLE_CHOICE


class PersonalizedQuizIn(Schema):
    question_type: QuestionType = QuestionType.MULTIPLE_CHOICE
    parent_quiz_id: int | None = Field(default=None)


class WhatsAppQuizIn(Schema):
    query: str = Field(max_length=1000)
    n_questions: int
    area: str = Field(max_length=255, default="")
    source_filter: str = Field(max_length=255, default="")


class GenerateQuizIn(Schema):
    is_fast: bool = True
    question_blocks: list[str] = []  # list of text blocks
    topic: str = Field(max_length=255, default="")
    selection_method: QuestionSelectionMethod = QuestionSelectionMethod.USER_GENERATED
    question_type: QuestionTypeIn = QuestionTypeIn.MULTIPLE_CHOICE
    n_questions_per_block: int | None = (
        None  # número de questões para cada bloco, caso existam blocos
    )
    n_questions_for_topic: int | None = (
        None  # número de questões específicas para o tema, caso nenhum arquivo seja fornecido
    )
    subject: str = Field(max_length=255, default="")

    @computed_field
    @property
    def selection_source(self) -> SelectionSource:
        if self.question_blocks:
            return SelectionSource.FILES
        return SelectionSource.TOPIC


class MultipleChoiceAnswer(Schema):
    question_id: int
    answer_choice_id: int


def unwrap_single_item_list(
    v: MultipleChoiceAnswer | list[MultipleChoiceAnswer],
) -> MultipleChoiceAnswer:
    if isinstance(v, list):
        if len(v) != 1:
            raise ValueError("only one answer must be provided")
        return v[0]
    return v


OneAnswerOrAnswers = Annotated[
    MultipleChoiceAnswer,
    BeforeValidator(unwrap_single_item_list),
]


class SubmitMultipleChoiceAnswerIn(Schema):
    answers: OneAnswerOrAnswers


class NewSubmitMultipleChoiceAnswerIn(Schema):
    question_id: int
    answer_choice_id: int


class SubmitOpenEndedAnswerIn(Schema):
    question_id: int
    submitted_text: str = Field(max_length=5000, min_length=1)
