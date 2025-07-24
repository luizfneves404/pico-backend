import logging
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field

from app.flows.db_types import ImageBlockBase, ImageBlockDB, TextBlock
from app.flows.models import (
    Campaign,
    Choice,
    Exam,
    Flow,
    FlowDifficulty,
    FlowQuestion,
    FlowQuestionUser,
    QuestionAnswerType,
    QuestionArea,
    QuestionDifficulty,
    QuestionSourceType,
)

logger = logging.getLogger(__name__)


class ImageBlockAPI(ImageBlockBase):
    file_url: str


ContentBlockAPI = Annotated[
    TextBlock | ImageBlockAPI, Field(discriminator="block_type")
]


class SimpleUser(BaseModel):
    id: int
    username: str
    name: str


class AnswerInFeed(BaseModel):
    user: SimpleUser
    submitted_text: str
    choice_id: int | None

    @classmethod
    def from_orm_model(cls, flow_question_user: FlowQuestionUser) -> "AnswerInFeed":
        return cls(
            user=SimpleUser(
                id=flow_question_user.user.id,
                username=flow_question_user.user.username,
                name=flow_question_user.user.name,
            ),
            submitted_text=flow_question_user.submitted_text,
            choice_id=flow_question_user.choice_id,
        )


class ChoiceInFeed(BaseModel):
    id: int
    text: str
    image_url: str | None
    is_correct: bool

    @classmethod
    async def from_orm_model(cls, choice: Choice) -> "ChoiceInFeed":
        return cls(
            id=choice.id,
            text=choice.text,
            image_url=await choice.image.get_url() if choice.image else None,
            is_correct=choice.is_correct,
        )


class FlowQuestionInFeed(BaseModel):
    id: int
    element_type: Literal["flow_question"]
    content_blocks: list[ContentBlockAPI]
    answer_content_blocks: list[ContentBlockAPI]
    has_me_answered_in_any_flow: bool
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
    async def from_orm_model(
        cls,
        flow_question: FlowQuestion,
        *,
        user_id: int,
        image_id_to_file_url: dict[int, str],
    ) -> "FlowQuestionInFeed":
        return cls(
            id=flow_question.question.id,
            element_type="flow_question",
            content_blocks=[
                ImageBlockAPI(
                    block_type="image",
                    alt=block.alt,
                    file_url=image_id_to_file_url[block.image_id],
                )
                if isinstance(block, ImageBlockDB)
                else block
                for block in flow_question.question.content_blocks
            ],
            answer_content_blocks=[
                ImageBlockAPI(
                    block_type="image",
                    alt=block.alt,
                    file_url=image_id_to_file_url[block.image_id],
                )
                if isinstance(block, ImageBlockDB)
                else block
                for block in flow_question.question.answer_content_blocks
            ],
            has_me_answered_in_any_flow=flow_question.question.has_user_answered(
                user_id
            ),
            relevant_answers=[
                AnswerInFeed.from_orm_model(answer)
                for answer in flow_question.flow_question_users
            ],
            num_total_answers=flow_question.num_total_answers,
            choices=[
                await ChoiceInFeed.from_orm_model(choice)
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
                    name=flow_question.question.source_user.name,
                )
                if flow_question.question.source_user
                else None
            ),
            answer_type=flow_question.question.answer_type,
        )


class FlowBase(BaseModel):
    id: int
    code: UUID
    created_at: AwareDatetime
    title: str

    cover_image_url: str | None
    action_link: str  # not link of the flow
    action_text: str
    created_by: SimpleUser

    difficulty: FlowDifficulty
    max_num_questions: int

    num_total_elements: int
    num_users_answered: int

    @classmethod
    async def from_orm_model(cls, flow: Flow) -> "FlowBase":
        return cls(
            id=flow.id,
            code=flow.code,
            created_at=flow.created_at,
            title=flow.title,
            cover_image_url=await flow.cover_image.get_url()
            if flow.cover_image
            else None,
            action_link=flow.action_link,
            action_text=flow.action_text,
            created_by=SimpleUser(
                id=flow.created_by.id,
                username=flow.created_by.username,
                name=flow.created_by.name,
            ),
            difficulty=flow.difficulty,
            max_num_questions=flow.max_num_questions,
            num_total_elements=flow.num_total_elements,
            num_users_answered=flow.num_users_answered,
        )


