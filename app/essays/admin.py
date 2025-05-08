from typing import Any, ClassVar

from app.essays.models import Essay, EssayTopic, EssayType, Feedback, FeedbackCategory
from app.shared.admin import Admin


class EssayTopicAdmin(Admin, model=EssayTopic):
    column_list = [
        EssayTopic.id,
        EssayTopic.name,
        EssayTopic.created_at,
    ]
    column_searchable_list = [EssayTopic.id, EssayTopic.name]
    column_sortable_list = [EssayTopic.id, EssayTopic.created_at]


class EssayTypeAdmin(Admin, model=EssayType):
    column_list = [
        EssayType.id,
        EssayType.name,
        EssayType.created_at,
    ]
    column_searchable_list = [EssayType.id, EssayType.name]
    column_sortable_list = [EssayType.id, EssayType.created_at]


class EssayAdmin(Admin, model=Essay):
    column_list = [
        Essay.id,
        Essay.essay_topic_id,
        Essay.author_id,
        Essay.essay_type_id,
        Essay.created_at,
    ]
    column_searchable_list = [Essay.id, Essay.essay_topic_id, Essay.author_id]
    column_sortable_list = [Essay.id, Essay.created_at]
    column_details_list = [
        Essay.id,
        Essay.essay_topic_id,
        Essay.author_id,
        Essay.essay_type_id,
        Essay.original_file_id,
        Essay.cleaned_text,
        Essay.user_corrected_text,
        Essay.created_at,
    ]
    form_ajax_refs: ClassVar[dict[str, dict[str, Any]]] = {
        "original_file": {
            "fields": ("original_name", "file_id"),
            "order_by": ["id"],
        }
    }


class FeedbackCategoryAdmin(Admin, model=FeedbackCategory):
    column_list = [
        FeedbackCategory.id,
        FeedbackCategory.name,
        FeedbackCategory.essay_type_id,
        FeedbackCategory.temperature,
        FeedbackCategory.created_at,
    ]
    column_searchable_list = [FeedbackCategory.id, FeedbackCategory.name]
    column_sortable_list = [FeedbackCategory.id, FeedbackCategory.created_at]


class FeedbackAdmin(Admin, model=Feedback):
    column_list = [
        Feedback.id,
        Feedback.essay_id,
        Feedback.feedback_category_id,
        Feedback.grade,
        Feedback.created_at,
    ]
    column_searchable_list = [Feedback.id, Feedback.essay_id]
    column_sortable_list = [Feedback.id, Feedback.created_at, Feedback.grade]
    column_details_list = [
        Feedback.id,
        Feedback.essay_id,
        Feedback.feedback_category_id,
        Feedback.text,
        Feedback.grade,
        Feedback.created_at,
    ]
