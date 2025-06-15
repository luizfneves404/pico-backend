from typing import Any, ClassVar, Sequence, Union

from fastapi import Request
from sqlalchemy import Select, select
from sqlalchemy.orm import selectinload

from app.flows.models import (
    Campaign,
    Choice,
    Exam,
    Flow,
    FlowElement,
    FlowQuestion,
    FlowQuestionUser,
    FlowTranscriptionBlock,
    FlowUserFeed,
    OfficialQuestionSource,
    Question,
    QuestionArea,
)
from app.shared.admin import MODEL_ATTR, CustomModelView


class FlowAdmin(CustomModelView, model=Flow):
    icon = "fa-solid fa-stream"

    column_list: ClassVar[Union[str, Sequence[MODEL_ATTR]]] = [
        Flow.id,
        Flow.code,
        Flow.title,
        Flow.created_by,
        Flow.flow_input_type,
        Flow.difficulty,
        Flow.question_answer_type,
        Flow.source_type,
        "num_total_questions",
        Flow.created_at,
    ]
    column_searchable_list = [
        Flow.title,
        Flow.input_topic,
        Flow.major_tags,
        Flow.minor_tags,
    ]
    column_sortable_list = [
        Flow.id,
        Flow.title,
        Flow.created_at,
        Flow.difficulty,
        Flow.flow_input_type,
        Flow.source_type,
    ]
    column_details_list: ClassVar[Union[str, Sequence[MODEL_ATTR]]] = [
        Flow.id,
        Flow.code,
        Flow.title,
        Flow.created_by,
        Flow.cover_image,
        Flow.action_link,
        Flow.action_text,
        Flow.max_num_questions,
        Flow.difficulty,
        Flow.question_answer_type,
        Flow.source_type,
        Flow.flow_input_type,
        Flow.input_topic,
        Flow.major_tags,
        Flow.minor_tags,
        "num_total_questions",
        "num_total_elements",
        "num_total_answers",
        Flow.created_at,
    ]

    column_labels: ClassVar[dict[MODEL_ATTR, str]] = {
        "num_total_questions": "Total Questions",
        "num_total_elements": "Total Elements",
        "num_total_answers": "Total Answers",
        Flow.created_by: "Created By",
        Flow.cover_image: "Cover Image",
    }

    form_columns: ClassVar[Union[str, Sequence[MODEL_ATTR]]] = [
        Flow.title,
        Flow.created_by,
        Flow.cover_image,
        Flow.action_link,
        Flow.action_text,
        Flow.max_num_questions,
        Flow.difficulty,
        Flow.question_answer_type,
        Flow.source_type,
        Flow.flow_input_type,
        Flow.input_topic,
        Flow.major_tags,
        Flow.minor_tags,
    ]

    def list_query(self, request: Request) -> Select[tuple[Flow]]:
        return select(Flow).options(
            selectinload(Flow.created_by),
            selectinload(Flow.cover_image),
        )

    async def get_object_for_details(self, value: Any) -> Any:
        stmt = (
            select(Flow)
            .options(
                selectinload(Flow.created_by),
                selectinload(Flow.cover_image),
                selectinload(Flow.elements),
            )
            .where(Flow.id == int(value))
        )
        return await self._get_object_by_pk(stmt)


class FlowTranscriptionBlockAdmin(CustomModelView, model=FlowTranscriptionBlock):
    icon = "fa-solid fa-file-text"

    column_list = [
        FlowTranscriptionBlock.id,
        FlowTranscriptionBlock.flow_id,
        FlowTranscriptionBlock.block_number,
        FlowTranscriptionBlock.title,
        FlowTranscriptionBlock.created_at,
    ]
    column_searchable_list = [
        FlowTranscriptionBlock.flow_id,
        FlowTranscriptionBlock.title,
        FlowTranscriptionBlock.block_text,
    ]
    column_sortable_list = [
        FlowTranscriptionBlock.id,
        FlowTranscriptionBlock.flow_id,
        FlowTranscriptionBlock.block_number,
        FlowTranscriptionBlock.created_at,
    ]
    column_details_list = [
        FlowTranscriptionBlock.id,
        FlowTranscriptionBlock.flow_id,
        FlowTranscriptionBlock.block_number,
        FlowTranscriptionBlock.title,
        FlowTranscriptionBlock.block_text,
        FlowTranscriptionBlock.created_at,
    ]

    form_columns = [
        FlowTranscriptionBlock.flow_id,
        FlowTranscriptionBlock.block_number,
        FlowTranscriptionBlock.title,
        FlowTranscriptionBlock.block_text,
    ]


