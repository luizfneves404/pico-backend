from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field

from app.flows.db_types import ContentBlock
from app.flows.models import (
    Campaign,
    Choice,
    Exam,
    Flow,
    FlowDifficulty,
    FlowQuestion,
    FlowQuestionUser,
    FlowSourceType,
    QuestionAnswerType,
    QuestionArea,
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
    answer_content_blocks: list[ContentBlock]
    relevant_answers: list[AnswerInFeed]  # all answers for now
    num_total_answers: int
    choices: list[ChoiceInFeed]

    is_quantitative: bool
    major_tags: list[str]
    minor_tags: list[str]
    difficulty: QuestionDifficulty

    source_type: QuestionSourceType
    official_source: str | None
    source_user: SimpleUser | None

    answer_type: QuestionAnswerType

    @classmethod
    def from_orm_model(cls, flow_question: FlowQuestion) -> "FlowQuestionInFeed":
        return cls(
            id=flow_question.id,
            element_type="flow_question",
            content_blocks=flow_question.question.content_blocks,
            answer_content_blocks=flow_question.question.answer_content_blocks,
            relevant_answers=[
                AnswerInFeed.from_orm_model(answer)
                for answer in flow_question.flow_question_users
            ],
            num_total_answers=flow_question.num_total_answers,
            choices=[
                ChoiceInFeed.from_orm_model(choice)
                for choice in flow_question.question.choices
            ],
            is_quantitative=flow_question.question.is_quantitative,
            major_tags=flow_question.question.major_tags,
            minor_tags=flow_question.question.minor_tags,
            difficulty=flow_question.question.difficulty,
            source_type=flow_question.question.source_type,
            official_source=(
                flow_question.question.official_source.exam.name
                if flow_question.question.official_source
                else None
            ),
            source_user=(
                SimpleUser(
                    id=flow_question.question.source_user.id,
                    username=flow_question.question.source_user.username,
                )
                if flow_question.question.source_user
                else None
            ),
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

    difficulty: FlowDifficulty
    max_num_questions: int

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
            difficulty=flow.difficulty,
            max_num_questions=flow.max_num_questions,
            elements=[
                FlowQuestionInFeed.from_orm_model(element)
                for i, element in enumerate(flow.elements)
                if isinstance(element, FlowQuestion)
                and (i == 0 or flow.elements[i - 1].order == flow.elements[i].order - 1)
            ],
            num_total_elements=flow.num_total_elements,
        )


class FlowDetail(FlowInFeed):
    # but now with all questions
    num_user_total_answers: int
    num_user_correct_answers: int

    @classmethod
    def from_orm_model_for_user(cls, flow: Flow, *, user_id: int) -> "FlowDetail":
        flow_in_feed = FlowInFeed.from_orm_model(flow)
        return cls(
            id=flow_in_feed.id,
            code=flow_in_feed.code,
            created_at=flow_in_feed.created_at,
            title=flow_in_feed.title,
            cover_image=flow_in_feed.cover_image,
            action_link=flow_in_feed.action_link,
            action_text=flow_in_feed.action_text,
            created_by=flow_in_feed.created_by,
            max_num_questions=flow_in_feed.max_num_questions,
            difficulty=flow_in_feed.difficulty,
            elements=flow_in_feed.elements,
            num_total_elements=flow_in_feed.num_total_elements,
            num_user_total_answers=flow.num_user_total_answers(user_id),
            num_user_correct_answers=flow.num_user_correct_answers(user_id),
        )


class FlowInSearch(FlowDetail):
    @classmethod
    def from_orm_model_for_user(cls, flow: Flow, *, user_id: int) -> "FlowInSearch":
        flow_detail = FlowDetail.from_orm_model_for_user(flow, user_id=user_id)
        return cls(
            id=flow_detail.id,
            code=flow_detail.code,
            created_at=flow_detail.created_at,
            title=flow_detail.title,
            cover_image=flow_detail.cover_image,
            action_link=flow_detail.action_link,
            action_text=flow_detail.action_text,
            created_by=flow_detail.created_by,
            max_num_questions=flow_detail.max_num_questions,
            difficulty=flow_detail.difficulty,
            elements=flow_detail.elements,
            num_total_elements=flow_detail.num_total_elements,
            num_user_total_answers=flow_detail.num_user_total_answers,
            num_user_correct_answers=flow_detail.num_user_correct_answers,
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
    question_density: QuestionDensity = QuestionDensity.MEDIUM
    prompt_type: PromptType = PromptType.DEFAULT
    extra_instructions: str = Field(
        default="", max_length=255
    )  # this should not go to system message!!! just user message


class AddQuestionsToFlowOfficial(BaseModel):
    question_density: QuestionDensity = QuestionDensity.MEDIUM
    question_area_name: str = Field(default="", max_length=255)
    exam_id: int | None = None
    exam_country_code: str | None = None
    exam_education_level_id: int | None = None
    source_year: int | None = None


class AddQuestionsToFlowFull(BaseModel):
    question_density: QuestionDensity = QuestionDensity.MEDIUM
    prompt_type: PromptType = PromptType.DEFAULT
    extra_instructions: str = Field(
        default="", max_length=255
    )  # this should not go to system message!!! just user message
    question_area_name: str = Field(default="", max_length=255)
    exam_id: int | None = None
    exam_country_code: str | None = None
    exam_education_level_id: int | None = None
    source_year: int | None = None

class SubmitAnswerMultipleChoiceRequest(BaseModel):
    question_id: int
    choice_id: int | None


class SubmitAnswerMultipleChoiceResponse(BaseModel):
    xp_increase: int


class CampaignInFeed(BaseModel):
    id: int
    name: str
    text: str
    external_link: str
    external_link_text: str
    image1: str | None
    image2: str | None

    @classmethod
    def from_orm_model(cls, campaign: Campaign) -> "CampaignInFeed":
        return cls(
            id=campaign.id,
            name=campaign.name,
            text=campaign.text,
            external_link=campaign.external_link,
            external_link_text=campaign.external_link_text,
            image1=campaign.image1.url if campaign.image1 else None,
            image2=campaign.image2.url if campaign.image2 else None,
        )


class FlowFeedItem(BaseModel):
    item_type: Literal[
        "flow"
    ]  # didn't add as default because OpenAPI will render it as optional
    item: FlowInFeed


class CampaignFeedItem(BaseModel):
    item_type: Literal[
        "campaign"
    ]  # didn't add as default because OpenAPI will render it as optional
    item: CampaignInFeed


FeedItem = Annotated[FlowFeedItem | CampaignFeedItem, Field(discriminator="item_type")]


class ExamOut(BaseModel):
    id: int
    name: str
    country_code: str
    education_level_id: int

    @classmethod
    def from_orm_model(cls, exam: Exam) -> "ExamOut":
        return cls(
            id=exam.id,
            name=exam.name,
            country_code=exam.country_code,
            education_level_id=exam.education_level_id,
        )


class QuestionAreaOut(BaseModel):
    name: str

    @classmethod
    def from_orm_model(cls, question_area: QuestionArea) -> "QuestionAreaOut":
        return cls(
            name=question_area.name,
        )