class FlowInFeed(FlowBase):
    elements: list[FlowQuestionInFeed]

    @classmethod
    async def from_orm_model_with_context(
        cls, flow: Flow, *, user_id: int, image_id_to_file_url: dict[int, str]
    ) -> "FlowInFeed":
        flow_base = await FlowBase.from_orm_model(flow)
        return cls(
            id=flow_base.id,
            code=flow_base.code,
            created_at=flow_base.created_at,
            title=flow_base.title,
            cover_image_url=flow_base.cover_image_url,
            action_link=flow_base.action_link,
            action_text=flow_base.action_text,
            created_by=flow_base.created_by,
            difficulty=flow_base.difficulty,
            max_num_questions=flow_base.max_num_questions,
            elements=[
                await FlowQuestionInFeed.from_orm_model(
                    element, user_id=user_id, image_id_to_file_url=image_id_to_file_url
                )
                for i, element in enumerate(flow.elements)
                if isinstance(element, FlowQuestion)
                and (i == 0 or flow.elements[i - 1].order == flow.elements[i].order - 1)
            ],
            num_total_elements=flow_base.num_total_elements,
            num_users_answered=flow_base.num_users_answered,
        )


class FlowDetail(FlowInFeed):
    num_me_total_answers: int
    num_me_correct_answers: int

    @classmethod
    async def from_orm_model_with_context(
        cls, flow: Flow, *, user_id: int, image_id_to_file_url: dict[int, str]
    ) -> "FlowDetail":
        flow_in_feed = await FlowInFeed.from_orm_model_with_context(
            flow, user_id=user_id, image_id_to_file_url=image_id_to_file_url
        )
        return cls(
            id=flow_in_feed.id,
            code=flow_in_feed.code,
            created_at=flow_in_feed.created_at,
            title=flow_in_feed.title,
            cover_image_url=flow_in_feed.cover_image_url,
            action_link=flow_in_feed.action_link,
            action_text=flow_in_feed.action_text,
            created_by=flow_in_feed.created_by,
            max_num_questions=flow_in_feed.max_num_questions,
            difficulty=flow_in_feed.difficulty,
            elements=flow_in_feed.elements,
            num_total_elements=flow_in_feed.num_total_elements,
            num_users_answered=flow_in_feed.num_users_answered,
            num_me_total_answers=flow.num_user_total_answers(user_id),
            num_me_correct_answers=flow.num_user_correct_answers(user_id),
        )


class FlowInSearch(FlowBase):
    num_me_total_answers: int
    num_me_correct_answers: int

    @classmethod
    async def from_orm_model_for_user(
        cls, flow: Flow, *, user_id: int
    ) -> "FlowInSearch":
        flow_base = await FlowBase.from_orm_model(flow)
        return cls(
            id=flow_base.id,
            code=flow_base.code,
            created_at=flow_base.created_at,
            title=flow_base.title,
            cover_image_url=flow_base.cover_image_url,
            action_link=flow_base.action_link,
            action_text=flow_base.action_text,
            created_by=flow_base.created_by,
            max_num_questions=flow_base.max_num_questions,
            difficulty=flow_base.difficulty,
            num_total_elements=flow_base.num_total_elements,
            num_users_answered=flow_base.num_users_answered,
            num_me_total_answers=flow.num_user_total_answers(user_id),
            num_me_correct_answers=flow.num_user_correct_answers(user_id),
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
    image1_url: str | None
    image2_url: str | None

    @classmethod
    async def from_orm_model(cls, campaign: Campaign) -> "CampaignInFeed":
        return cls(
            id=campaign.id,
            name=campaign.name,
            text=campaign.text,
            external_link=campaign.external_link,
            external_link_text=campaign.external_link_text,
            image1_url=await campaign.image1.get_url() if campaign.image1 else None,
            image2_url=await campaign.image2.get_url() if campaign.image2 else None,
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
            country_code=exam.country.code,
            education_level_id=exam.education_level_id,
        )


class QuestionAreaOut(BaseModel):
    name: str

    @classmethod
    def from_orm_model(cls, question_area: QuestionArea) -> "QuestionAreaOut":
        return cls(
            name=question_area.name,
        )