class FlowElementAdmin(CustomModelView, model=FlowElement):
    icon = "fa-solid fa-list"

    column_list = [
        FlowElement.id,
        FlowElement.flow_id,
        FlowElement.element_type,
        FlowElement.order,
        FlowElement.question_id,
        FlowElement.created_at,
    ]
    column_searchable_list = [
        FlowElement.flow_id,
        FlowElement.question_id,
        FlowElement.element_type,
    ]
    column_sortable_list = [
        FlowElement.id,
        FlowElement.flow_id,
        FlowElement.order,
        FlowElement.created_at,
    ]
    column_details_list = [
        FlowElement.id,
        FlowElement.flow_id,
        FlowElement.element_type,
        FlowElement.order,
        FlowElement.question_id,
        FlowElement.created_at,
    ]

    form_columns = [
        FlowElement.flow_id,
        FlowElement.order,
        FlowElement.element_type,
        FlowElement.question_id,
    ]


class QuestionAdmin(CustomModelView, model=Question):
    icon = "fa-solid fa-question-circle"

    column_list = [
        Question.id,
        Question.difficulty,
        Question.answer_type,
        Question.is_quantitative,
        Question.is_active,
        Question.source_type,
        Question.major_tags,
        Question.minor_tags,
        Question.created_at,
    ]
    column_searchable_list = [
        Question.major_tags,
        Question.minor_tags,
    ]
    column_sortable_list = [
        Question.id,
        Question.created_at,
        Question.is_quantitative,
        Question.difficulty,
        Question.source_type,
        Question.is_active,
    ]
    column_details_list = [
        Question.id,
        Question.content_blocks,
        Question.is_active,
        Question.is_quantitative,
        Question.major_tags,
        Question.minor_tags,
        Question.difficulty,
        Question.parameter_a,
        Question.parameter_b,
        Question.parameter_c,
        Question.answer_content_blocks,
        Question.source_type,
        Question.official_source,
        Question.source_user,
        Question.answer_type,
        Question.created_at,
    ]

    column_labels: ClassVar[dict[MODEL_ATTR, str]] = {
        Question.is_quantitative: "Quantitative?",
        Question.is_active: "Active?",
        Question.source_type: "Source Type",
        Question.answer_type: "Answer Type",
        Question.official_source: "Official Source",
        Question.source_user: "Source User",
    }

    form_excluded_columns = [
        "created_at",
        "embedding",
        "flows",
        "flow_questions",
    ]

    def list_query(self, request: Request) -> Select[tuple[Question]]:
        return select(Question).options(
            selectinload(Question.official_source),
            selectinload(Question.source_user),
        )


class QuestionAreaAdmin(CustomModelView, model=QuestionArea):
    icon = "fa-solid fa-map"

    column_list = [
        QuestionArea.id,
        QuestionArea.name,
        QuestionArea.education_level,
        QuestionArea.country,
        QuestionArea.course,
        QuestionArea.created_at,
    ]
    column_searchable_list = [
        QuestionArea.name,
        QuestionArea.tags,
    ]
    column_sortable_list = [
        QuestionArea.id,
        QuestionArea.name,
        QuestionArea.created_at,
    ]
    column_details_list = [
        QuestionArea.id,
        QuestionArea.name,
        QuestionArea.tags,
        QuestionArea.education_level,
        QuestionArea.country,
        QuestionArea.course,
        QuestionArea.created_at,
    ]

    form_columns = [
        QuestionArea.name,
        QuestionArea.tags,
        QuestionArea.education_level_id,
        QuestionArea.country_code,
        QuestionArea.course_id,
    ]


