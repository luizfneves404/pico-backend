"""in order to help with explicitly synchronizing the async things that the test methods do,
do something to wait for a response from the server, such as communicator.receive_json_from()
after sending json, for example.
Test with wifi turned off to ensure no external api calls are being made."""

import logging
import sys
from unittest.mock import MagicMock, patch

from api.file_tasks import (
    FILE_TOO_BIG_MESSAGE,
    FINISHED_READING_MESSAGE,
    NO_TEXT_IN_FILE_MESSAGE,
)
from api.models import User
from api.services.message_service import WILL_READ_MESSAGE
from api.tests.factories import GroupChatroomFactory, MessageFactory, UserFactory
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from pico_backend.asgi import application
from pico_backend.auth import generate_tokens
from shared.testing import PatchingAndRedisTestCase

sys.modules["channels.testing.live"] = MagicMock()

logger = logging.getLogger(__name__)


User = get_user_model()


class NotificationTestCase(PatchingAndRedisTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user1 = UserFactory.create()
        cls.user2 = UserFactory.create()

        cls.access_token1, _ = generate_tokens(cls.user1)
        cls.access_token2, _ = generate_tokens(cls.user2)

        cls.auth_headers = {"Authorization": f"Bearer {cls.access_token1}"}

        cls.system_user = User.objects.get_system_user()
        cls.pico_user = User.objects.get_pico_user()

        cls.chatroom = GroupChatroomFactory.create()
        cls.chatroom.add_member(cls.user1, admin=True)
        cls.chatroom.add_member(cls.user2)
        cls.chatroom_id = cls.chatroom.pk

        cls.fake_chatroom = GroupChatroomFactory.create()
        cls.fake_message = MessageFactory.create(chatroom=cls.fake_chatroom)

    def setUp(self):
        super().setUp()

        self.client = Client(headers=self.auth_headers)

    def tearDown(self):
        patch.stopall()

    async def connect(self, token=None):
        from channels.testing import WebsocketCommunicator

        headers = []
        if token:
            headers.append(("Authorization", f"Bearer {token}"))
        communicator = WebsocketCommunicator(
            application, self.get_ws_url(), headers=headers
        )

        connected, subprotocol = await communicator.connect()
        return communicator, connected, subprotocol

    async def connect_jwt_query_param(self, token=None):
        from channels.testing import WebsocketCommunicator

        communicator = WebsocketCommunicator(
            application,
            self.get_ws_url(token=token),
        )
        connected, subprotocol = await communicator.connect()
        return communicator, connected, subprotocol

    def get_ws_url(self, token=None):
        return f"/ws/notifications?token={token}" if token else "/ws/notifications"

    async def test_token_required(self):
        communicator, connected, close_code = await self.connect()
        self.assertFalse(connected)
        self.assertEqual(close_code, 4010)

        await communicator.disconnect()

    async def test_invalid_token(self):
        communicator, connected, close_code = await self.connect(token="invalidtoken")
        self.assertFalse(connected)
        self.assertEqual(close_code, 4011)

        await communicator.disconnect()

    async def test_jwt_query_param(self):
        communicator, connected, _ = await self.connect_jwt_query_param(
            token=self.access_token1
        )
        self.assertTrue(connected)

        await communicator.disconnect()

    async def test_jwt_header(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        await communicator.disconnect()

    async def test_invalid_message(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        # Send a message to the chatroom
        message_content = "hello world!"
        await communicator.send_json_to(
            {"message": message_content, "chatroom_id": "heyy"}
        )

        # Receive error notification
        response = await communicator.receive_json_from()
        self.assertIsNotNone(response.get("error", None))
        await communicator.disconnect()

    async def test_chatroom_does_not_exist(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        # Send a message to the chatroom
        message_content = "hello world!"
        await communicator.send_json_to(
            {"chatroom_id": 999, "message": message_content}
        )

        # Receive error notification
        response = await communicator.receive_json_from(timeout=5)
        self.assertEqual(
            response["error"],
            "Error validating message event: Chatroom not found for this user",
        )

        await communicator.disconnect()

    async def test_not_member_of_chatroom(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        # Send a message to the chatroom
        message_content = "hello world!"
        await communicator.send_json_to(
            {"chatroom_id": self.fake_chatroom.pk, "message": message_content}
        )

        # Receive error notification
        response = await communicator.receive_json_from()
        self.assertEqual(
            response["error"],
            "Error validating message event: Chatroom not found for this user",
        )
        await communicator.disconnect()

    async def test_top_level_message_not_found(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        # Send a message to the chatroom
        message_content = "hello world!"
        await communicator.send_json_to(
            {
                "chatroom_id": self.chatroom.pk,
                "parent_message_id": 999,
                "message": message_content,
            }
        )

        # Receive error notification
        response = await communicator.receive_json_from(timeout=5)
        self.assertEqual(
            response["error"],
            "Error validating message event: Top-level message not found for this chatroom",
        )
        await communicator.disconnect()

    async def test_top_level_message_not_in_chatroom(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        # Send a message to the chatroom
        message_content = "hello world!"
        await communicator.send_json_to(
            {
                "chatroom_id": self.chatroom.pk,
                "parent_message_id": self.fake_message.pk,
                "message": message_content,
            }
        )

        # Receive error notification
        response = await communicator.receive_json_from()
        self.assertEqual(
            response["error"],
            "Error validating message event: Top-level message not found for this chatroom",
        )
        await communicator.disconnect()

    async def test_chatroom_rename(self):
        communicator1, connected1, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected1)

        communicator2, connected2, _ = await self.connect(token=self.access_token2)
        self.assertTrue(connected2)

        # user 1 renames the chatroom
        url = reverse("api:chatroom_detail", kwargs={"chatroom_id": self.chatroom.pk})
        data = {"name": "New Chatroom Name"}
        response = await sync_to_async(self.client.patch)(
            url, data, content_type="application/json"
        )

        # user 1 receives the rename event
        response = await communicator1.receive_json_from()
        self.assertEqual(response["chatroom_id"], self.chatroom.pk)
        self.assertEqual(response["by_user"]["id"], self.user1.id)
        self.assertEqual(response["name"], "New Chatroom Name")

        # user 2 receives the rename event
        response = await communicator2.receive_json_from()
        self.assertEqual(response["chatroom_id"], self.chatroom.pk)
        self.assertEqual(response["by_user"]["id"], self.user1.id)
        self.assertEqual(response["name"], "New Chatroom Name")

        # user 1 receives the rename system message
        response = await communicator1.receive_json_from()
        self.assertEqual(response["chatroom_id"], self.chatroom.pk)
        self.assertEqual(response["message"]["sender"]["id"], self.system_user.id)
        self.assertEqual(
            response["message"]["content"],
            f"User {self.user1.username} renamed the chatroom to 'New Chatroom Name'",
        )

        # user 2 receives the rename system message
        response = await communicator2.receive_json_from()
        self.assertEqual(response["chatroom_id"], self.chatroom.pk)
        self.assertEqual(response["message"]["sender"]["id"], self.system_user.id)
        self.assertEqual(
            response["message"]["content"],
            f"User {self.user1.username} renamed the chatroom to 'New Chatroom Name'",
        )

        await communicator1.disconnect()
        await communicator2.disconnect()

    async def test_chatroom_leave(self):
        communicator1, connected1, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected1)

        communicator2, connected2, _ = await self.connect(token=self.access_token2)
        self.assertTrue(connected2)

        # user 1 leaves the chatroom
        url = reverse("api:chatroom_leave", kwargs={"chatroom_id": self.chatroom.pk})
        response = await sync_to_async(self.client.patch)(
            url, content_type="application/json"
        )

        # user 1 receives the leave event
        response = await communicator1.receive_json_from()
        self.assertEqual(response["chatroom_id"], self.chatroom.pk)
        self.assertEqual(response["user"]["id"], self.user1.id)

        # user 2 receives the leave event
        response = await communicator2.receive_json_from()
        self.assertEqual(response["chatroom_id"], self.chatroom.pk)
        self.assertEqual(response["user"]["id"], self.user1.id)

        # user 1 receives the leave system message
        response = await communicator1.receive_json_from()
        self.assertEqual(response["chatroom_id"], self.chatroom.pk)
        self.assertEqual(response["message"]["sender"]["id"], self.system_user.id)
        self.assertEqual(
            response["message"]["content"],
            f"User {self.user1.username} left the chatroom",
        )

        # user 2 receives the leave system message
        response = await communicator2.receive_json_from()
        self.assertEqual(response["chatroom_id"], self.chatroom.pk)
        self.assertEqual(response["message"]["sender"]["id"], self.system_user.id)
        self.assertEqual(
            response["message"]["content"],
            f"User {self.user1.username} left the chatroom",
        )

        await communicator1.disconnect()
        await communicator2.disconnect()

    async def test_chatroom_add_member(self):
        await self.chatroom.aremove_member(self.user2)

        communicator1, connected1, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected1)

        (
            communicator2,
            connected2,
            _,
        ) = await self.connect(token=self.access_token2)

        self.assertTrue(connected2)
        # user 1 adds user 2
        url = reverse(
            "api:chatroom_add_member", kwargs={"chatroom_id": self.chatroom.pk}
        )
        data = {"username": self.user2.username}
        response = await sync_to_async(self.client.patch)(
            url, data, content_type="application/json"
        )

        # user 1 receives the add_member event
        response = await communicator1.receive_json_from()
        self.assertEqual(response["chatroom_id"], self.chatroom.pk)
        self.assertEqual(response["added_by_user"]["id"], self.user1.id)
        self.assertEqual(response["added_user"]["id"], self.user2.id)

        # user 2 receives the add_member event
        response = await communicator2.receive_json_from()
        self.assertEqual(response["chatroom_id"], self.chatroom.pk)
        self.assertEqual(response["added_by_user"]["id"], self.user1.id)
        self.assertEqual(response["added_user"]["id"], self.user2.id)

        # user 1 receives the add_member system message
        response = await communicator1.receive_json_from()
        self.assertEqual(response["chatroom_id"], self.chatroom.pk)
        self.assertEqual(response["message"]["sender"]["id"], self.system_user.id)
        self.assertEqual(
            response["message"]["content"],
            f"User {self.user1.username} added user {self.user2.username}",
        )

        # user 2 receives the add_member system message
        response = await communicator2.receive_json_from()
        self.assertEqual(response["chatroom_id"], self.chatroom.pk)
        self.assertEqual(response["message"]["sender"]["id"], self.system_user.id)
        self.assertEqual(
            response["message"]["content"],
            f"User {self.user1.username} added user {self.user2.username}",
        )

        await communicator1.disconnect()
        await communicator2.disconnect()

    async def test_chatroom_remove_member(self):
        communicator1, connected1, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected1)

        communicator2, connected2, _ = await self.connect(token=self.access_token2)
        self.assertTrue(connected2)

        # user 1 removes user 2
        url = reverse(
            "api:chatroom_remove_member", kwargs={"chatroom_id": self.chatroom.pk}
        )
        data = {"username": self.user2.username}
        response = await sync_to_async(self.client.patch)(
            url, data, content_type="application/json"
        )

        # user 1 receives the remove_member event
        response = await communicator1.receive_json_from()
        self.assertEqual(response["chatroom_id"], self.chatroom.pk)
        self.assertEqual(response["removed_by_user"]["id"], self.user1.id)
        self.assertEqual(response["removed_user"]["id"], self.user2.id)

        # user 2 receives the remove_member event
        response = await communicator2.receive_json_from()
        self.assertEqual(response["chatroom_id"], self.chatroom.pk)
        self.assertEqual(response["removed_by_user"]["id"], self.user1.id)
        self.assertEqual(response["removed_user"]["id"], self.user2.id)

        # user 1 receives the remove_member system message
        response = await communicator1.receive_json_from()
        self.assertEqual(response["chatroom_id"], self.chatroom.pk)
        self.assertEqual(response["message"]["sender"]["id"], self.system_user.id)
        self.assertEqual(
            response["message"]["content"],
            f"User {self.user1.username} removed user {self.user2.username}",
        )

        # user 2 receives the remove_member system message
        response = await communicator2.receive_json_from()
        self.assertEqual(response["chatroom_id"], self.chatroom.pk)
        self.assertEqual(response["message"]["sender"]["id"], self.system_user.id)
        self.assertEqual(
            response["message"]["content"],
            f"User {self.user1.username} removed user {self.user2.username}",
        )

        await communicator1.disconnect()
        await communicator2.disconnect()

    async def test_chatroom_make_admin(self):
        communicator1, connected1, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected1)

        communicator2, connected2, _ = await self.connect(token=self.access_token2)
        self.assertTrue(connected2)

        # user 1 makes user 2 admin
        url = reverse(
            "api:chatroom_make_admin", kwargs={"chatroom_id": self.chatroom.pk}
        )
        data = {"username": self.user2.username}
        response = await sync_to_async(self.client.patch)(
            url, data, content_type="application/json"
        )

        # user 1 receives the make_admin event
        response = await communicator1.receive_json_from()
        self.assertEqual(response["chatroom_id"], self.chatroom.pk)
        self.assertEqual(response["by_user"]["id"], self.user1.id)
        self.assertEqual(response["to_user"]["id"], self.user2.id)

        # user 2 receives the make_admin event
        response = await communicator2.receive_json_from()
        self.assertEqual(response["chatroom_id"], self.chatroom.pk)
        self.assertEqual(response["by_user"]["id"], self.user1.id)
        self.assertEqual(response["to_user"]["id"], self.user2.id)

        await communicator1.disconnect()
        await communicator2.disconnect()

    async def test_chatroom_remove_admin(self):
        communicator1, connected1, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected1)

        communicator2, connected2, _ = await self.connect(token=self.access_token2)
        self.assertTrue(connected2)
        await self.chatroom.aset_admin(self.user2, True)

        # user 1 removes admin status from user 2
        url = reverse(
            "api:chatroom_remove_admin", kwargs={"chatroom_id": self.chatroom.pk}
        )
        data = {"username": self.user2.username}
        response = await sync_to_async(self.client.patch)(
            url, data, content_type="application/json"
        )

        # user 1 receives the remove_admin event
        response = await communicator1.receive_json_from()
        self.assertEqual(response["chatroom_id"], self.chatroom.pk)
        self.assertEqual(response["by_user"]["id"], self.user1.id)
        self.assertEqual(response["to_user"]["id"], self.user2.id)

        # user 2 receives the remove_admin event
        response = await communicator2.receive_json_from()
        self.assertEqual(response["chatroom_id"], self.chatroom.pk)
        self.assertEqual(response["by_user"]["id"], self.user1.id)
        self.assertEqual(response["to_user"]["id"], self.user2.id)

        await communicator1.disconnect()
        await communicator2.disconnect()

    async def test_user_receives_other_user_message(self):
        communicator1, connected1, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected1)

        communicator2, connected2, _ = await self.connect(token=self.access_token2)
        self.assertTrue(connected2)

        # Send a message to the chatroom
        message_content = "hello world!"
        await communicator1.send_json_to(
            {"chatroom_id": self.chatroom_id, "message": message_content}
        )

        # Receive my message back
        response = await communicator1.receive_json_from(timeout=3)
        self.assertEqual(response["message"]["content"], message_content)
        self.assertEqual(response["message"]["sender"]["id"], self.user1.id)

        # user 2 receives the message
        response = await communicator2.receive_json_from()
        self.assertEqual(response["chatroom_id"], self.chatroom_id)
        self.assertEqual(response["message"]["sender"]["id"], self.user1.id)
        self.assertEqual(response["message"]["content"], message_content)

        await communicator1.disconnect()
        await communicator2.disconnect()

    def create_attachment_message_through_http(self):
        with open("pico_django/api/tests/test_files/test_photo.png", "rb") as file:
            file = SimpleUploadedFile(
                "test_photo.png", file.read(), content_type="image/png"
            )
        data = {"content": "Test Attachment Message", "upload": file}
        url = reverse(
            "api:chatroom_message_list",
            kwargs={"chatroom_id": self.chatroom.pk},
        )

        return self.client.post(url, data)

    async def test_user_receives_other_user_attachment_message(self):
        communicator1, connected1, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected1)

        communicator2, connected2, _ = await self.connect(token=self.access_token2)
        self.assertTrue(connected2)

        # Send an attachment message to the chatroom
        response_create = await sync_to_async(
            self.create_attachment_message_through_http
        )()
        self.assertEqual(response_create.status_code, 201)

        # Receive my message back
        response_receive = await communicator1.receive_json_from()
        self.assertEqual(
            response_receive["message"]["content"], "Test Attachment Message"
        )
        self.assertEqual(response_receive["message"]["sender"]["id"], self.user1.id)

        # user 2 receives the message
        response_receive = await communicator2.receive_json_from()
        self.assertEqual(response_receive["chatroom_id"], self.chatroom.pk)
        self.assertEqual(response_receive["message"]["sender"]["id"], self.user1.id)
        self.assertEqual(
            response_receive["message"]["attachment"],
            response_create.json()["attachment"],
        )

        await communicator1.disconnect()
        await communicator2.disconnect()

    def create_pdf_message_through_http(self, filepath: str, filename: str):
        with open(filepath, "rb") as file:
            file = SimpleUploadedFile(
                filename, file.read(), content_type="application/pdf"
            )
        data = {"content": "Test PDF Message", "upload": file}
        url = reverse(
            "api:chatroom_message_list",
            kwargs={"chatroom_id": self.chatroom.pk},
        )

        return self.client.post(url, data)

    async def test_pdf_message_processing(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        await sync_to_async(self.create_pdf_message_through_http)(
            "pico_django/api/tests/test_files/test_pdf.pdf", "test_pdf.pdf"
        )

        # Receive my message back
        response = await communicator.receive_json_from()
        self.assertEqual(response["message"]["content"], "Test PDF Message")
        self.assertEqual(response["message"]["sender"]["id"], self.user1.id)

        # Receive pdf processing message from the chatbot
        response = await communicator.receive_json_from()
        pico_user = await User.objects.aget_pico_user()

        self.assertEqual(response["chatroom_id"], self.chatroom_id)
        self.assertEqual(
            response["message"]["content"],
            WILL_READ_MESSAGE,
        )
        self.assertEqual(response["message"]["sender"]["id"], pico_user.id)

        # Receive pdf finished processing message from the chatbot
        response = await communicator.receive_json_from(timeout=10)
        self.assertEqual(response["chatroom_id"], self.chatroom_id)
        self.assertEqual(
            response["message"]["content"],
            FINISHED_READING_MESSAGE,
        )
        self.assertEqual(response["message"]["sender"]["id"], pico_user.id)

        await communicator.disconnect()

    async def test_pdf_message_processing_too_big(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        await sync_to_async(self.create_pdf_message_through_http)(
            "pico_django/api/tests/test_files/test_too_big_pdf.pdf",
            "test_too_big_pdf.pdf",
        )

        await communicator.receive_json_from()

        await communicator.receive_json_from()

        response = await communicator.receive_json_from()

        pico_user = await User.objects.aget_pico_user()

        self.assertEqual(response["message"]["content"], FILE_TOO_BIG_MESSAGE)
        self.assertEqual(response["chatroom_id"], self.chatroom.pk)
        self.assertEqual(response["message"]["sender"]["id"], pico_user.id)

        await communicator.disconnect()

    def list_messages_through_http(self):
        url = reverse(
            "api:chatroom_message_list",
            kwargs={"chatroom_id": self.chatroom.pk},
        )
        return self.client.get(url)

    async def test_thread_message(self):
        communicator1, connected1, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected1)

        communicator2, connected2, _ = await self.connect(token=self.access_token2)
        self.assertTrue(connected2)

        response_create = await sync_to_async(
            self.create_attachment_message_through_http
        )()
        self.assertEqual(response_create.status_code, 201)

        # Receive my message
        for communicator in [communicator1, communicator2]:
            response = await communicator.receive_json_from()
            self.assertEqual(response["message"]["content"], "Test Attachment Message")
            self.assertEqual(response["message"]["sender"]["id"], self.user1.id)
        parent_message_id = response["message"]["id"]

        # Receives will read message
        message_content = WILL_READ_MESSAGE
        for communicator in [communicator1, communicator2]:
            response = await communicator.receive_json_from()
            self.assertEqual(response["chatroom_id"], self.chatroom_id)
            self.assertEqual(response["message"]["content"], message_content)
            self.assertEqual(response["message"]["sender"]["id"], self.pico_user.id)

        # Receives no text message
        message_content = NO_TEXT_IN_FILE_MESSAGE
        for communicator in [communicator1, communicator2]:
            response = await communicator.receive_json_from()
            self.assertEqual(response["chatroom_id"], self.chatroom_id)
            self.assertEqual(response["message"]["content"], message_content)
            self.assertEqual(response["message"]["sender"]["id"], self.pico_user.id)

        # user 2 says something in the thread
        message_content = "Test Thread Message"
        await communicator2.send_json_to(
            {
                "chatroom_id": self.chatroom_id,
                "parent_message_id": parent_message_id,
                "message": message_content,
            }
        )

        # Receive user 2 message
        for communicator in [communicator1, communicator2]:
            response = await communicator.receive_json_from()
            self.assertEqual(response["message"]["content"], message_content)
            self.assertEqual(response["message"]["sender"]["id"], self.user2.id)
            self.assertEqual(
                response["message"]["parent_message"]["id"], parent_message_id
            )

        # Test list messages (tested here and not in test_message_views because thread_messages can only be created through websockets)
        response = await sync_to_async(self.list_messages_through_http)()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 3)
        self.assertEqual(response.json()[0]["id"], parent_message_id)
        self.assertEqual(len(response.json()[0]["thread_messages"]), 1)
        self.assertEqual(
            response.json()[0]["thread_messages"][0]["content"], message_content
        )
        self.assertEqual(
            response.json()[0]["thread_messages"][0]["sender"]["id"], self.user2.id
        )

        await communicator1.disconnect()
        await communicator2.disconnect()

    def add_member_through_http(self, username):
        url = reverse(
            "api:chatroom_add_member", kwargs={"chatroom_id": self.chatroom.pk}
        )
        data = {"username": username}
        return self.client.patch(url, data, content_type="application/json")

    def remove_member_through_http(self, username):
        url = reverse(
            "api:chatroom_remove_member", kwargs={"chatroom_id": self.chatroom.pk}
        )
        data = {"username": username}
        return self.client.patch(url, data, content_type="application/json")

    async def test_undelivered_notifications(self):
        communicator1, connected1, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected1)

        communicator2, connected2, _ = await self.connect(token=self.access_token2)
        self.assertTrue(connected2)

        # user 2 disconnects
        await communicator2.disconnect()

        # user 1 sends a message
        messages = ["hello world!", "how are you?", "let's meet tomorrow"]
        for message_content in messages:
            await communicator1.send_json_to(
                {"chatroom_id": self.chatroom_id, "message": message_content}
            )
            await communicator1.receive_json_from()  # Synchronization

        # user 2 is removed, triggering remove_member notification
        response = await sync_to_async(self.remove_member_through_http)(
            username=self.user2.username
        )
        self.assertEqual(response.status_code, 200)

        # Message is sent (should not turn into notification because user 2 is not member)
        message_content = "hello universe!"
        await communicator1.send_json_to(
            {"chatroom_id": self.chatroom_id, "message": message_content}
        )

        await communicator1.receive_json_from()  # explicitly synchronizing

        # user 2 is added to the chatroom, triggering add_member notification
        response = await sync_to_async(self.add_member_through_http)(
            username=self.user2.username
        )
        self.assertEqual(response.status_code, 200)

        # user 2 reconnects
        communicator2, connected2, _ = await self.connect(token=self.access_token2)
        self.assertTrue(connected2)

        # user 2 receives the undelivered notifications
        for message_content in messages:
            response = await communicator2.receive_json_from()
            self.assertEqual(response["type"], "notification.message")
            self.assertEqual(response["message"]["content"], message_content)
            self.assertEqual(response["message"]["sender"]["id"], self.user1.id)

        response = await communicator2.receive_json_from()
        self.assertEqual(response["type"], "notification.remove_member")
        self.assertEqual(
            response["removed_by_user"]["id"],
            self.user1.id,
        )
        self.assertEqual(response["removed_user"]["id"], self.user2.id)

        response = await communicator2.receive_json_from()
        self.assertEqual(response["type"], "notification.message")  # system message
        self.assertEqual(response["message"]["sender"]["id"], self.system_user.id)
        self.assertEqual(
            response["message"]["content"],
            f"User {self.user1.username} removed user {self.user2.username}",
        )

        response = await communicator2.receive_json_from()
        self.assertEqual(response["type"], "notification.add_member")
        self.assertEqual(
            response["added_by_user"]["id"],
            self.user1.id,
        )
        self.assertEqual(response["added_user"]["id"], self.user2.id)

        response = await communicator2.receive_json_from()
        self.assertEqual(response["type"], "notification.message")  # system message
        self.assertEqual(response["message"]["sender"]["id"], self.system_user.id)
        self.assertEqual(
            response["message"]["content"],
            f"User {self.user1.username} added user {self.user2.username}",
        )

        await communicator1.disconnect()
        await communicator2.disconnect()

    def get_online_info_through_http(self):
        url = reverse("api:user_online_info")
        data = {"user_ids": [self.user1.pk, self.user2.pk]}
        return self.client.post(url, data, content_type="application/json")

    async def test_get_online_info(self):
        # check everyone is offline
        response = await sync_to_async(self.get_online_info_through_http)()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["id"], self.user1.pk)
        self.assertEqual(response.json()[0]["is_online"], False)
        self.assertIsNone(response.json()[0]["last_online"])
        self.assertEqual(response.json()[1]["id"], self.user2.pk)
        self.assertEqual(response.json()[1]["is_online"], False)
        self.assertIsNone(response.json()[1]["last_online"])

        # user 1 connects
        communicator1, connected1, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected1)

        # check user 1 is online and user 2 is offline
        response = await sync_to_async(self.get_online_info_through_http)()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["id"], self.user1.pk)
        self.assertEqual(response.json()[0]["is_online"], True)
        self.assertIsNone(response.json()[0]["last_online"])
        self.assertEqual(response.json()[1]["id"], self.user2.pk)
        self.assertEqual(response.json()[1]["is_online"], False)
        self.assertIsNone(response.json()[1]["last_online"])

        # user 1 disconnects
        await communicator1.disconnect()

        # check everyone is offline
        response = await sync_to_async(self.get_online_info_through_http)()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["id"], self.user1.pk)
        self.assertEqual(response.json()[0]["is_online"], False)
        # assert that its a timestamp
        self.assertIsInstance(response.json()[0]["last_online"], str)
        self.assertEqual(response.json()[1]["id"], self.user2.pk)
        self.assertEqual(response.json()[1]["is_online"], False)
        self.assertIsNone(response.json()[1]["last_online"])
