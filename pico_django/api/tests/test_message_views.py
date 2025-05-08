from api.models import Message
from api.tests.factories import MessageFactory
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from pico_backend.auth import generate_tokens
from shared.testing import PatchingAndRedisTestCase


class MessageForMemberTestCase(PatchingAndRedisTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.message = MessageFactory.create()
        cls.user = cls.message.sender
        cls.access_token, _ = generate_tokens(cls.user)
        cls.auth_headers = {"Authorization": f"Bearer {cls.access_token}"}

        cls.chatroom = cls.message.chatroom
        cls.chatroom.add_member(cls.user)

    def setUp(self):
        super().setUp()
        self.client = Client(headers=self.auth_headers)

    def test_create_message_as_member(self):
        data = {"content": "Test Message"}
        url = reverse(
            "api:chatroom_message_list",
            kwargs={"chatroom_id": self.chatroom.pk},
        )
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["content"], "Test Message")
        self.assertEqual(response.json()["sender"]["id"], self.user.pk)
        self.assertEqual(response.json()["attachment"], None)
        self.assertEqual(response.json()["thread_messages"], [])
        self.assertEqual(response.json()["parent_message"], None)
        self.assertEqual(Message.objects.count(), 2)
        new_message = Message.objects.get(id=response.json()["id"])
        self.assertEqual(new_message.content, "Test Message")
        self.assertEqual(new_message.sender, self.user)
        self.assertEqual(new_message.chatroom, self.chatroom)

    def test_create_empty_message_as_member(self):
        data = {"content": ""}
        url = reverse(
            "api:chatroom_message_list",
            kwargs={"chatroom_id": self.chatroom.pk},
        )
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Message.objects.count(), 1)

    def test_create_no_text_attachment_message_as_member(self):
        # Create dummy files
        with open("pico_django/api/tests/test_files/test_photo.png", "rb") as file:
            file = SimpleUploadedFile(
                "test_photo.png", file.read(), content_type="image/png"
            )

        # Data dictionary
        data = {
            "upload": file,
        }

        url = reverse(
            "api:chatroom_message_list",
            kwargs={"chatroom_id": self.chatroom.pk},
        )

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Message.objects.count(), 4)
        new_message = Message.objects.get(id=response.json()["id"])
        self.assertEqual(new_message.content, "")
        self.assertEqual(new_message.sender, self.user)
        self.assertEqual(new_message.chatroom, self.chatroom)

    def test_create_attachment_message_as_member(self):
        # Create dummy files
        with open("pico_django/api/tests/test_files/test_photo.png", "rb") as file:
            file = SimpleUploadedFile(
                "test_photo.png", file.read(), content_type="image/png"
            )

        # Data dictionary
        data = {
            "content": "Test Message",
            "upload": file,
        }

        url = reverse(
            "api:chatroom_message_list",
            kwargs={"chatroom_id": self.chatroom.pk},
        )

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 201)

        response_attachment_url = response.json()["attachment"]
        self.assertTrue("files/no_file_group/test_photo" in response_attachment_url)

        self.assertEqual(Message.objects.count(), 4)
        new_message = Message.objects.get(id=response.json()["id"])
        self.assertEqual(new_message.content, "Test Message")
        self.assertEqual(new_message.sender, self.user)
        self.assertEqual(new_message.chatroom, self.chatroom)

    def test_create_pdf_file_attachment_message_as_member(self):
        # Create dummy files
        with open("pico_django/api/tests/test_files/test_pdf.pdf", "rb") as file:
            file = SimpleUploadedFile(
                "test_pdf.pdf", file.read(), content_type="application/pdf"
            )

        # Data dictionary
        data = {
            "content": "Test Message",
            "upload": file,
        }

        url = reverse(
            "api:chatroom_message_list",
            kwargs={"chatroom_id": self.chatroom.pk},
        )

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 201)

        response_attachment_url = response.json()["attachment"]
        self.assertTrue("files/no_file_group/test_pdf" in response_attachment_url)
        new_message = Message.objects.get(id=response.json()["id"])
        self.assertEqual(new_message.content, "Test Message")
        self.assertEqual(new_message.sender, self.user)
        self.assertEqual(new_message.chatroom, self.chatroom)

    def test_create_txt_file_attachment_message_as_member(self):
        # Create dummy files
        with open("pico_django/api/tests/test_files/test_txt.txt", "rb") as file:
            file = SimpleUploadedFile(
                "test_txt.txt", file.read(), content_type="text/plain"
            )

        # Data dictionary
        data = {
            "content": "Test Message",
            "upload": file,
        }

        url = reverse(
            "api:chatroom_message_list",
            kwargs={"chatroom_id": self.chatroom.pk},
        )

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Message.objects.count(), 4)
        new_message = Message.objects.get(id=response.json()["id"])
        self.assertEqual(new_message.content, "Test Message")
        self.assertEqual(new_message.sender, self.user)
        self.assertEqual(new_message.chatroom, self.chatroom)

    def test_create_docx_file_attachment_message_as_member(self):
        # Create dummy files
        with open("pico_django/api/tests/test_files/test_docx.docx", "rb") as file:
            file = SimpleUploadedFile(
                "test_docx.docx",
                file.read(),
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

        # Data dictionary
        data = {
            "content": "Test Message",
            "upload": file,
        }

        url = reverse(
            "api:chatroom_message_list",
            kwargs={"chatroom_id": self.chatroom.pk},
        )

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Message.objects.count(), 4)
        new_message = Message.objects.get(id=response.json()["id"])
        self.assertEqual(new_message.content, "Test Message")
        self.assertEqual(new_message.sender, self.user)

    def test_create_bad_file_type_attachment_message_as_member(self):
        # Create dummy files
        with open(
            "pico_django/api/tests/test_files/sh_exec_with_photo_extension.png",
            "rb",
        ) as file:
            file = SimpleUploadedFile(
                "sh_exec_with_photo_extension.png",
                file.read(),
                content_type="image/png",
            )

        # Data dictionary
        data = {
            "content": "Test Message",
            "upload": file,
        }

        url = reverse(
            "api:chatroom_message_list",
            kwargs={"chatroom_id": self.chatroom.pk},
        )

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Message.objects.count(), 1)

    def test_create_bad_type_header_attachment_message_as_member(self):
        # Create dummy files
        with open("pico_django/api/tests/test_files/test_photo.png", "rb") as file:
            file = SimpleUploadedFile(
                "test_photo.png", file.read(), content_type="application/x-sh"
            )

        # Data dictionary
        data = {
            "content": "Test Message",
            "upload": file,
        }

        url = reverse(
            "api:chatroom_message_list",
            kwargs={"chatroom_id": self.chatroom.pk},
        )

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Message.objects.count(), 1)

    def test_list_messages_as_member(self):
        url = reverse(
            "api:chatroom_message_list", kwargs={"chatroom_id": self.chatroom.pk}
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertTrue(self.message.pk in [msg["id"] for msg in response.json()])
        message = [
            message for message in response.json() if message["id"] == self.message.pk
        ][0]
        self.assertEqual(message["content"], self.message.content)
        self.assertEqual(message["sender"]["id"], self.user.pk)
        self.assertEqual(message["sender"]["username"], self.user.username)


class MessageForNonMemberTestCase(PatchingAndRedisTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.message = MessageFactory.create()
        cls.user = cls.message.sender
        cls.access_token, _ = generate_tokens(cls.user)
        cls.auth_headers = {"Authorization": f"Bearer {cls.access_token}"}

        cls.chatroom = cls.message.chatroom

    def setUp(self):
        super().setUp()
        self.client = Client(headers=self.auth_headers)

    def test_create_messages_as_non_member(self):
        data = {"content": "Test Message"}
        url = reverse(
            "api:chatroom_message_list",
            kwargs={"chatroom_id": self.chatroom.pk},
        )
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Message.objects.count(), 1)

    def test_list_messages_as_non_member(self):
        url = reverse(
            "api:chatroom_message_list", kwargs={"chatroom_id": self.chatroom.pk}
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)