class ExamAdmin(CustomModelView, model=Exam):
    icon = "fa-solid fa-clipboard-check"

    column_list = [
        Exam.id,
        Exam.name,
        Exam.country,
        Exam.education_level,
        Exam.course,
        Exam.created_at,
    ]
    column_searchable_list = [
        Exam.name,
    ]
    column_sortable_list = [
        Exam.id,
        Exam.name,
        Exam.created_at,
    ]
    column_details_list = [
        Exam.id,
        Exam.name,
        Exam.country,
        Exam.education_level,
        Exam.course,
        Exam.created_at,
    ]

    form_columns = [
        Exam.name,
        Exam.country_code,
        Exam.education_level_id,
        Exam.course_id,
    ]


class OfficialQuestionSourceAdmin(CustomModelView, model=OfficialQuestionSource):
    icon = "fa-solid fa-certificate"

    column_list = [
        OfficialQuestionSource.id,
        OfficialQuestionSource.exam,
        OfficialQuestionSource.year,
        OfficialQuestionSource.created_at,
    ]
    column_searchable_list = [
        OfficialQuestionSource.year,
    ]
    column_sortable_list = [
        OfficialQuestionSource.id,
        OfficialQuestionSource.year,
        OfficialQuestionSource.created_at,
    ]
    column_details_list = [
        OfficialQuestionSource.id,
        OfficialQuestionSource.exam,
        OfficialQuestionSource.year,
        OfficialQuestionSource.created_at,
    ]

    form_columns = [
        OfficialQuestionSource.exam_id,
        OfficialQuestionSource.year,
    ]


class FlowUserFeedAdmin(CustomModelView, model=FlowUserFeed):
    icon = "fa-solid fa-rss"

    column_list = [
        FlowUserFeed.id,
        FlowUserFeed.user_id,
        FlowUserFeed.flow_id,
        FlowUserFeed.created_at,
    ]
    column_searchable_list = [
        FlowUserFeed.user_id,
        FlowUserFeed.flow_id,
    ]
    column_sortable_list = [
        FlowUserFeed.id,
        FlowUserFeed.user_id,
        FlowUserFeed.flow_id,
        FlowUserFeed.created_at,
    ]
    column_details_list = [
        FlowUserFeed.id,
        FlowUserFeed.user_id,
        FlowUserFeed.flow_id,
        FlowUserFeed.created_at,
    ]

    form_columns = [
        FlowUserFeed.user_id,
        FlowUserFeed.flow_id,
    ]


class CampaignAdmin(CustomModelView, model=Campaign):
    icon = "fa-solid fa-bullhorn"

    column_list = [
        Campaign.id,
        Campaign.name,
        Campaign.campaign_type,
        Campaign.probability,
        Campaign.created_at,
    ]
    column_searchable_list = [
        Campaign.name,
        Campaign.text,
        Campaign.campaign_type,
    ]
    column_sortable_list = [
        Campaign.id,
        Campaign.name,
        Campaign.campaign_type,
        Campaign.probability,
        Campaign.created_at,
    ]
    column_details_list = [
        Campaign.id,
        Campaign.name,
        Campaign.text,
        Campaign.external_link,
        Campaign.external_link_text,
        Campaign.image1,
        Campaign.image2,
        Campaign.probability,
        Campaign.campaign_type,
        Campaign.created_at,
    ]

    column_labels: ClassVar[dict[MODEL_ATTR, str]] = {
        Campaign.campaign_type: "Type",
        Campaign.external_link: "External Link",
        Campaign.external_link_text: "Link Text",
        Campaign.image1: "Image 1",
        Campaign.image2: "Image 2",
    }

    form_columns = [
        Campaign.name,
        Campaign.text,
        Campaign.external_link,
        Campaign.external_link_text,
        Campaign.image1_id,
        Campaign.image2_id,
        Campaign.probability,
        Campaign.campaign_type,
    ]


