import logging

import api.services.chatroom_service as chatroom_service
import api.services.fcm_service as fcm_service
import api.services.message_service as message_service
import api.services.user_service as user_service
import notifications.utils as notifications_utils
from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from commands.tasks import handle_command_workflow

import chat.chat_service as chat_service
import pico_backend.amp as pico_backend_amp
from chat.schemas import MessageEventIn

logger = logging.getLogger(__name__)

VALIDATING_MESSAGE_ERROR = "Error validating message event: {}"
USER_NOT_AUTHENTICATED_WARNING = "AnonymousUser tried to connect but is not authenticated in notifications. Error code: {}"
USER_DISCONNECTED_INFO = "User {} disconnected from notifications"

WEBSOCKET_MESSAGE_EVENT_TYPE = "Websocket Message"


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        """
        Handles the WebSocket connection.
        """
        self.user = self.scope["user"]

        if self.user.is_authenticated:
            await self._handle_authenticated_user()
        elif "error_code" in self.scope:
            await self._handle_unauthenticated_user_with_error_code()
        else:
            await self._handle_unauthenticated_user()

    async def disconnect(self, close_code):
        """
        Handles WebSocket disconnection.
        """
        logger.debug(f"User {self.user.id} disconnecting from notifications...")
        await self._handle_group_discard()
        await self._update_user_status_offline()
        await sync_to_async(chat_service.update_disconnection_timestamp)(self.user.id)
        logger.info(USER_DISCONNECTED_INFO.format(self.user.id))

    async def _handle_authenticated_user(self):
        """
        Handles actions to be performed when the user is authenticated.
        """
        await notifications_utils.aset_user_status(self.user.id, "online")

        logger.info(
            f"User is authenticated in notifications with id: {self.user.id} and"
            f" username: {self.user.username}"
        )
        self.notifications_name = f"notifications_{self.user.id}"

        await self.channel_layer.group_add(self.notifications_name, self.channel_name)

        logger.debug(f"Added user to notifications group: {self.notifications_name}")

        await sync_to_async(chat_service.update_connection_timestamp)(self.user.id)

        await self.accept()

        await self._send_undelivered_notifications()

        await sync_to_async(fcm_service.send_reset_badge_notification)(self.user.id)

    async def _handle_unauthenticated_user_with_error_code(self):
        """
        Handles unauthenticated users when an error code is present in the scope.
        """
        logger.warning(USER_NOT_AUTHENTICATED_WARNING.format(self.scope["error_code"]))
        await self.close(code=self.scope["error_code"])

    async def _handle_unauthenticated_user(self):
        """
        Handles unauthenticated users with no specific error code.
        """
        logger.warning(
            "AnonymousUser tried to connect but is not authenticated in notifications. Unknown error."
        )
        await self.close(code=4000)

    async def receive_json(self, content):
        """
        Handles receiving a JSON message.
        """
        logger.debug(f"Received json from {self.user.username}: {content}")
        try:
            message_event = MessageEventIn.model_validate(content)
            logger.debug(
                f"Received valid json from {self.user.username} for message event: {content}"
            )
            await self._process_message_event(message_event)
        except Exception as e:
            logger.error(VALIDATING_MESSAGE_ERROR.format(e), exc_info=True)
            await notifications_utils.prepare_error_notification(
                self.user.id, VALIDATING_MESSAGE_ERROR.format(e)
            ).send_async()

    async def notification_message(self, event):
        await self.send_json(content=event)

    async def notification_chatroom_rename(self, event):
        await self.send_json(content=event)

    async def notification_leave(self, event):
        await self.send_json(content=event)

    async def notification_add_member(self, event):
        await self.send_json(content=event)

    async def notification_remove_member(self, event):
        await self.send_json(content=event)

    async def notification_make_admin(self, event):
        await self.send_json(content=event)

    async def notification_remove_admin(self, event):
        await self.send_json(content=event)

    async def notification_cleaned_text(self, event):
        await self.send_json(content=event)

    async def notification_essay_correction(self, event):
        await self.send_json(content=event)

    async def notification_error(self, event):
        await self.send_json(content=event)

    async def notification_feature_error(self, event):
        await self.send_json(content=event)

    async def _process_message_event(self, message_event: MessageEventIn):
        """
        Processes the message event received in JSON format.
        """
        if message_event.chatroom_id is None:
            try:
                chatroom = await chatroom_service.aget_official_chatroom(self.user)
            except chatroom_service.OfficialChatroomNotFound:
                chatroom = await user_service.create_official_chatroom_for_user(
                    self.user
                )
        else:
            chatroom = await chatroom_service.aget_chatroom_for_user(
                self.user, message_event.chatroom_id
            )
        logger.debug(
            f"Processing message event for chatroom {chatroom.id} and user {self.user.id}"
        )

        parent_message = await message_service.aget_top_level_message(
            message_event.parent_message_id, chatroom
        )

        await message_service.asend_message(
            sender=self.user,
            chatroom=chatroom,
            content=message_event.message,
            parent_message=parent_message,
        )

        pico_backend_amp.track_amplitude_event(
            self.user.id, WEBSOCKET_MESSAGE_EVENT_TYPE, {"chatroom_id": chatroom.id}
        )

        if message_event.message.lstrip().startswith("/"):
            await handle_command_workflow(
                message_event.message,
                chatroom.id,
                parent_message.id if parent_message else None,
                self.user.id,
            )

    async def _handle_group_discard(self):
        """
        Handles discarding the user from the group upon disconnect.
        """
        if hasattr(self, "notifications_name"):
            logger.debug(
                f"Removing user from notifications group: {self.notifications_name}"
            )
            await self.channel_layer.group_discard(
                self.notifications_name, self.channel_name
            )
            logger.debug(
                f"Removed user from notifications group: {self.notifications_name}"
            )
        else:
            logger.debug("User is not in a notifications group, no need to discard")

    async def _update_user_status_offline(self):
        """
        Updates the user's status to offline.
        """
        if self.user.is_authenticated:
            await notifications_utils.aset_user_status(self.user.id, "offline")

    async def _send_undelivered_notifications(self):
        queued_events = await notifications_utils.aget_queued_notifications(
            self.user.id
        )

        for event_str in queued_events:
            await self.send(event_str)
