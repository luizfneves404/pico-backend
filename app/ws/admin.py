from app.shared.admin import CustomModelView
from app.ws.models import UserOnlineInfo


class UserOnlineInfoAdmin(CustomModelView, model=UserOnlineInfo):
    icon = "fa-solid fa-plug"

    column_list = [
        UserOnlineInfo.id,
        UserOnlineInfo.user_id,
        UserOnlineInfo.last_websocket_connection,
        UserOnlineInfo.last_websocket_disconnection,
        UserOnlineInfo.created_at,
    ]
    column_searchable_list = [
        UserOnlineInfo.user_id,
    ]
    column_sortable_list = [
        UserOnlineInfo.id,
        UserOnlineInfo.user_id,
        UserOnlineInfo.last_websocket_connection,
        UserOnlineInfo.last_websocket_disconnection,
        UserOnlineInfo.created_at,
    ]
    column_details_list = [
        UserOnlineInfo.id,
        UserOnlineInfo.user_id,
        UserOnlineInfo.last_websocket_connection,
        UserOnlineInfo.last_websocket_disconnection,
        UserOnlineInfo.created_at,
    ]

    form_columns = [
        "user_id",
        "last_websocket_connection",
        "last_websocket_disconnection",
    ]
