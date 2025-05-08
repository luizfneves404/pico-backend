from api.tests.factories import UserFactory
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from fcm_django.models import FCMDevice

from pico_backend.auth import generate_tokens

User = get_user_model()


class FCMDevicesTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user_no_device1 = UserFactory.create()
        cls.user_no_device2 = UserFactory.create()
        cls.user_device1 = UserFactory.create()
        cls.access_token_no_device1, _ = generate_tokens(cls.user_no_device1)
        cls.access_token_no_device2, _ = generate_tokens(cls.user_no_device2)
        cls.access_token_device1, _ = generate_tokens(cls.user_device1)
        cls.auth_headers_no_device1 = {
            "Authorization": f"Bearer {cls.access_token_no_device1}"
        }
        cls.auth_headers_no_device2 = {
            "Authorization": f"Bearer {cls.access_token_no_device2}"
        }
        cls.auth_headers_device1 = {
            "Authorization": f"Bearer {cls.access_token_device1}"
        }

        cls.fcm_device1 = FCMDevice.objects.create(
            registration_id="4667", type="android", user=cls.user_device1
        )

    def setUp(self):
        self.client_no_device1 = Client(headers=self.auth_headers_no_device1)
        self.client_no_device2 = Client(headers=self.auth_headers_no_device2)
        self.client_device1 = Client(headers=self.auth_headers_device1)

    def test_create_or_update_device(self):
        url = reverse("api:device_create_or_update")
        data = {"registration_id": "123", "type": "android"}
        response = self.client_no_device1.post(
            url, data, content_type="application/json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["registration_id"], "123")
        self.assertEqual(response.json()["type"], "android")

    def test_create_or_update_device_wrong_type(self):
        url = reverse("api:device_create_or_update")
        data = {"registration_id": "123", "type": "wrong"}
        response = self.client_no_device1.post(
            url, data, content_type="application/json"
        )
        self.assertEqual(response.status_code, 422)

    def test_create_or_update_device_missing_type(self):
        url = reverse("api:device_create_or_update")
        data = {"registration_id": "123"}
        response = self.client_no_device1.post(
            url, data, content_type="application/json"
        )
        self.assertEqual(response.status_code, 422)

    def test_create_or_update_device_missing_registration_id(self):
        url = reverse("api:device_create_or_update")
        data = {"type": "android"}
        response = self.client_no_device1.post(
            url, data, content_type="application/json"
        )
        self.assertEqual(response.status_code, 422)

    def test_create_or_update_new_user_on_device(self):
        url = reverse("api:device_create_or_update")
        data = {"registration_id": self.fcm_device1.registration_id, "type": "android"}
        response = self.client_no_device1.post(
            url, data, content_type="application/json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json()["registration_id"], self.fcm_device1.registration_id
        )
        self.assertEqual(response.json()["type"], "android")
        self.fcm_device1.refresh_from_db()
        self.assertEqual(self.fcm_device1.user, self.user_no_device1)

    def test_create_or_update_new_device_for_user(self):
        url = reverse("api:device_create_or_update")
        data = {"registration_id": "123", "type": "android"}
        response = self.client_device1.post(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["registration_id"], "123")
        self.assertEqual(response.json()["type"], "android")
        self.assertEqual(FCMDevice.objects.filter(user=self.user_device1).count(), 1)
        self.assertFalse(
            FCMDevice.objects.filter(
                registration_id=self.fcm_device1.registration_id
            ).exists()
        )
