from collections.abc import Sequence
from typing import ClassVar

from app.shared.admin import MODEL_ATTR, CustomModelView
from app.ws.models import UserOnlineInfo


class UserOnlineInfoAdmin(CustomModelView, model=UserOnlineInfo):
    icon = "fa-solid fa-plug"

    column_list: ClassVar[str | Sequence[MODEL_ATTR]] = [
        UserOnlineInfo.id,
        UserOnlineInfo.user_id,
        UserOnlineInfo.last_websocket_connection,
        UserOnlineInfo.last_websocket_disconnection,
        UserOnlineInfo.created_at,
    ]
    column_searchable_list: ClassVar[str | Sequence[MODEL_ATTR]] = [
        UserOnlineInfo.user_id,
    ]
    column_sortable_list: ClassVar[str | Sequence[MODEL_ATTR]] = [
        UserOnlineInfo.id,
        UserOnlineInfo.user_id,
        UserOnlineInfo.last_websocket_connection,
        UserOnlineInfo.last_websocket_disconnection,
        UserOnlineInfo.created_at,
    ]
    column_details_list: ClassVar[str | Sequence[MODEL_ATTR]] = [
        UserOnlineInfo.id,
        UserOnlineInfo.user_id,
        UserOnlineInfo.last_websocket_connection,
        UserOnlineInfo.last_websocket_disconnection,
        UserOnlineInfo.created_at,
    ]

    form_columns: ClassVar[str | Sequence[MODEL_ATTR]] = [
        "user_id",
        "last_websocket_connection",
        "last_websocket_disconnection",
    ]
