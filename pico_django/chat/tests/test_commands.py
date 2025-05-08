"""in order to help with explicitly synchronizing the async things that the test methods do,
do something to wait for a response from the server, such as communicator.receive_json_from()
after sending json, for example.
Test with wifi turned off to ensure no external api calls are being made."""

import logging
import sys
from unittest.mock import MagicMock

import api.services.file_service as message_service
import quiz.question_service as question_service
from api.models import EmbeddedFile, FileGroup, Message
from api.tests.factories import GroupChatroomFactory, UserFactory
from api.tests.utils import create_simple_uploaded_file
from asgiref.sync import sync_to_async
from commands.commands_utils.command_handlers.core import (
    CHAT_MODEL,
    DEFAULT_TEMPERATURE,
)
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from pico_backend.asgi import application
from pico_backend.auth import generate_tokens
from shared.testing import PatchingAndRedisTestCase

sys.modules["channels.testing.live"] = MagicMock()
logger = logging.getLogger(__name__)

User = get_user_model()


class CommandsTestCase(PatchingAndRedisTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user1 = UserFactory.create()
        cls.member1 = UserFactory.create()
        cls.member2 = UserFactory.create()

        cls.pico_user = User.objects.get_pico_user()

        cls.access_token1, _ = generate_tokens(cls.user1)

        cls.auth_headers = {"Authorization": f"Bearer {cls.access_token1}"}

        cls.chatroom = GroupChatroomFactory.create()
        cls.chatroom.add_member(cls.user1, admin=True)
        cls.chatroom_id = cls.chatroom.pk

    def setUp(self):
        super().setUp()

        self.client = Client(headers=self.auth_headers)

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

    def get_ws_url(self, token=None):
        return f"/ws/notifications?token={token}" if token else "/ws/notifications"

    def create_attachment_message_through_http(self):
        file = create_simple_uploaded_file(
            "pico_django/api/tests/test_files/test_photo.png",
            "test_photo.png",
            "image/png",
        )
        data = {"content": "Test Photo Message", "upload": file}
        url = reverse(
            "api:chatroom_message_list",
            kwargs={"chatroom_id": self.chatroom.pk},
        )

        return self.client.post(url, data)

    def create_pdf_message_through_http(self):
        file = create_simple_uploaded_file(
            "pico_django/api/tests/test_files/test_pdf.pdf",
            "test_pdf.pdf",
            "application/pdf",
        )
        data = {"content": "Test PDF Message", "upload": file}
        url = reverse(
            "api:chatroom_message_list",
            kwargs={"chatroom_id": self.chatroom.pk},
        )

        return self.client.post(url, data)

    async def test_files_command(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        # create 3 messages with attachments
        for _ in range(3):
            await sync_to_async(self.create_attachment_message_through_http)()

            # Receive my message back
            await communicator.receive_json_from()

            # Receive will read message
            await communicator.receive_json_from()

            # Receive no text message
            await communicator.receive_json_from()

        # Send a message to the chatroom
        message_content = "/files"
        await communicator.send_json_to(
            {"chatroom_id": self.chatroom_id, "message": message_content}
        )
        # Receive my message back
        response = await communicator.receive_json_from()
        self.assertEqual(response["message"]["content"], "/files")
        self.assertEqual(response["message"]["sender"]["id"], self.user1.id)

        # Receive a message from the chatbot
        response = await communicator.receive_json_from()

        self.assertEqual(response["chatroom_id"], self.chatroom_id)

        for line in response["message"]["content"].split("\n"):
            self.assertRegex(line, r"\d+\. test_photo\w*\.png")

        await communicator.disconnect()

    async def test_help_command(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        # Send a message to the chatroom
        message_content = "/help"
        await communicator.send_json_to(
            {"chatroom_id": self.chatroom_id, "message": message_content}
        )

        # Receive my message back
        response = await communicator.receive_json_from()
        # Verificar que a mensagem que você enviou foi recebida corretamente
        self.assertEqual(response["message"]["content"], "/help")
        self.assertEqual(response["message"]["sender"]["id"], self.user1.id)

        # Receive a message from the chatbot
        response = await communicator.receive_json_from()
        # Não verificar o conteúdo exato, apenas que veio do chatbot
        self.assertEqual(response["chatroom_id"], self.chatroom_id)
        self.assertEqual(response["message"]["sender"]["id"], self.pico_user.id)
        self.assertEqual(
            response["message"]["sender"]["username"], self.pico_user.username
        )
        # Opcionalmente, você pode verificar se a resposta contém certas palavras-chave
        # self.assertIn("ajuda", response["message"]["content"].lower())

        await communicator.disconnect()

    async def test_pico_command(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        message = await Message.objects.acreate(
            sender=self.user1,
            chatroom=self.chatroom,
            content="First attachment message",
        )
        file = create_simple_uploaded_file(
            "pico_django/api/tests/test_files/test_pdf.pdf",
            "test_pdf.pdf",
            "application/pdf",
        )
        embedded_file = await EmbeddedFile.objects.acreate(
            file=file,
        )
        await embedded_file.messages.aadd(message)

        await sync_to_async(message_service.handle_global_file)(
            embedded_file.id, embedded_file.file
        )

        response = await communicator.receive_json_from()

        # send a message to the chatroom
        message_content = "old message to serve as context"
        await communicator.send_json_to(
            {"chatroom_id": self.chatroom_id, "message": message_content}
        )
        response = await communicator.receive_json_from()
        self.assertEqual(response["message"]["content"], message_content)
        self.assertEqual(response["message"]["sender"]["id"], self.user1.id)

        # Send a message to the chatroom
        message_content = "/pico hey Pico!"
        await communicator.send_json_to(
            {"chatroom_id": self.chatroom_id, "message": message_content}
        )
        # Receive my message back
        response = await communicator.receive_json_from()
        self.assertEqual(response["message"]["content"], message_content)
        self.assertEqual(response["message"]["sender"]["id"], self.user1.id)

        # Receive a message from the chatbot
        response = await communicator.receive_json_from()

        self.assertEqual(response["chatroom_id"], self.chatroom_id)
        self.assertEqual(response["message"]["sender"]["id"], self.pico_user.id)
        self.assertEqual(
            response["message"]["sender"]["username"], self.pico_user.username
        )
        mock_id_like = f"mock_{CHAT_MODEL}_{DEFAULT_TEMPERATURE}_"
        self.assertRegex(
            response["message"]["content"],
            f"Mocked response for {mock_id_like}",
        )

        await communicator.disconnect()

    async def test_file_context_commands_in_thread(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)
        # create a message with an attachment
        response = await sync_to_async(self.create_pdf_message_through_http)()

        # Receive my message back
        await communicator.receive_json_from(timeout=3)

        # Receive processing attachment
        await communicator.receive_json_from(timeout=3)

        # Receive finished processing
        await communicator.receive_json_from(timeout=3)

        for command in ["/file_ask"]:
            with self.subTest(command):
                # Send file context command
                message_content = f"{command} what is this?"
                await communicator.send_json_to(
                    {
                        "chatroom_id": self.chatroom_id,
                        "message": message_content,
                        "parent_message_id": response.json()["id"],
                    }
                )

                # Receive my message back
                response = await communicator.receive_json_from()
                self.assertEqual(response["message"]["content"], message_content)
                self.assertEqual(response["message"]["sender"]["id"], self.user1.id)

                # Receive a message from the chatbot
                response = await communicator.receive_json_from()

                self.assertEqual(response["chatroom_id"], self.chatroom_id)
                self.assertEqual(response["message"]["sender"]["id"], self.pico_user.id)
                self.assertEqual(
                    response["message"]["sender"]["username"], self.pico_user.username
                )
                mock_id_like = f"mock_{CHAT_MODEL}_{DEFAULT_TEMPERATURE}_"
                self.assertRegex(
                    response["message"]["content"],
                    f"Mocked response for {mock_id_like}",
                )

        await communicator.disconnect()

    async def test_file_context_commands_in_main_chat(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)
        # create a message with an attachment
        response = await sync_to_async(self.create_pdf_message_through_http)()

        # Receive my message back
        await communicator.receive_json_from()

        # Receive processing attachment
        await communicator.receive_json_from()

        # Receive finished processing
        await communicator.receive_json_from()

        for command in ["/file_ask"]:
            with self.subTest(command):
                # Send file context command
                message_content = f"{command} # 1 what is this?"
                await communicator.send_json_to(
                    {
                        "chatroom_id": self.chatroom_id,
                        "message": message_content,
                    }
                )

                # Receive my message back
                response = await communicator.receive_json_from()
                self.assertEqual(response["message"]["content"], message_content)
                self.assertEqual(response["message"]["sender"]["id"], self.user1.id)

                # Receive a message from the chatbot
                response = await communicator.receive_json_from()

                self.assertEqual(response["chatroom_id"], self.chatroom_id)
                self.assertEqual(response["message"]["sender"]["id"], self.pico_user.id)
                self.assertEqual(
                    response["message"]["sender"]["username"], self.pico_user.username
                )
                mock_id_like = f"mock_{CHAT_MODEL}_{DEFAULT_TEMPERATURE}_"
                self.assertRegex(
                    response["message"]["content"],
                    f"Mocked response for {mock_id_like}",
                )

        await communicator.disconnect()

    async def test_file_group_context_commands_in_main_chat(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        file = create_simple_uploaded_file(
            "pico_django/api/tests/test_files/test_pdf.pdf",
            "test_pdf.pdf",
            "application/pdf",
        )
        file_group = await FileGroup.objects.acreate(
            name="test",
        )
        embedded_file = await EmbeddedFile.objects.acreate(
            file=file,
            name="test_pdf",
            file_group=file_group,
        )

        await sync_to_async(message_service.handle_global_file)(
            embedded_file.id, embedded_file.file
        )

        for command in ["/files_ask"]:
            with self.subTest(command):
                # Send file context command
                message_content = f"{command} test what is this?"
                await communicator.send_json_to(
                    {
                        "chatroom_id": self.chatroom_id,
                        "message": message_content,
                    }
                )

                # Receive my message back
                response = await communicator.receive_json_from()
                self.assertEqual(response["message"]["content"], message_content)
                self.assertEqual(response["message"]["sender"]["id"], self.user1.id)

                # Receive a message from the chatbot
                response = await communicator.receive_json_from()

                self.assertEqual(response["chatroom_id"], self.chatroom_id)
                self.assertEqual(response["message"]["sender"]["id"], self.pico_user.id)
                self.assertEqual(
                    response["message"]["sender"]["username"], self.pico_user.username
                )
                mock_id_like = f"mock_{CHAT_MODEL}_{DEFAULT_TEMPERATURE}_"
                self.assertRegex(
                    response["message"]["content"],
                    f"Mocked response for {mock_id_like}",
                )

        await communicator.disconnect()

    async def test_quiz_command(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        await sync_to_async(question_service.create_questions)(
            [
                "Qual é a raiz quadrada de 4?",
                "Qual é a raiz quadrada de 9?",
                "Qual é a raiz quadrada de 16?",
            ],
            ["2", "3", "4"],
        )

        # Send a message to the chatroom
        message_content = "/quiz matematica basica"
        await communicator.send_json_to(
            {"chatroom_id": self.chatroom_id, "message": message_content}
        )

        # Receive my message back
        response = await communicator.receive_json_from()
        self.assertEqual(response["message"]["content"], "/quiz matematica basica")
        self.assertEqual(response["message"]["sender"]["id"], self.user1.id)

        # Receive a message from the chatbot
        response = await communicator.receive_json_from()
        # Não verificar o conteúdo exato, apenas que veio do chatbot e tem um anexo
        self.assertEqual(response["chatroom_id"], self.chatroom_id)
        self.assertEqual(response["message"]["sender"]["id"], self.pico_user.id)
        self.assertEqual(
            response["message"]["sender"]["username"], self.pico_user.username
        )
        self.assertIsNotNone(response["message"]["attachment"])
        # Opcionalmente, você pode verificar se a resposta contém certas palavras-chave
        # self.assertIn("quiz", response["message"]["content"].lower())

        await communicator.disconnect()

    """ async def test_pico_command(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        # Send a message to the chatroom
        message_content = "/pico hey Pico!"
        await communicator.send_json_to(
            {"chatroom_id": self.chatroom_id, "message": message_content}
        )
        # Receive my message back
        response = await communicator.receive_json_from()
        self.assertEqual(response["message"]["content"], "/pico hey Pico!")
        self.assertEqual(response["message"]["sender"]["id"], self.user1.id)

        # Receive a message from the chatbot
        response = await communicator.receive_json_from()

        self.assertEqual(response["chatroom_id"], self.chatroom_id)
        self.assertEqual(response["message"]["sender"]["id"], self.pico_user.id)
        self.assertEqual(
            response["message"]["sender"]["username"], self.pico_user.username
        )
        self.assertEqual(response["message"]["content"], "Mocked response from OpenAI completions create")

        await communicator.disconnect()

    async def test_search_command(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        # create dummy messages for searching
        message_contents = [
            "i love bananas",
            "my car is green",
            "i love apples",
            "i am a doctor",
            "altruism is great",
            "Em português essa mensagem",
            "Deutsch is gut",
            "Ich esse einen Apfel",
        ]

        embeddings = (
            await commands.commands_utils.embeddings._acall_openai_embeddings_create(
                EMBEDDING_MODEL, message_contents
            )
        )

        self.assertEqual(len(embeddings), len(message_contents))

        messages_with_embeddings = [
            Message(
                sender=self.user1,
                chatroom=self.chatroom,
                content=content,
                embedding=embedding,
            )
            for content, embedding in zip(message_contents, embeddings)
        ]

        await Message.objects.abulk_create(messages_with_embeddings)

        # Send a message to the chatroom
        message_content = "/search when i ate fruits"
        await communicator.send_json_to(
            {"chatroom_id": self.chatroom_id, "message": message_content}
        )

        # Receive my message back
        response = await communicator.receive_json_from()
        self.assertEqual(response["message"]["content"], "/search when i ate fruits")
        self.assertEqual(response["message"]["sender"]["id"], self.user1.id)

        # Receive a message from the chatbot
        response = await communicator.receive_json_from()

        self.assertEqual(response["chatroom_id"], self.chatroom_id)
        self.assertEqual(response["message"]["sender"]["id"], self.pico_user.id)
        self.assertEqual(
            response["message"]["sender"]["username"], self.pico_user.username
        )

        await communicator.disconnect()

    async def test_pico_roadmap_command(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        # Send a message to the chatroom
        message_content = "/pico_roadmap backend developer"
        await communicator.send_json_to(
            {"chatroom_id": self.chatroom_id, "message": message_content}
        )

        # Receive my message back
        response = await communicator.receive_json_from()
        self.assertEqual(
            response["message"]["content"], "/pico_roadmap backend developer"
        )
        self.assertEqual(response["message"]["sender"]["id"], self.user1.id)

        # Receive a message from the chatbot
        response = await communicator.receive_json_from()

        self.assertEqual(response["chatroom_id"], self.chatroom_id)
        self.assertEqual(response["message"]["content"], "Mocked response from OpenAI completions create")
        self.assertEqual(response["message"]["sender"]["id"], self.pico_user.id)
        self.assertEqual(
            response["message"]["sender"]["username"], self.pico_user.username
        )

        await communicator.disconnect()

    async def test_ask_command(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        # create dummy messages for searching
        message_contents = [
            "i love bananas",
            "my car is green",
            "i love apples",
            "i am a doctor",
            "altruism is great",
            "Em português essa mensagem",
            "Deutsch is gut",
            "Ich esse einen Apfel",
        ]

        embeddings = (
            await commands.commands_utils.embeddings._acall_openai_embeddings_create(
                EMBEDDING_MODEL, message_contents
            )
        )

        self.assertEqual(len(embeddings), len(message_contents))

        messages_with_embeddings = [
            Message(
                sender=self.user1,
                chatroom=self.chatroom,
                content=content,
                embedding=embedding,
            )
            for content, embedding in zip(message_contents, embeddings)
        ]

        await Message.objects.abulk_create(messages_with_embeddings)

        # Send a message to the chatroom
        message_content = "/ask what are my favorite fruits?"
        await communicator.send_json_to(
            {"chatroom_id": self.chatroom_id, "message": message_content}
        )

        # Receive my message back
        response = await communicator.receive_json_from()
        self.assertEqual(
            response["message"]["content"], "/ask what are my favorite fruits?"
        )
        self.assertEqual(response["message"]["sender"]["id"], self.user1.id)

        # Receive a message from the chatbot
        response = await communicator.receive_json_from()

        self.assertEqual(response["chatroom_id"], self.chatroom_id)
        self.assertEqual(response["message"]["sender"]["id"], self.pico_user.id)
        self.assertEqual(
            response["message"]["sender"]["username"], self.pico_user.username
        )

        await communicator.disconnect()

    async def test_file_search_command(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        # create a message with an attachment
        response = await sync_to_async(self.create_pdf_message_through_http)()

        # Receive my message back
        await communicator.receive_json_from()

        # Receive processing pdf
        await communicator.receive_json_from()

        # Receive finished processing
        await communicator.receive_json_from()

        # Send file search command
        message_content = "/file_search the middle ages started to decline"
        await communicator.send_json_to(
            {
                "chatroom_id": self.chatroom_id,
                "message": message_content,
                "parent_message_id": response.json()["id"],
            }
        )

        # Receive my message back
        response = await communicator.receive_json_from()
        self.assertEqual(
            response["message"]["content"],
            "/file_search the middle ages started to decline",
        )
        self.assertEqual(response["message"]["sender"]["id"], self.user1.id)

        # Receive a message from the chatbot
        response = await communicator.receive_json_from()

        self.assertEqual(response["chatroom_id"], self.chatroom_id)
        self.assertEqual(response["message"]["sender"]["id"], self.pico_user.id)
        self.assertEqual(
            response["message"]["sender"]["username"], self.pico_user.username
        )

        await communicator.disconnect()

    async def test_file_search_command_not_processed(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        # create a message with an attachment
        response = await sync_to_async(self.create_attachment_message_through_http)()

        # Receive my message back
        await communicator.receive_json_from()

        # Send file search command
        message_content = "/file_search the middle ages started to decline"
        await communicator.send_json_to(
            {
                "chatroom_id": self.chatroom_id,
                "message": message_content,
                "parent_message_id": response.json()["id"],
            }
        )

        # Receive my message back
        response = await communicator.receive_json_from()
        self.assertEqual(
            response["message"]["content"],
            "/file_search the middle ages started to decline",
        )
        self.assertEqual(response["message"]["sender"]["id"], self.user1.id)

        # Receive a message from the chatbot
        response = await communicator.receive_json_from()

        self.assertEqual(response["chatroom_id"], self.chatroom_id)
        self.assertEqual(response["message"]["sender"]["id"], self.pico_user.id)
        self.assertEqual(
            response["message"]["sender"]["username"], self.pico_user.username
        )
        self.assertEqual(response["message"]["content"], FILE_NOT_READY_MESSAGE)

        await communicator.disconnect()

    async def test_file_search_command_in_main_chat(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        for _ in range(2):
            response = await sync_to_async(self.create_pdf_message_through_http)()

            # Receive my message back
            await communicator.receive_json_from()

            # Receive processing pdf
            await communicator.receive_json_from()

            # Receive finished processing
            await communicator.receive_json_from(timeout=3)

        # Send file search command
        message_content = "/file_search # 2 the middle ages started to decline"
        await communicator.send_json_to(
            {
                "chatroom_id": self.chatroom_id,
                "message": message_content,
            }
        )

        # Receive my message back
        response = await communicator.receive_json_from()
        self.assertEqual(
            response["message"]["content"],
            "/file_search # 2 the middle ages started to decline",
        )
        self.assertEqual(response["message"]["sender"]["id"], self.user1.id)

        # Receive a message from the chatbot
        response = await communicator.receive_json_from()

        self.assertEqual(response["chatroom_id"], self.chatroom_id)
        self.assertEqual(response["message"]["sender"]["id"], self.pico_user.id)
        self.assertEqual(
            response["message"]["sender"]["username"], self.pico_user.username
        )
        self.assertTrue(
            response["message"]["content"].startswith(
                "Resultados da pesquisa por 'the middle ages started to decline' no arquivo:"
            )
        )

        await communicator.disconnect()

    async def test_file_search_command_in_main_chat_no_arg1(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        # Send file search command
        message_content = "/file_search the middle ages started to decline"
        await communicator.send_json_to(
            {
                "chatroom_id": self.chatroom_id,
                "message": message_content,
            }
        )

        # Receive my message back
        response = await communicator.receive_json_from()
        self.assertEqual(
            response["message"]["content"],
            "/file_search the middle ages started to decline",
        )
        self.assertEqual(response["message"]["sender"]["id"], self.user1.id)

        # Receive a message from the chatbot
        response = await communicator.receive_json_from()

        self.assertEqual(response["message"]["content"], FILE_NOT_FOUND_MESSAGE)

        await communicator.disconnect()

    async def test_file_search_command_in_main_chat_bad_arg1(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        # Send file search command
        message_content = "/file_search # a the middle ages started to decline"
        await communicator.send_json_to(
            {
                "chatroom_id": self.chatroom_id,
                "message": message_content,
            }
        )

        # Receive my message back
        response = await communicator.receive_json_from()
        self.assertEqual(
            response["message"]["content"],
            "/file_search # a the middle ages started to decline",
        )
        self.assertEqual(response["message"]["sender"]["id"], self.user1.id)

        # Receive a message from the chatbot
        response = await communicator.receive_json_from()

        self.assertEqual(response["message"]["content"], FILE_NOT_FOUND_MESSAGE)

        await communicator.disconnect()

    async def test_file_search_command_in_main_chat_no_arg2(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        # Send file search command
        message_content = "/file_search # 1"
        await communicator.send_json_to(
            {
                "chatroom_id": self.chatroom_id,
                "message": message_content,
            }
        )

        # Receive my message back
        response = await communicator.receive_json_from()
        self.assertEqual(
            response["message"]["content"],
            message_content,
        )
        self.assertEqual(response["message"]["sender"]["id"], self.user1.id)

        # Receive a message from the chatbot
        response = await communicator.receive_json_from()

        self.assertEqual(
            response["message"]["content"],
            FILE_NOT_FOUND_MESSAGE,
        )

        await communicator.disconnect()

    def create_big_pdf_message_through_http(self):
        with open("pico_django/api/tests/test_files/big_pdf.pdf", "rb") as file:
            file = SimpleUploadedFile(
                "big_pdf.pdf", file.read(), content_type="application/pdf"
            )
        data = {"content": "Big PDF Message", "upload": file}
        url = reverse(
            "api:chatroom_message_list",
            kwargs={"chatroom_id": self.chatroom.pk},
        )

        return self.client.post(url, data)

    async def test_file_search_command_big_file(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        # create a big message with an attachment
        response = await sync_to_async(self.create_big_pdf_message_through_http)()

        # Receive my message back
        await communicator.receive_json_from()

        # Receive processing pdf
        await communicator.receive_json_from()

        # Receive finished processing
        await communicator.receive_json_from(timeout=10)

        # Send file search command
        message_content = "/file_search sapientia fugit"
        await communicator.send_json_to(
            {
                "chatroom_id": self.chatroom_id,
                "message": message_content,
                "parent_message_id": response.json()["id"],
            }
        )

        # Receive my message back
        response = await communicator.receive_json_from()
        self.assertEqual(
            response["message"]["content"],
            message_content,
        )
        self.assertEqual(response["message"]["sender"]["id"], self.user1.id)

        # Receive a message from the chatbot
        response = await communicator.receive_json_from()

        self.assertEqual(response["chatroom_id"], self.chatroom_id)
        self.assertEqual(response["message"]["sender"]["id"], self.pico_user.id)
        self.assertEqual(
            response["message"]["sender"]["username"], self.pico_user.username
        )
        self.assertTrue(
            response["message"]["content"].startswith(
                "Resultados da pesquisa por 'sapientia fugit' no arquivo:"
            )
        )

        await communicator.disconnect()

    async def test_file_ask_command(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        # create a message with an attachment
        response = await sync_to_async(self.create_pdf_message_through_http)()

        # Receive my message back
        await communicator.receive_json_from()

        # Receive processing pdf
        await communicator.receive_json_from()

        # Receive finished processing
        await communicator.receive_json_from(timeout=3)

        # Send ask file command
        message_content = "/file_ask what is the middle ages"
        await communicator.send_json_to(
            {
                "chatroom_id": self.chatroom_id,
                "message": message_content,
                "parent_message_id": response.json()["id"],
            }
        )

        # Receive my message back
        response = await communicator.receive_json_from()
        self.assertEqual(
            response["message"]["content"], "/file_ask what is the middle ages"
        )
        self.assertEqual(response["message"]["sender"]["id"], self.user1.id)

        # Receive a message from the chatbot
        response = await communicator.receive_json_from()

        self.assertEqual(response["chatroom_id"], self.chatroom_id)
        self.assertEqual(response["message"]["sender"]["id"], self.pico_user.id)
        self.assertEqual(
            response["message"]["sender"]["username"], self.pico_user.username
        )

        await communicator.disconnect()

    async def test_file_ask_command_in_main_chat(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        for _ in range(2):
            response = await sync_to_async(self.create_pdf_message_through_http)()

            # Receive my message back
            await communicator.receive_json_from()

            # Receive processing pdf
            await communicator.receive_json_from()

            # Receive finished processing
            await communicator.receive_json_from()

        # Send ask file command
        message_content = "/file_ask # 2 what is the middle ages"
        await communicator.send_json_to(
            {
                "chatroom_id": self.chatroom_id,
                "message": message_content,
            }
        )

        # Receive my message back
        response = await communicator.receive_json_from()
        self.assertEqual(
            response["message"]["content"], "/file_ask # 2 what is the middle ages"
        )
        self.assertEqual(response["message"]["sender"]["id"], self.user1.id)

        # Receive a message from the chatbot
        response = await communicator.receive_json_from()

        self.assertEqual(response["chatroom_id"], self.chatroom_id)
        self.assertEqual(response["message"]["sender"]["id"], self.pico_user.id)
        self.assertEqual(
            response["message"]["sender"]["username"], self.pico_user.username
        )

        await communicator.disconnect()

    async def test_file_ask_command_in_main_chat_no_arg1(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        # Send ask file command
        message_content = "/file_ask what is the middle ages"
        await communicator.send_json_to(
            {
                "chatroom_id": self.chatroom_id,
                "message": message_content,
            }
        )

        # Receive my message back
        response = await communicator.receive_json_from()
        self.assertEqual(
            response["message"]["content"], "/file_ask what is the middle ages"
        )
        self.assertEqual(response["message"]["sender"]["id"], self.user1.id)

        # Receive a message from the chatbot
        response = await communicator.receive_json_from()

        self.assertEqual(response["message"]["content"], FILE_NOT_FOUND_MESSAGE)

        await communicator.disconnect()

    async def test_file_ask_command_in_main_chat_bad_arg1(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        # Send file search command
        message_content = "/file_ask # a what is the middle ages"
        await communicator.send_json_to(
            {
                "chatroom_id": self.chatroom_id,
                "message": message_content,
            }
        )

        # Receive my message back
        response = await communicator.receive_json_from()
        self.assertEqual(
            response["message"]["content"], "/file_ask # a what is the middle ages"
        )
        self.assertEqual(response["message"]["sender"]["id"], self.user1.id)

        # Receive a message from the chatbot
        response = await communicator.receive_json_from()

        self.assertEqual(response["message"]["content"], FILE_NOT_FOUND_MESSAGE)

        await communicator.disconnect()

    async def test_file_ask_command_in_main_chat_no_arg2(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        # Send file search command
        message_content = "/file_search # 1"
        await communicator.send_json_to(
            {
                "chatroom_id": self.chatroom_id,
                "message": message_content,
            }
        )

        # Receive my message back
        response = await communicator.receive_json_from()
        self.assertEqual(
            response["message"]["content"],
            message_content,
        )
        self.assertEqual(response["message"]["sender"]["id"], self.user1.id)

        # Receive a message from the chatbot
        response = await communicator.receive_json_from()

        self.assertEqual(response["message"]["content"], FILE_NOT_FOUND_MESSAGE)

        await communicator.disconnect()

    async def test_file_ask_command_not_processed(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        # create a message with an attachment
        response = await sync_to_async(self.create_attachment_message_through_http)()

        # Receive my message back
        await communicator.receive_json_from()

        # Send ask file command
        message_content = "/file_ask what is the middle ages"
        await communicator.send_json_to(
            {
                "chatroom_id": self.chatroom_id,
                "message": message_content,
                "parent_message_id": response.json()["id"],
            }
        )

        # Receive my message back
        response = await communicator.receive_json_from()
        self.assertEqual(
            response["message"]["content"], "/file_ask what is the middle ages"
        )
        self.assertEqual(response["message"]["sender"]["id"], self.user1.id)

        # Receive a message from the chatbot
        response = await communicator.receive_json_from()

        self.assertEqual(response["chatroom_id"], self.chatroom_id)
        self.assertEqual(response["message"]["sender"]["id"], self.pico_user.id)
        self.assertEqual(
            response["message"]["sender"]["username"], self.pico_user.username
        )
        self.assertEqual(response["message"]["content"], FILE_NOT_READY_MESSAGE)

        await communicator.disconnect()

    async def test_pico_translate_command(self):
        communicator, connected, _ = await self.connect(token=self.access_token1)
        self.assertTrue(connected)

        # Send a message to the chatroom
        message_content = (
            "i love baseball bats. there is not much to say except baseball bats"
        )
        await communicator.send_json_to(
            {"chatroom_id": self.chatroom_id, "message": message_content}
        )
        # Receive my message back
        response = await communicator.receive_json_from()
        self.assertEqual(response["message"]["content"], message_content)
        self.assertEqual(response["message"]["sender"]["id"], self.user1.id)

        # Send a message to the chatroom
        message_content = "/pico_translate"
        await communicator.send_json_to(
            {"chatroom_id": self.chatroom_id, "message": message_content}
        )
        # Receive my message back
        response = await communicator.receive_json_from()
        self.assertEqual(response["message"]["content"], message_content)
        self.assertEqual(response["message"]["sender"]["id"], self.user1.id)

        # Receive a message from the chatbot
        response = await communicator.receive_json_from(timeout=30)
        self.assertEqual(response["chatroom_id"], self.chatroom_id)
        self.assertEqual(response["message"]["sender"]["id"], self.pico_user.id)
        self.assertEqual(
            response["message"]["sender"]["username"], self.pico_user.username
        )
        self.assertEqual(
            response["message"]["content"],
            "Mocked response from OpenAI completions create",
        ) """
