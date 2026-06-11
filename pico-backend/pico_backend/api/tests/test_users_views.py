from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from api.tests.factories import SchoolFactory, UserFactory
from pico_backend.auth import generate_tokens

User = get_user_model()


class UserCoreTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory.create()
        cls.user_existing = UserFactory.create()
        cls.referred_by_user = UserFactory.create()
        cls.access_token, _ = generate_tokens(cls.user)
        cls.auth_headers = {"Authorization": f"Bearer {cls.access_token}"}

    def setUp(self):
        self.client = Client(headers=self.auth_headers)

    def test_create_user_followed_by_jwt_and_retrieve_user_me(self):
        url = reverse("api:user_create")

        user2_data = UserFactory.build()

        user2_dict = {
            "username": user2_data.username,
            "password": "defaultpassword",
            "phone_number": user2_data.phone_number,
            "email": user2_data.email,
            "school_id": user2_data.school.id,
            "chosen_college": user2_data.chosen_college.name,
            "chosen_course": user2_data.chosen_course.name,
            "education_level": user2_data.education_level,
            "signup_source": user2_data.signup_source,
            "referred_by_username": self.referred_by_user.username,
            "commitment": user2_data.commitment,
        }
        client = Client()
        response = client.post(url, user2_dict, content_type="application/json")
        self.assertEqual(response.status_code, 201)
        new_user = User.objects.get(id=response.json()["id"])
        self.assertEqual(response.json()["id"], new_user.id)
        self.assertEqual(response.json()["username"], user2_dict["username"])
        self.assertEqual(response.json()["phone_number"], user2_dict["phone_number"])
        self.assertEqual(response.json()["email"], user2_dict["email"])
        self.assertEqual(response.json()["school_id"], user2_dict["school_id"])
        self.assertEqual(response.json()["commitment"], user2_dict["commitment"])
        self.assertEqual(
            response.json()["education_level"], user2_dict["education_level"]
        )
        self.assertEqual(
            response.json()["chosen_college"], user2_dict["chosen_college"]
        )
        self.assertEqual(response.json()["chosen_course"], user2_dict["chosen_course"])
        self.assertEqual(response.json()["signup_source"], user2_dict["signup_source"])
        self.assertEqual(new_user.username, user2_dict["username"])  # type: ignore
        # ensure that i can login with the new user
        url = reverse("api:token_obtain_pair")
        data = {"username": user2_dict["username"], "password": "defaultpassword"}
        response_token = client.post(url, data, content_type="application/json")
        self.assertEqual(response_token.status_code, 200)

        auth_headers = {"Authorization": f"Bearer {response_token.json()['access']}"}
        client = Client(headers=auth_headers)

        # ensure that i can retrieve the new user
        url = reverse("api:user_me")
        response_me = client.get(url)
        self.assertEqual(response_me.status_code, 200)
        self.assertEqual(response_me.json()["id"], new_user.id)
        self.assertEqual(response_me.json()["username"], user2_dict["username"])
        self.assertEqual(response_me.json()["phone_number"], user2_dict["phone_number"])
        self.assertEqual(response_me.json()["email"], user2_dict["email"])
        self.assertEqual(response_me.json()["school_id"], user2_dict["school_id"])
        self.assertEqual(response_me.json()["commitment"], user2_dict["commitment"])
        self.assertEqual(
            response_me.json()["education_level"], user2_dict["education_level"]
        )
        self.assertEqual(
            response_me.json()["chosen_college"], user2_dict["chosen_college"]
        )
        self.assertEqual(
            response_me.json()["chosen_course"], user2_dict["chosen_course"]
        )
        self.assertEqual(response_me.json()["balance"], 1000)

    def test_create_user_deprecated(self):
        url = reverse("api:user_create")

        user2_data = UserFactory.build()

        user2_dict = {
            "username": user2_data.username,
            "password": "defaultpassword",
            "phone_number": user2_data.phone_number,
            "email": user2_data.email,
            "school": user2_data.school.name,
            "chosen_college": user2_data.chosen_college.name,
            "chosen_course": user2_data.chosen_course.name,
            "education_level": user2_data.education_level,
            "signup_source": user2_data.signup_source,
            "referred_by_username": self.referred_by_user.username,
            "commitment": user2_data.commitment,
        }
        client = Client()
        response = client.post(url, user2_dict, content_type="application/json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(User.objects.filter(pk=response.json()["id"]).exists())
        new_user = User.objects.get(id=response.json()["id"])
        self.assertEqual(new_user.username, user2_dict["username"])  # type: ignore

        # ensure that i can login with the new user
        url = reverse("api:token_obtain_pair")
        data = {"username": user2_dict["username"], "password": "defaultpassword"}
        response_token = client.post(url, data, content_type="application/json")
        self.assertEqual(response_token.status_code, 200)

        auth_headers = {"Authorization": f"Bearer {response_token.json()['access']}"}
        client = Client(headers=auth_headers)

        # ensure that i can retrieve the new user
        url = reverse("api:user_me")
        response_me = client.get(url)
        self.assertEqual(response_me.status_code, 200)
        self.assertEqual(response_me.json()["id"], new_user.id)
        self.assertEqual(response_me.json()["username"], user2_dict["username"])
        self.assertEqual(response_me.json()["phone_number"], user2_dict["phone_number"])
        self.assertEqual(response_me.json()["email"], user2_dict["email"])
        self.assertEqual(response_me.json()["school"], user2_dict["school"])
        self.assertEqual(response_me.json()["commitment"], user2_dict["commitment"])
        self.assertEqual(
            response_me.json()["education_level"], user2_dict["education_level"]
        )
        self.assertEqual(
            response_me.json()["chosen_college"], user2_dict["chosen_college"]
        )
        self.assertEqual(
            response_me.json()["chosen_course"], user2_dict["chosen_course"]
        )
        self.assertEqual(
            response_me.json()["signup_source"], user2_dict["signup_source"]
        )
        self.assertEqual(response_me.json()["balance"], 1000)

    def test_create_user_fail_username_case_insensitive(self):
        url = reverse("api:user_create")
        username = self.user.username.upper()
        user2_data = UserFactory.build()
        user_dict = {
            "username": username,
            "password": "defaultpassword",
            "phone_number": user2_data.phone_number,
            "email": user2_data.email,
            "school_id": user2_data.school.id,
        }
        response = self.client.post(url, user_dict, content_type="application/json")
        self.assertEqual(response.status_code, 409)

    def test_retrieve_user_me(self):
        url = reverse("api:user_me")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], self.user.pk)
        self.assertEqual(response.json()["username"], self.user.username)
        self.assertEqual(response.json()["phone_number"], self.user.phone_number)
        self.assertEqual(response.json()["email"], self.user.email)
        self.assertEqual(response.json()["school_id"], self.user.school.id)
        self.assertEqual(response.json()["commitment"], self.user.commitment)
        self.assertEqual(response.json()["education_level"], self.user.education_level)
        self.assertEqual(response.json()["signup_source"], self.user.signup_source)
        self.assertEqual(response.json()["balance"], 1000)

    def test_retrieve_user_me_deprecated(self):
        url = reverse("api:user_me")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], self.user.pk)
        self.assertEqual(response.json()["username"], self.user.username)
        self.assertEqual(response.json()["phone_number"], self.user.phone_number)
        self.assertEqual(response.json()["email"], self.user.email)
        self.assertEqual(response.json()["school"], self.user.school.name)
        self.assertEqual(response.json()["commitment"], self.user.commitment)
        self.assertEqual(response.json()["education_level"], self.user.education_level)
        self.assertEqual(response.json()["signup_source"], self.user.signup_source)
        self.assertEqual(response.json()["balance"], 1000)

    def test_update_username(self):
        url = reverse("api:user_set_username")
        data = {"new_username": "newname", "current_password": "defaultpassword"}
        response = self.client.patch(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 204)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "newname")

    def test_update_username_already_exists(self):
        url = reverse("api:user_set_username")
        data = {
            "new_username": self.user_existing.username,
            "current_password": "defaultpassword",
        }
        response = self.client.patch(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 409)
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.username, self.user_existing.username)

    def test_update_password(self):
        url = reverse("api:user_set_password")
        data = {
            "new_password": "newpassword605",
            "current_password": "defaultpassword",
        }
        response = self.client.patch(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 204)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("newpassword605"))

    def test_update_phone_number(self):
        url = reverse("api:user_set_phone_number")
        data = {
            "new_phone_number": "21999202390",
            "current_password": "defaultpassword",
        }
        response = self.client.patch(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 204)
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone_number, "tel:+55-21-99920-2390")

    def test_update_phone_number_already_exists(self):
        url = reverse("api:user_set_phone_number")
        data = {
            "new_phone_number": self.user_existing.phone_number,
            "current_password": "defaultpassword",
        }
        response = self.client.patch(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 409)
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.phone_number, self.user_existing.phone_number)

    def test_update_phone_number_invalid(self):
        url = reverse("api:user_set_phone_number")
        data = {
            "new_phone_number": "invalid",
            "current_password": "defaultpassword",
        }
        response = self.client.patch(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 422)
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.phone_number, "invalid")

    def test_update_email(self):
        url = reverse("api:user_set_email")
        data = {
            "new_email": "test@example.com",
            "current_password": "defaultpassword",
        }
        response = self.client.patch(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 204)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "test@example.com")

    def test_update_email_already_exists(self):
        url = reverse("api:user_set_email")
        data = {
            "new_email": self.user_existing.email,
            "current_password": "defaultpassword",
        }
        response = self.client.patch(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 409)
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.email, self.user_existing.email)

    def test_update_email_invalid(self):
        url = reverse("api:user_set_email")
        data = {
            "new_email": "invalid",
            "current_password": "defaultpassword",
        }
        response = self.client.patch(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 422)
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.email, "invalid")

    def test_update_school(self):
        url = reverse("api:user_set_school")
        school = SchoolFactory.create()
        data = {
            "new_school_id": school.id,
        }
        response = self.client.patch(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 204)
        self.user.refresh_from_db()
        self.assertEqual(self.user.school, school)

    def test_update_school_deprecated(self):
        url = reverse("api:user_set_school")
        data = {
            "new_school": "new_school",
        }
        response = self.client.patch(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 204)
        self.user.refresh_from_db()
        self.assertEqual(self.user.school.name, "new_school")

    def test_update_school_to_blank(self):
        url = reverse("api:user_set_school")
        data = {
            "new_school_id": None,
        }
        response = self.client.patch(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 204)
        self.user.refresh_from_db()
        self.assertEqual(self.user.school, None)

    def test_update_school_to_blank_deprecated(self):
        url = reverse("api:user_set_school")
        data = {
            "new_school": "",
        }
        response = self.client.patch(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 204)
        self.user.refresh_from_db()
        self.assertEqual(self.user.school, None)

    def test_update_chosen_college(self):
        url = reverse("api:user_set_chosen_college")
        data = {
            "new_chosen_college": "new_chosen_college",
        }
        response = self.client.patch(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 204)
        self.user.refresh_from_db()
        self.assertEqual(self.user.chosen_college.name, "new_chosen_college")

    def test_update_chosen_college_to_blank(self):
        url = reverse("api:user_set_chosen_college")
        data = {
            "new_chosen_college": "",
        }
        response = self.client.patch(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 204)
        self.user.refresh_from_db()
        self.assertEqual(self.user.chosen_college, None)

    def test_update_chosen_course(self):
        url = reverse("api:user_set_chosen_course")
        data = {
            "new_chosen_course": "new_chosen_course",
        }
        response = self.client.patch(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 204)
        self.user.refresh_from_db()
        self.assertEqual(self.user.chosen_course.name, "new_chosen_course")

    def test_update_chosen_course_to_blank(self):
        url = reverse("api:user_set_chosen_course")
        data = {
            "new_chosen_course": "",
        }
        response = self.client.patch(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 204)
        self.user.refresh_from_db()
        self.assertEqual(self.user.chosen_course, None)

    def test_update_commitment(self):
        url = reverse("api:user_set_commitment")
        data = {
            "commitment": 10,
        }
        response = self.client.patch(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 204)
        self.user.refresh_from_db()
        self.assertEqual(self.user.commitment, 10)

    def test_update_education_level(self):
        url = reverse("api:user_set_education_level")
        data = {
            "education_level": "COL",
        }
        response = self.client.patch(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 204)
        self.user.refresh_from_db()
        self.assertEqual(self.user.education_level, "COL")

    def test_destroy_user(self):
        url = reverse("api:user_me")
        data = {"current_password": "defaultpassword"}
        response = self.client.delete(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())

    def test_destroy_user_wrong_password(self):
        url = reverse("api:user_me")
        data = {"current_password": "wrongpassword"}
        response = self.client.delete(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 401)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_retrieve_user_stats_me(self):
        url = reverse("api:user_stats_me")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], self.user.pk)
        self.assertEqual(response.json()["username"], self.user.username)
        self.assertEqual(response.json()["streak"], 0)
        self.assertEqual(response.json()["done_today"], False)
        self.assertEqual(response.json()["total_answers"], 0)
        self.assertEqual(response.json()["correct_answers"], 0)
        self.assertIn("area_expected_scores", response.json())
        self.assertEqual(len(response.json()["area_expected_scores"]), 4)
        for area in [
            "Matemática",
            "Linguagem",  # deveria ser Linguagens, mas o front ta esperando errado
            "Ciências Humanas",
            "Ciências da Natureza",
        ]:
            self.assertIn(area, response.json()["area_expected_scores"])
            self.assertIsInstance(response.json()["area_expected_scores"][area], float)
        self.assertIn("score", response.json())
        self.assertIsInstance(response.json()["score"], float)
        self.assertIsInstance(response.json()["percentage_score"], float)
        self.assertIsInstance(response.json()["dynamic_score"], float)

    def test_retrieve_user_stats(self):
        url = reverse("api:user_stats", args=[self.user.username])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], self.user.pk)
        self.assertEqual(response.json()["username"], self.user.username)
        self.assertEqual(response.json()["school_id"], self.user.school.id)
        self.assertEqual(response.json()["school"], self.user.school.name)  # deprecated
        self.assertEqual(
            response.json()["chosen_college"],
            "" if self.user.chosen_college is None else self.user.chosen_college.name,
        )
        self.assertEqual(
            response.json()["chosen_course"],
            "" if self.user.chosen_course is None else self.user.chosen_course.name,
        )
        self.assertEqual(response.json()["education_level"], self.user.education_level)

        self.assertIn("area_expected_scores", response.json())
        self.assertEqual(len(response.json()["area_expected_scores"]), 4)
        for area in [
            "Matemática",
            "Linguagem",  # deveria ser Linguagens, mas o front ta esperando errado
            "Ciências Humanas",
            "Ciências da Natureza",
        ]:
            self.assertIn(area, response.json()["area_expected_scores"])
            self.assertIsInstance(response.json()["area_expected_scores"][area], float)
        self.assertIn("score", response.json())
        self.assertIsInstance(response.json()["score"], float)
        self.assertIn("percentage_score", response.json())
        self.assertIsInstance(response.json()["percentage_score"], float)


class UserMiscellaneousTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory.create(username="me_user")

        cls.deleted_user = User.objects.get_deleted_user()
        cls.system_user = User.objects.get_system_user()
        cls.pico_user = User.objects.get_pico_user()

        cls.access_token, _ = generate_tokens(cls.user)
        cls.auth_headers = {"Authorization": f"Bearer {cls.access_token}"}
        cls.users = UserFactory.create_batch(7)
        cls.search_users = [
            UserFactory.create(username=f"searchuser{i}") for i in range(1, 8)
        ]

    def setUp(self):
        self.client = Client(headers=self.auth_headers)

    def test_check_contacts(self):
        url = reverse("api:check_contacts") + "?page=1&page_size=4"
        phone_numbers = [str(user.phone_number) for user in self.users] + [
            "+551123111111"
        ]
        data = {"phone_numbers": phone_numbers}
        response = self.client.post(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        response_ids = [user["id"] for user in results]
        self.assertEqual(len(response_ids), 4)

        new_url = reverse("api:check_contacts") + "?page=2&page_size=4"
        new_response = self.client.post(new_url, data, content_type="application/json")
        self.assertEqual(new_response.status_code, 200)
        new_results = new_response.json()["results"]
        new_response_ids = [user["id"] for user in new_results]
        self.assertEqual(len(new_response_ids), 3)

        response_ids.extend(new_response_ids)

        for user in self.users:
            self.assertIn(user.pk, response_ids)

        for search_user in self.search_users:
            self.assertNotIn(search_user.pk, response_ids)

        response_phone_numbers = [
            user["phone_number"] for user in results + new_results
        ]

        for user in self.users:
            self.assertIn(user.phone_number, response_phone_numbers)

        self.assertNotIn("tel:+55-11-2311-1111", response_phone_numbers)

    def test_search_username(self):
        # add username to query string
        url = reverse("api:search_username") + "?username=searchuser&page=1&page_size=4"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        response_ids = [user["id"] for user in results]
        self.assertEqual(len(response_ids), 4)

        new_url = (
            reverse("api:search_username") + "?username=searchuser&page=2&page_size=4"
        )
        new_response = self.client.get(new_url)
        self.assertEqual(new_response.status_code, 200)
        new_results = new_response.json()["results"]
        new_response_ids = [user["id"] for user in new_results]
        self.assertEqual(len(new_response_ids), 3)

        response_ids.extend(new_response_ids)

        for search_user in self.search_users:
            self.assertTrue(search_user.pk in response_ids)

        for user in self.users:
            self.assertFalse(user.pk in response_ids)

        self.assertFalse(self.user.pk in response_ids)

    def test_retrieve_sentinel_users(self):
        url = reverse("api:sentinel_users")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        response = response.json()
        response_ids = [user["id"] for user in response]
        response_usernames = [user["username"] for user in response]
        self.assertEqual(len(response_ids), 3)
        self.assertIn(self.deleted_user.pk, response_ids)
        self.assertIn(self.deleted_user.username, response_usernames)
        self.assertIn(self.system_user.pk, response_ids)
        self.assertIn(self.system_user.username, response_usernames)
        self.assertIn(self.pico_user.pk, response_ids)
        self.assertIn(self.pico_user.username, response_usernames)

    def test_get_balance(self):
        url = reverse("api:get_balance")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["balance"], 1000)