class ChoiceAdmin(CustomModelView, model=Choice):
    icon = "fa-solid fa-check-circle"

    column_list = [
        Choice.id,
        Choice.question_id,
        Choice.text,
        Choice.is_correct,
        Choice.order,
        Choice.created_at,
    ]
    column_searchable_list = [
        Choice.text,
        Choice.question_id,
    ]
    column_sortable_list = [
        Choice.id,
        Choice.question_id,
        Choice.is_correct,
        Choice.order,
        Choice.created_at,
    ]
    column_details_list = [
        Choice.id,
        Choice.question_id,
        Choice.text,
        Choice.image,
        Choice.is_correct,
        Choice.order,
        Choice.created_at,
    ]

    column_labels: ClassVar[dict[MODEL_ATTR, str]] = {
        "is_correct": "Correct?",
        "question_id": "Question",
    }

    form_columns = [
        Choice.question_id,
        Choice.text,
        Choice.image_id,
        Choice.is_correct,
        Choice.order,
    ]


class FlowQuestionAdmin(CustomModelView, model=FlowQuestion):
    icon = "fa-solid fa-question"

    column_list: ClassVar[Union[str, Sequence[MODEL_ATTR]]] = [
        FlowQuestion.id,
        FlowQuestion.flow_id,
        FlowQuestion.question_id,
        FlowQuestion.order,
        "num_total_answers",
        FlowQuestion.created_at,
    ]
    column_searchable_list = [
        FlowQuestion.flow_id,
        FlowQuestion.question_id,
    ]
    column_sortable_list = [
        FlowQuestion.id,
        FlowQuestion.flow_id,
        FlowQuestion.order,
        FlowQuestion.created_at,
    ]
    column_details_list: ClassVar[Union[str, Sequence[MODEL_ATTR]]] = [
        FlowQuestion.id,
        FlowQuestion.flow_id,
        FlowQuestion.question_id,
        FlowQuestion.order,
        "num_total_answers",
        FlowQuestion.created_at,
    ]

    column_labels: ClassVar[dict[MODEL_ATTR, str]] = {
        "num_total_answers": "Total Answers",
        "flow_id": "Flow",
        "question_id": "Question",
    }

    form_columns = [
        FlowQuestion.flow_id,
        FlowQuestion.question_id,
        FlowQuestion.order,
    ]


class FlowQuestionUserAdmin(CustomModelView, model=FlowQuestionUser):
    icon = "fa-solid fa-user-check"

    column_list = [
        FlowQuestionUser.id,
        FlowQuestionUser.flow_element_id,
        FlowQuestionUser.user_id,
        FlowQuestionUser.choice_id,
        FlowQuestionUser.grade,
        FlowQuestionUser.created_at,
    ]
    column_searchable_list = [
        FlowQuestionUser.flow_element_id,
        FlowQuestionUser.user_id,
        FlowQuestionUser.submitted_text,
        FlowQuestionUser.feedback,
    ]
    column_sortable_list = [
        FlowQuestionUser.id,
        FlowQuestionUser.created_at,
        FlowQuestionUser.grade,
    ]
    column_details_list = [
        FlowQuestionUser.id,
        FlowQuestionUser.flow_element_id,
        FlowQuestionUser.user_id,
        FlowQuestionUser.choice_id,
        FlowQuestionUser.submitted_text,
        FlowQuestionUser.feedback,
        FlowQuestionUser.grade,
        FlowQuestionUser.created_at,
    ]

    column_labels: ClassVar[dict[MODEL_ATTR, str]] = {
        "flow_element_id": "Flow Element",
        "user_id": "User",
        "choice_id": "Choice",
        "submitted_text": "Submitted Text",
    }

    form_columns = [
        FlowQuestionUser.flow_element_id,
        FlowQuestionUser.user_id,
        FlowQuestionUser.choice_id,
        FlowQuestionUser.submitted_text,
        FlowQuestionUser.feedback,
        FlowQuestionUser.grade,
    ]
