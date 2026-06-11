import jwt
from api.tests.factories import UserFactory
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class AuthTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory.create()
        cls.password = "defaultpassword"

    def get_tokens(self, username: str, password: str):
        response = self.client.post(
            reverse("api:token_obtain_pair"),
            {"username": username, "password": password},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["access"], response.json()["refresh"]

    def assert_valid_jwt(self, token):
        decoded_token = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        self.assertEqual(decoded_token["user_id"], self.user.id)

    def test_token_obtain_pair(self):
        access_token, refresh_token = self.get_tokens(self.user.username, self.password)
        self.assert_valid_jwt(access_token)

    def test_token_obtain_pair_whitespace(self):
        access_token, refresh_token = self.get_tokens(
            f"  {self.user.username}  ", self.password
        )
        self.assert_valid_jwt(access_token)

    def test_token_verify(self):
        access_token, _ = self.get_tokens(self.user.username, self.password)
        response = self.client.post(
            reverse("api:token_verify"),
            {"token": access_token},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

    def test_token_refresh(self):
        _, refresh_token = self.get_tokens(self.user.username, self.password)
        response = self.client.post(
            reverse("api:token_refresh"),
            {"refresh": refresh_token},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        new_access_token = response.json()["access"]
        self.assert_valid_jwt(new_access_token)

    def test_user_me_endpoint(self):
        access_token, _ = self.get_tokens(self.user.username, self.password)
        response = self.client.get(
            reverse("api:user_me"), HTTP_AUTHORIZATION=f"Bearer {access_token}"
        )
        self.assertEqual(response.status_code, 200)
        user_data = response.json()
        self.assertEqual(user_data["id"], self.user.pk)
        self.assertEqual(user_data["username"], self.user.username)
        self.assertEqual(user_data["phone_number"], self.user.phone_number)
        self.assertEqual(user_data["email"], self.user.email)
