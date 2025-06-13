from app.shared.admin import Admin
from app.ws.models import UserWebsocketInfo


class UserWebsocketInfoAdmin(Admin, model=UserWebsocketInfo):
    icon = "fa-solid fa-plug"

    column_list = [
        UserWebsocketInfo.id,
        UserWebsocketInfo.user_id,
        UserWebsocketInfo.last_websocket_connection,
        UserWebsocketInfo.last_websocket_disconnection,
        UserWebsocketInfo.created_at,
    ]
    column_searchable_list = [
        UserWebsocketInfo.user_id,
    ]
    column_sortable_list = [
        UserWebsocketInfo.id,
        UserWebsocketInfo.user_id,
        UserWebsocketInfo.last_websocket_connection,
        UserWebsocketInfo.last_websocket_disconnection,
        UserWebsocketInfo.created_at,
    ]
    column_details_list = [
        UserWebsocketInfo.id,
        UserWebsocketInfo.user_id,
        UserWebsocketInfo.last_websocket_connection,
        UserWebsocketInfo.last_websocket_disconnection,
        UserWebsocketInfo.created_at,
    ]

    form_columns = [
        "user_id",
        "last_websocket_connection",
        "last_websocket_disconnection",
    ]
