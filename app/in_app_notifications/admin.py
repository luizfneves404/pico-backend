from app.in_app_notifications.models import (
    ExternalInAppNotification,
    FlowInAppNotification,
    InAppNotification,
)
from app.shared.admin import Admin


class InAppNotificationAdmin(Admin, model=InAppNotification):
    icon = "fa-solid fa-bell"

    column_list = [
        InAppNotification.id,
        InAppNotification.user_id,
        InAppNotification.text,
        InAppNotification.seen,
        InAppNotification.in_app_notification_type,
        InAppNotification.created_at,
    ]
    column_searchable_list = [
        InAppNotification.user_id,
        InAppNotification.text,
        InAppNotification.in_app_notification_type,
    ]
    column_sortable_list = [
        InAppNotification.id,
        InAppNotification.user_id,
        InAppNotification.seen,
        InAppNotification.in_app_notification_type,
        InAppNotification.created_at,
    ]
    column_details_list = [
        InAppNotification.id,
        InAppNotification.user_id,
        InAppNotification.text,
        InAppNotification.seen,
        InAppNotification.in_app_notification_type,
        InAppNotification.created_at,
    ]

    form_columns = [
        "user_id",
        "text",
        "seen",
        "in_app_notification_type",
        "flow_id",
        "external_url",
    ]


class ExternalInAppNotificationAdmin(Admin, model=ExternalInAppNotification):
    icon = "fa-solid fa-external-link"

    column_list = [
        ExternalInAppNotification.id,
        ExternalInAppNotification.user_id,
        ExternalInAppNotification.text,
        ExternalInAppNotification.external_url,
        ExternalInAppNotification.seen,
        ExternalInAppNotification.created_at,
    ]
    column_searchable_list = [
        ExternalInAppNotification.user_id,
        ExternalInAppNotification.text,
        ExternalInAppNotification.external_url,
    ]
    column_sortable_list = [
        ExternalInAppNotification.id,
        ExternalInAppNotification.user_id,
        ExternalInAppNotification.seen,
        ExternalInAppNotification.created_at,
    ]
    column_details_list = [
        ExternalInAppNotification.id,
        ExternalInAppNotification.user_id,
        ExternalInAppNotification.text,
        ExternalInAppNotification.external_url,
        ExternalInAppNotification.seen,
        ExternalInAppNotification.created_at,
    ]

    form_columns = [
        "user_id",
        "text",
        "external_url",
        "seen",
    ]


class FlowInAppNotificationAdmin(Admin, model=FlowInAppNotification):
    icon = "fa-solid fa-stream"

    column_list = [
        FlowInAppNotification.id,
        FlowInAppNotification.user_id,
        FlowInAppNotification.flow_id,
        FlowInAppNotification.text,
        FlowInAppNotification.seen,
        FlowInAppNotification.created_at,
    ]
    column_searchable_list = [
        FlowInAppNotification.user_id,
        FlowInAppNotification.flow_id,
        FlowInAppNotification.text,
    ]
    column_sortable_list = [
        FlowInAppNotification.id,
        FlowInAppNotification.user_id,
        FlowInAppNotification.flow_id,
        FlowInAppNotification.seen,
        FlowInAppNotification.created_at,
    ]
    column_details_list = [
        FlowInAppNotification.id,
        FlowInAppNotification.user_id,
        FlowInAppNotification.flow_id,
        FlowInAppNotification.text,
        FlowInAppNotification.seen,
        FlowInAppNotification.created_at,
    ]

    form_columns = [
        "user_id",
        "flow_id",
        "text",
        "seen",
    ]
