from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field

from app.base import ContentBlock
from app.flows.models import (
    Campaign,
    Choice,
    Flow,
    FlowDifficulty,
    FlowQuestion,
    FlowQuestionUser,
    QuestionAnswerType,
    QuestionDifficulty,
    QuestionSourceType,
)


class SimpleUser(BaseModel):
    id: int
    username: str


class AnswerInFeed(BaseModel):
    user: SimpleUser
    submitted_text: str
    choice_id: int | None

    @classmethod
    def from_orm_model(cls, flow_question_user: FlowQuestionUser) -> "AnswerInFeed":
        return cls(
            user=SimpleUser(
                id=flow_question_user.user.id, username=flow_question_user.user.username
            ),
            submitted_text=flow_question_user.submitted_text,
            choice_id=flow_question_user.choice_id,
        )


class ChoiceInFeed(BaseModel):
    id: int
    text: str
    image: str | None
    is_correct: bool

    @classmethod
    def from_orm_model(cls, choice: Choice) -> "ChoiceInFeed":
        return cls(
            id=choice.id,
            text=choice.text,
            image=choice.image.url if choice.image else None,
            is_correct=choice.is_correct,
        )


class FlowQuestionInFeed(BaseModel):
    id: int
    element_type: Literal["flow_question"]
    content_blocks: list[ContentBlock]
    relevant_answers: list[AnswerInFeed]  # all answers for now
    num_total_answers: int
    choices: list[ChoiceInFeed]

    subject: str
    category: str
    subcategory: str
    difficulty: QuestionDifficulty

    source_type: QuestionSourceType
    official_source: str
    source_user: SimpleUser | None

    answer_type: QuestionAnswerType

    @classmethod
    def from_orm_model(cls, flow_question: FlowQuestion) -> "FlowQuestionInFeed":
        return cls(
            id=flow_question.id,
            element_type="flow_question",
            content_blocks=flow_question.question.content_blocks,
            relevant_answers=[
                AnswerInFeed.from_orm_model(answer)
                for answer in flow_question.flow_question_users
            ],
            num_total_answers=flow_question.num_total_answers,
            choices=[
                ChoiceInFeed.from_orm_model(choice)
                for choice in flow_question.question.choices
            ],
            subject=flow_question.question.subject,
            category=flow_question.question.category,
            subcategory=flow_question.question.subcategory,
            difficulty=flow_question.question.difficulty,
            source_type=flow_question.question.source_type,
            official_source=flow_question.question.official_source,
            source_user=SimpleUser(
                id=flow_question.question.source_user.id,
                username=flow_question.question.source_user.username,
            )
            if flow_question.question.source_user
            else None,
            answer_type=flow_question.question.answer_type,
        )


class FlowInFeed(BaseModel):
    id: int
    code: UUID
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

    @classmethod
    def from_orm_model(cls, flow: Flow) -> "FlowInFeed":
        return cls(
            id=flow.id,
            code=flow.code,
            created_at=flow.created_at,
            title=flow.title,
            cover_image=flow.cover_image.url if flow.cover_image else None,
            action_link=flow.action_link,
            action_text=flow.action_text,
            created_by=SimpleUser(
                id=flow.created_by.id, username=flow.created_by.username
            ),
            query=flow.query,
            area=flow.area,
            source_filter=flow.source_filter,
            difficulty=flow.difficulty,
            elements=[
                FlowQuestionInFeed.from_orm_model(element)
                for element in flow.elements
                if isinstance(element, FlowQuestion)
            ],
            num_total_elements=flow.num_total_elements,
        )


class FlowDetail(FlowInFeed):
    # but now with all questions
    num_user_total_answers: int
    num_user_correct_answers: int

    @classmethod
    def from_orm_model_for_user(cls, flow: Flow, *, user_id: int) -> "FlowDetail":
        return cls(
            id=flow.id,
            code=flow.code,
            created_at=flow.created_at,
            title=flow.title,
            cover_image=flow.cover_image.url if flow.cover_image else None,
            action_link=flow.action_link,
            action_text=flow.action_text,
            created_by=SimpleUser(
                id=flow.created_by.id, username=flow.created_by.username
            ),
            query=flow.query,
            area=flow.area,
            source_filter=flow.source_filter,
            difficulty=flow.difficulty,
            elements=[
                FlowQuestionInFeed.from_orm_model(element)
                for element in flow.elements
                if isinstance(element, FlowQuestion)
            ],
            num_total_elements=flow.num_total_elements,
            num_user_total_answers=flow.num_user_total_answers(user_id),
            num_user_correct_answers=flow.num_user_correct_answers(user_id),
        )


class FlowInSearch(FlowDetail):
    @classmethod
    def from_orm_model_for_user(cls, flow: Flow, *, user_id: int) -> "FlowInSearch":
        return cls(
            id=flow.id,
            code=flow.code,
            created_at=flow.created_at,
            title=flow.title,
            cover_image=flow.cover_image.url if flow.cover_image else None,
            action_link=flow.action_link,
            action_text=flow.action_text,
            created_by=SimpleUser(
                id=flow.created_by.id, username=flow.created_by.username
            ),
            query=flow.query,
            area=flow.area,
            source_filter=flow.source_filter,
            difficulty=flow.difficulty,
            elements=[
                FlowQuestionInFeed.from_orm_model(element)
                for element in flow.elements
                if isinstance(element, FlowQuestion)
            ],
            num_total_elements=flow.num_total_elements,
            num_user_total_answers=flow.num_user_total_answers(user_id),
            num_user_correct_answers=flow.num_user_correct_answers(user_id),
        )


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


class CampaignInFeed(BaseModel):
    id: int
    name: str
    text: str
    action_link: str
    action_text: str
    cover_image: str | None

    @classmethod
    def from_orm_model(cls, campaign: Campaign) -> "CampaignInFeed":
        return cls(
            id=campaign.id,
            name=campaign.name,
            text=campaign.text,
            action_link=campaign.action_link,
            action_text=campaign.action_text,
            cover_image=campaign.cover_image.url if campaign.cover_image else None,
        )
