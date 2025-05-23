from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from app.base import ContentBlock
from app.flows.models import (
    FLOW_QUESTION_POLYMORPHIC_IDENTITY,
    FlowDifficulty,
    QuestionAnswerType,
    QuestionDifficulty,
    QuestionSourceType,
)


class SimpleUser(BaseModel):
    id: int
    username: str


class Answer(BaseModel):
    user: SimpleUser
    submitted_text: str
    choice_id: int | None


class Choice(BaseModel):
    id: int
    text: str
    image: str | None
    is_correct: bool


class FlowQuestionInFeed(BaseModel):
    id: int
    element_type: Literal[FLOW_QUESTION_POLYMORPHIC_IDENTITY]
    json_content: list[ContentBlock]
    relevant_answers: list[Answer]  # all answers
    num_total_answers: int
    choices: list[Choice]

    subject: str
    category: str
    subcategory: str
    difficulty: QuestionDifficulty

    source_type: QuestionSourceType
    official_source: str
    source_user: SimpleUser | None

    answer_type: QuestionAnswerType


class FlowInFeed(BaseModel):
    id: int
    code: str
    created_at: AwareDatetime
    title: str

    cover_image: str | None
    action_link: str  # not link of the flow
    action_text: str
    created_by: SimpleUser

    query: str
    area: str
    source_filter: str
    difficulty: FlowDifficulty

    elements: list[FlowQuestionInFeed]  # first 5 questions? ask gpt if this is needed
    num_total_elements: int


class FlowDetail(FlowInFeed):
    # but now with all questions
    num_user_answers: int
    num_user_correct_answers: int


class FlowInSearch(FlowDetail):
    pass


class QuestionDensity(
    StrEnum
):  # number of questions per block if input type is files, or total number if input type is topic
    NOT_APPLICABLE = "not_applicable"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PromptType(StrEnum):
    EXPERT = "expert"
    DEFAULT = "default"


class AddQuestionsToFlowAI(BaseModel):
    question_density: QuestionDensity
    subject: str = Field(default="", max_length=255)
    prompt_type: PromptType = PromptType.DEFAULT
    extra_instructions: str = Field(
        default="", max_length=255
    )  # this should not go to system message!!! just user message


class AddQuestionsToFlowOfficial(BaseModel):
    question_density: QuestionDensity
    area: str = Field(default="", max_length=255)
    source_filter: str = Field(default="", max_length=255)
    difficulty: FlowDifficulty = Field(default=FlowDifficulty.ALL)


class SubmitAnswerMultipleChoice(BaseModel):
    question_id: int
    choice_id: int | None
