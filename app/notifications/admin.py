from pydantic import BaseModel

from app.notifications.models import (
    ExternalInAppNotification,
    FlowInAppNotification,
    InAppNotification,
)
from app.shared.admin import CustomModelView


class InAppNotificationAdmin(CustomModelView, model=InAppNotification):
    icon = "fa-solid fa-bell"
    can_create = False

    column_list = [
        InAppNotification.id,
        InAppNotification.user_id,
        InAppNotification.text,
        InAppNotification.seen,
        InAppNotification.in_app_notification_type,
        InAppNotification.created_at,
        FlowInAppNotification.flow_id,
        ExternalInAppNotification.external_url,
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
        "user",
        "text",
        "seen",
        "in_app_notification_type",
    ]


class ExternalInAppNotificationImportSchema(BaseModel):
    user_id: int
    text: str
    external_url: str
    seen: bool


class ExternalInAppNotificationAdmin(CustomModelView, model=ExternalInAppNotification):
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

    form_columns = ["user", "text", "seen", "external_url"]

    can_import = True
    import_schema = ExternalInAppNotificationImportSchema
    import_template_data = {
        "user_id": 1,
        "text": "Hello, world!",
        "external_url": "https://www.google.com",
        "seen": False,
    }

    async def to_orm_model(
        self, validated_data_list: list[ExternalInAppNotificationImportSchema]
    ) -> list[ExternalInAppNotification]:
        return [
            ExternalInAppNotification(
                user_id=validated_data.user_id,
                text=validated_data.text,
                external_url=validated_data.external_url,
                seen=validated_data.seen,
            )
            for validated_data in validated_data_list
        ]


class FlowInAppNotificationImportSchema(BaseModel):
    user_id: int
    flow_id: int
    text: str
    seen: bool


class FlowInAppNotificationAdmin(CustomModelView, model=FlowInAppNotification):
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

    form_columns = ["user", "text", "seen", "flow"]

    can_import = True
    import_schema = FlowInAppNotificationImportSchema
    import_template_data = {
        "user_id": 1,
        "flow_id": 1,
        "text": "Hello, world!",
        "seen": False,
    }

    async def to_orm_model(
        self, validated_data_list: list[FlowInAppNotificationImportSchema]
    ) -> list[FlowInAppNotification]:
        return [
            FlowInAppNotification(
                user_id=validated_data.user_id,
                flow_id=validated_data.flow_id,
                text=validated_data.text,
                seen=validated_data.seen,
            )
            for validated_data in validated_data_list
        ]
