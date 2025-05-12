from api.tests.factories import UserFactory
from commands.commands_utils import CommandRegistry
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from pico_backend.auth import generate_tokens

User = get_user_model()


class MiscellaneousTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory.create()
        cls.access_token, _ = generate_tokens(cls.user)
        cls.auth_headers = {"Authorization": f"Bearer {cls.access_token}"}

    def setUp(self):
        self.client = Client(headers=self.auth_headers)

    def test_list_commands(self):
        url = reverse("api:commands_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(response.json()), len(CommandRegistry.get_commands_and_descriptions())
        )
        self.assertEqual(
            set(
                (command["name"], command["description"]) for command in response.json()
            ),
            set(CommandRegistry.get_commands_and_descriptions()),
        )
