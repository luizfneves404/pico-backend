from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from api.models import School
from api.tests.factories import SchoolFactory, UserFactory
from pico_backend.auth import generate_tokens

User = get_user_model()


class SchoolTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = SchoolFactory.create()
        cls.school2 = SchoolFactory.create()
        cls.user = UserFactory.create(school=cls.school)
        cls.access_token, _ = generate_tokens(cls.user)
        cls.auth_headers = {"Authorization": f"Bearer {cls.access_token}"}

    def setUp(self):
        self.client = Client(headers=self.auth_headers)

    def test_list_schools(self):
        url = reverse("api:school_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 2)
        schools = response.json()
        self.assertCountEqual(
            [
                {"id": self.school.id, "name": self.school.name},
                {"id": self.school2.id, "name": self.school2.name},
            ],
            [{"id": school["id"], "name": school["name"]} for school in schools],
        )

    def test_get_school_detail(self):
        url = reverse("api:school_detail", args=[self.school.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], self.school.id)
        self.assertEqual(response.json()["name"], self.school.name)

    def test_get_school_detail_not_found(self):
        url = reverse("api:school_detail", args=[9999])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_create_school(self):
        url = reverse("api:school_create")
        response = self.client.post(
            url, {"name": "New School"}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["name"], "New School")
        self.assertEqual(School.objects.count(), 3)

    def test_create_school_invalid(self):
        url = reverse("api:school_create")
        response = self.client.post(url, {"name": ""}, content_type="application/json")
        self.assertEqual(response.status_code, 422)

    def test_school_ranking(self):
        url = reverse("api:school_ranking")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 2)
        self.assertEqual(response.json()[0]["id"], self.school.id)
        self.assertEqual(response.json()[0]["name"], self.school.name)
        self.assertEqual(response.json()[0]["score"], 0)
        self.assertEqual(response.json()[0]["rank"], 1)
        self.assertEqual(response.json()[1]["id"], self.school2.id)
        self.assertEqual(response.json()[1]["name"], self.school2.name)
        self.assertEqual(response.json()[1]["score"], 0)
        self.assertEqual(response.json()[1]["rank"], 2)

        # user answers 100 correct answers
        self.user.quiz_info.dynamic_score = 100
        self.user.quiz_info.save()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 2)
        self.assertEqual(response.json()[0]["id"], self.school.id)
        self.assertEqual(response.json()[0]["name"], self.school.name)
        self.assertEqual(response.json()[0]["score"], 100)
        self.assertEqual(response.json()[0]["rank"], 1)
        self.assertEqual(response.json()[1]["id"], self.school2.id)
        self.assertEqual(response.json()[1]["name"], self.school2.name)
        self.assertEqual(response.json()[1]["score"], 0)
        self.assertEqual(response.json()[1]["rank"], 2)
