from unittest.mock import MagicMock, patch

import api.services.message_service as message_service
from api.models import EmbeddedFile, Message
from api.tests.factories import (
    GroupChatroomFactory,
    MembershipFactory,
    MessageFactory,
    UserFactory,
)
from api.tests.utils import create_simple_uploaded_file
from shared.testing import PatchingAndRedisTestCase


class MessageServiceTestCase(PatchingAndRedisTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user = UserFactory.create()
        cls.chatroom = GroupChatroomFactory.create()
        cls.messages = MessageFactory.create_batch(
            3, chatroom=cls.chatroom, sender=cls.user
        )

        MembershipFactory.create(user=cls.user, chatroom=cls.chatroom)

    def setUp(self):
        super().setUp()
        self.addCleanup(patch.stopall)

        self.mock_notification_batch = MagicMock(
            spec=message_service.notifications_utils.NotificationBatch
        )
        self.mock_prepare_messages_notifications = patch(
            "api.services.message_service.notifications_utils.prepare_messages_notifications",
        ).start()
        self.mock_prepare_messages_notifications.return_value = (
            self.mock_notification_batch
        )

        self.mock_process_file_async_workflow = patch(
            "api.file_tasks.process_file_async_workflow",
            autospec=True,
        ).start()
        self.mock_process_file_sync_workflow = patch(
            "api.file_tasks.process_file_sync_workflow",
            autospec=True,
        ).start()
        self.mock_task_add_embedding_to_message = patch(
            "api.message_tasks.task_add_embedding_to_message",
            autospec=True,
        ).start()
        self.mock_task_bulk_embed_messages = patch(
            "api.message_tasks.task_bulk_embed_messages",
            autospec=True,
        ).start()

    async def test_list_top_level_messages_for_chatroom(self):
        messages = await message_service.list_top_level_messages_for_chatroom(
            self.chatroom
        )
        self.assertEqual(len(messages), 3)

    async def test_get_top_level_message(self):
        message = await message_service.aget_top_level_message(
            self.messages[0].id, self.chatroom
        )
        self.assertEqual(message, self.messages[0])

    async def test_create_and_send_message_with_valid_pdf(self):
        file = create_simple_uploaded_file(
            "pico_django/api/tests/test_files/test_pdf.pdf",
            "test_pdf.pdf",
            "application/pdf",
        )
        message = await message_service.create_and_send_message(
            sender=self.user,
            chatroom=self.chatroom,
            content="Test message",
            attachment=file,
        )

        self.assertEqual(self.mock_prepare_messages_notifications.call_count, 2)

        self.assertEqual(self.mock_notification_batch.send_async.await_count, 2)

        embedded_file = await EmbeddedFile.objects.aget(messages=message)

        self.mock_process_file_async_workflow.assert_awaited_once_with(
            embedded_file.id, True
        )

        message = (
            await Message.objects.select_related("sender", "chatroom", "parent_message")
            .prefetch_related("thread_messages")
            .aget(id=message.id)
        )  # this is just to ease checking below, ideally we would just use the object returned by create_and_send_message

        self.assertIsInstance(message, Message)
        self.assertEqual(message.content, "Test message")
        self.assertEqual(message.sender, self.user)
        self.assertEqual(message.chatroom, self.chatroom)
        self.assertTrue(await message.embedded_files.aexists())
        self.assertRegex(
            (await message.embedded_files.afirst()).file.name, r"test_pdf\w*\.pdf"
        )
        self.assertIsNone(message.parent_message)
        self.assertEqual(await message.thread_messages.acount(), 0)

    async def test_create_and_send_message_with_invalid_content_type(self):
        file = create_simple_uploaded_file(
            "pico_django/api/tests/test_files/test_pdf.pdf",
            "test_pdf.pdf",
            "application/octet-stream",
        )
        with self.assertRaises(message_service.InvalidContentTypeError):
            await message_service.create_and_send_message(
                sender=self.user,
                chatroom=self.chatroom,
                content="Test message invalid content type",
                attachment=file,
            )
        self.assertFalse(
            await Message.objects.filter(
                content="Test message invalid content type"
            ).aexists()
        )

    async def test_create_and_send_message_with_invalid_mime_type(self):
        file = create_simple_uploaded_file(
            "pico_django/api/tests/test_files/sh_exec_with_photo_extension.png",
            "sh_exec_with_photo_extension.png",
            "image/png",
        )
        with self.assertRaises(message_service.InvalidMIMETypeError):
            await message_service.create_and_send_message(
                sender=self.user,
                chatroom=self.chatroom,
                content="Test message invalid mime type",
                attachment=file,
            )

        self.assertFalse(
            await Message.objects.filter(
                content="Test message invalid mime type"
            ).aexists()
        )

    def test_send_message_with_embedding(self):
        message = message_service.send_message(
            sender=self.user,
            chatroom=self.chatroom,
            content="Test user message",
        )
        self.mock_prepare_messages_notifications.assert_called_once_with([message])

        self.mock_notification_batch.send_sync.assert_called_once()

        self.mock_task_add_embedding_to_message.s.assert_called_once_with(
            message.id, "Test user message"
        )
        self.assertTrue(Message.objects.filter(content="Test user message").exists())

    def test_send_message_without_embedding(self):
        message = message_service.send_message(
            sender=self.user,
            chatroom=self.chatroom,
            content="Test user message",
            have_embedding=False,
        )
        self.mock_prepare_messages_notifications.assert_called_once_with([message])

        self.mock_notification_batch.send_sync.assert_called_once()

        self.mock_task_add_embedding_to_message.s.assert_not_called()

        self.assertTrue(Message.objects.filter(content="Test user message").exists())

    async def test_asend_message(self):
        message = await message_service.asend_message(
            sender=self.user,
            chatroom=self.chatroom,
            content="Test user message",
        )
        self.mock_prepare_messages_notifications.assert_called_once_with([message])

        self.mock_notification_batch.send_async.assert_awaited_once()

        self.mock_task_add_embedding_to_message.s.assert_called_once_with(
            message.id, "Test user message"
        )
        self.assertTrue(
            await Message.objects.filter(content="Test user message").aexists()
        )

    async def test_asend_message_without_embedding(self):
        message = await message_service.asend_message(
            sender=self.user,
            chatroom=self.chatroom,
            content="Test user message",
            have_embedding=False,
        )
        self.mock_prepare_messages_notifications.assert_called_once_with([message])

        self.mock_notification_batch.send_async.assert_awaited_once()

        self.mock_task_add_embedding_to_message.s.assert_not_called()

        self.assertTrue(
            await Message.objects.filter(content="Test user message").aexists()
        )

    def test_send_many_messages(self):
        contents = [f"Test pico message {i}" for i in range(10)]
        messages = message_service.send(
            [
                message_service.MessageContext(
                    chatroom=self.chatroom,
                    content=content,
                    sender=self.user,
                    have_embedding=True,
                )
                for content in contents
            ]
        )
        self.assertEqual(len(messages), 10)
        for i, message in enumerate(messages):
            self.assertEqual(message.content, contents[i])

        self.mock_task_bulk_embed_messages.delay.assert_called_once_with(
            [message.id for message in messages]
        )

    def test_send_message_sender_username(self):
        message = message_service.send_message(
            sender=self.user.username,
            chatroom=self.chatroom,
            content="Test user message",
        )
        self.assertEqual(message.sender, self.user)

    def test_send_messsage_sender_pico(self):
        message = message_service.send_message(
            sender="pico",
            chatroom=self.chatroom,
            content="Test user message",
        )
        self.assertEqual(message.sender.username, "pico")
