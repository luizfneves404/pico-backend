from app.flows.models import (
    Choice,
    Flow,
    FlowElement,
    FlowQuestion,
    FlowQuestionUser,
    Question,
)
from app.shared.admin import Admin


class FlowAdmin(Admin, model=Flow):
    column_list = [
        Flow.id,
        Flow.code,
        Flow.created_at,
        Flow.title,
        Flow.query,
        Flow.area,
    ]
    column_searchable_list = [Flow.id, Flow.code, Flow.title, Flow.query, Flow.area]
    column_sortable_list = [Flow.id, Flow.created_at, Flow.area]
    column_details_list = [
        Flow.id,
        Flow.code,
        Flow.title,
        Flow.created_at,
        Flow.query,
        Flow.area,
        Flow.source_filter,
        Flow.difficulty,
        Flow.question_answer_type,
    ]


class FlowElementAdmin(Admin, model=FlowElement):
    column_list = [
        FlowElement.id,
        FlowElement.flow_id,
        FlowElement.question_id,
        FlowElement.created_at,
    ]
    column_searchable_list = [
        FlowElement.id,
        FlowElement.flow_id,
        FlowElement.question_id,
    ]
    column_sortable_list = [
        FlowElement.id,
        FlowElement.created_at,
    ]
    column_details_list = [
        FlowElement.id,
        FlowElement.flow_id,
        FlowElement.question_id,
        FlowElement.created_at,
    ]


class QuestionAdmin(Admin, model=Question):
    column_list = [
        Question.id,
        Question.subject,
        Question.difficulty,
        Question.is_active,
        Question.source_type,
        Question.answer_type,
    ]
    column_searchable_list = [
        Question.id,
        Question.subject,
        Question.category,
        Question.subcategory,
    ]
    column_sortable_list = [
        Question.id,
        Question.created_at,
        Question.subject,
        Question.difficulty,
        Question.source_type,
    ]
    column_details_list = [
        Question.id,
        Question.subject,
        Question.category,
        Question.subcategory,
        Question.difficulty,
        Question.is_active,
        Question.source_type,
        Question.official_source,
        Question.answer_type,
        Question.parameter_a,
        Question.parameter_b,
        Question.parameter_c,
        Question.created_at,
    ]

    form_excluded_columns = [
        Question.created_at,
        Question.embedding,
    ]


class ChoiceAdmin(Admin, model=Choice):
    column_list = [
        Choice.id,
        Choice.question_id,
        Choice.text,
        Choice.is_correct,
        Choice.order,
    ]
    column_searchable_list = [Choice.id, Choice.text, Choice.question_id]
    column_sortable_list = [
        Choice.id,
        Choice.question_id,
        Choice.is_correct,
        Choice.order,
    ]
    column_details_list = [
        Choice.id,
        Choice.question_id,
        Choice.text,
        Choice.is_correct,
        Choice.order,
        Choice.created_at,
    ]


class FlowQuestionAdmin(Admin, model=FlowQuestion):
    column_list = [
        FlowQuestion.id,
        FlowQuestion.flow_id,
        FlowQuestion.question_id,
        FlowQuestion.created_at,
    ]
    column_searchable_list = [
        FlowQuestion.id,
        FlowQuestion.flow_id,
        FlowQuestion.question_id,
    ]
    column_sortable_list = [
        FlowQuestion.id,
        FlowQuestion.created_at,
    ]
    column_details_list = [
        FlowQuestion.id,
        FlowQuestion.flow_id,
        FlowQuestion.question_id,
        FlowQuestion.created_at,
    ]


class FlowQuestionUserAdmin(Admin, model=FlowQuestionUser):
    column_list = [
        FlowQuestionUser.id,
        FlowQuestionUser.flow_element_id,
        FlowQuestionUser.user_id,
        FlowQuestionUser.choice_id,
        FlowQuestionUser.grade,
        FlowQuestionUser.created_at,
    ]
    column_searchable_list = [
        FlowQuestionUser.id,
        FlowQuestionUser.flow_element_id,
        FlowQuestionUser.user_id,
        FlowQuestionUser.submitted_text,
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
