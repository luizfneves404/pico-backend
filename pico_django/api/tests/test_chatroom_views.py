import json

from api.models import GroupChatroom
from api.tests.factories import GroupChatroomFactory, UserFactory
from api.tests.utils import create_simple_uploaded_file
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from pico_backend.auth import generate_tokens
from shared.testing import PatchingAndRedisTestCase

User = get_user_model()


class ChatroomForMemberTestCase(PatchingAndRedisTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user = UserFactory.create()
        cls.access_token, _ = generate_tokens(cls.user)
        cls.auth_headers = {"Authorization": f"Bearer {cls.access_token}"}

        cls.admin_user = UserFactory.create()
        cls.not_admin_user = UserFactory.create()
        cls.user_out = UserFactory.create()
        cls.chatroom = GroupChatroomFactory.create()
        cls.chatroom.add_members([cls.admin_user, cls.user, cls.not_admin_user])

    def setUp(self):
        super().setUp()
        self.client = Client(headers=self.auth_headers)

    def test_rename_chatroom_as_member(self):
        url = reverse("api:chatroom_detail", kwargs={"chatroom_id": self.chatroom.pk})
        data = {"name": "New Name"}
        response = self.client.patch(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 403)
        self.chatroom.refresh_from_db()
        self.assertNotEqual(self.chatroom.name, "New Name")

    def test_list_chatrooms_as_member(self):
        url = reverse("api:chatroom_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            self.chatroom.pk in [chatroom["id"] for chatroom in response.json()]
        )

    def test_retrieve_chatroom_as_member(self):
        url = reverse("api:chatroom_detail", kwargs={"chatroom_id": self.chatroom.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], self.chatroom.pk)
        self.assertEqual(response.json()["name"], self.chatroom.name)
        self.assertTrue(
            self.admin_user.pk
            in [member["id"] for member in response.json()["members"]]
        )
        # get the admin user from the members list
        admin_user = [
            member
            for member in response.json()["members"]
            if member["id"] == self.admin_user.pk
        ][0]
        self.assertTrue(admin_user["is_admin"])
        self.assertTrue(admin_user["username"], self.admin_user.username)
        user = [
            member
            for member in response.json()["members"]
            if member["id"] == self.user.pk
        ][0]
        self.assertFalse(user["is_admin"])

    def test_join_chatroom_as_member(self):
        url = reverse("api:chatroom_join", kwargs={"chatroom_id": self.chatroom.pk})
        response = self.client.patch(url)
        self.assertEqual(response.status_code, 400)

    def test_leave_chatroom_as_member(self):
        url = reverse("api:chatroom_leave", kwargs={"chatroom_id": self.chatroom.pk})
        response = self.client.patch(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.user in self.chatroom.members.all())

    def test_add_member_as_member(self):
        # cannot add
        url = reverse(
            "api:chatroom_add_member", kwargs={"chatroom_id": self.chatroom.pk}
        )
        data = {"username": self.user_out.username}
        response = self.client.patch(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.chatroom.is_member(self.user_out))

    def test_remove_member_as_member(self):
        # cannot remove
        url = reverse(
            "api:chatroom_remove_member", kwargs={"chatroom_id": self.chatroom.pk}
        )
        data = {"username": self.not_admin_user.username}
        response = self.client.patch(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(self.chatroom.is_member(self.not_admin_user))

    def test_make_admin_as_member(self):
        # cannot make admin
        url = reverse(
            "api:chatroom_make_admin", kwargs={"chatroom_id": self.chatroom.pk}
        )
        data = {"username": self.not_admin_user.username}
        response = self.client.patch(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.chatroom.has_admin_perms(self.not_admin_user))

    def test_remove_admin_as_member(self):
        # cannot remove admin
        url = reverse(
            "api:chatroom_make_admin", kwargs={"chatroom_id": self.chatroom.pk}
        )
        data = {"username": self.admin_user.username}
        response = self.client.patch(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(self.chatroom.has_admin_perms(self.admin_user))


class ChatroomForAdminTestCase(PatchingAndRedisTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.creator_user = UserFactory.create()

        cls.admin_user = UserFactory.create()
        cls.access_token, _ = generate_tokens(cls.admin_user)
        cls.auth_headers = {"Authorization": f"Bearer {cls.access_token}"}

        cls.user_in = UserFactory.create()
        cls.user_out = UserFactory.create()
        cls.other_admin = UserFactory.create()
        cls.chatroom = GroupChatroomFactory.create()
        cls.chatroom.add_member(cls.creator_user, admin=True)
        cls.chatroom.add_member(cls.admin_user, admin=True)
        cls.chatroom.add_member(cls.other_admin, admin=True)
        cls.chatroom.add_member(cls.user_in)

    def setUp(self):
        super().setUp()
        self.client = Client(headers=self.auth_headers)

    def test_rename_chatroom_as_admin(self):
        url = reverse("api:chatroom_detail", kwargs={"chatroom_id": self.chatroom.pk})
        data = {"name": "New Name"}
        response = self.client.patch(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.chatroom.refresh_from_db()
        self.assertEqual(self.chatroom.name, "New Name")

    def test_add_member_as_admin(self):
        url = reverse(
            "api:chatroom_add_member", kwargs={"chatroom_id": self.chatroom.pk}
        )

        # add member that is already in chatroom
        data_in = {"username": self.user_in.username}
        response_in = self.client.patch(url, data_in, content_type="application/json")
        self.assertEqual(response_in.status_code, 400)
        self.assertTrue(self.chatroom.is_member(self.user_in))

        # add member that is not in chatroom
        data_out = {"username": self.user_out.username}
        response_out = self.client.patch(url, data_out, content_type="application/json")
        self.assertEqual(response_out.status_code, 200)
        self.assertTrue(self.chatroom.is_member(self.user_out))

        # add member for user that does not exist
        data_nonexistent = {"username": "dsonreognergnregno"}
        response_nonexistent = self.client.patch(
            url, data_nonexistent, content_type="application/json"
        )
        self.assertEqual(response_nonexistent.status_code, 404)

    def test_remove_member_as_admin(self):
        url = reverse(
            "api:chatroom_remove_member", kwargs={"chatroom_id": self.chatroom.pk}
        )

        # remove member that is in chatroom
        data_in = {"username": self.user_in.username}
        response_in = self.client.patch(url, data_in, content_type="application/json")
        self.assertEqual(response_in.status_code, 200)
        self.assertFalse(self.chatroom.is_member(self.user_in))

        # remove member that is not in chatroom
        data_out = {"username": self.user_out.username}
        response_out = self.client.patch(url, data_out, content_type="application/json")
        self.assertEqual(response_out.status_code, 400)
        self.assertFalse(self.chatroom.is_member(self.user_out))

        # remove member that is admin
        data_admin = {"username": self.other_admin.username}
        response_admin = self.client.patch(
            url, data_admin, content_type="application/json"
        )
        self.assertEqual(response_admin.status_code, 200)
        self.assertFalse(self.chatroom.is_member(self.other_admin))

        # remove member that is creator
        data_creator = {"username": self.creator_user.username}
        response_creator = self.client.patch(
            url, data_creator, content_type="application/json"
        )
        self.assertEqual(response_creator.status_code, 400)
        self.assertTrue(self.chatroom.is_member(self.creator_user))

        # remove member for user that does not exist
        data_nonexistent = {"username": "dsonreognergnregno"}
        response_nonexistent = self.client.patch(
            url, data_nonexistent, content_type="application/json"
        )
        self.assertEqual(response_nonexistent.status_code, 404)

    def test_make_admin_as_admin(self):
        url = reverse(
            "api:chatroom_make_admin", kwargs={"chatroom_id": self.chatroom.pk}
        )

        data = {"username": self.user_in.username}
        response = self.client.patch(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.chatroom.has_admin_perms(self.user_in))

        data = {"username": self.user_out.username}
        response = self.client.patch(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.chatroom.has_admin_perms(self.user_out))

    def test_remove_admin_as_admin(self):
        url = reverse(
            "api:chatroom_remove_admin", kwargs={"chatroom_id": self.chatroom.pk}
        )

        data_admin = {"username": self.other_admin.username}
        response_admin = self.client.patch(
            url, data_admin, content_type="application/json"
        )
        self.assertEqual(response_admin.status_code, 200)
        self.assertFalse(self.chatroom.has_admin_perms(self.other_admin))

        data_in = {"username": self.user_in.username}
        response_in = self.client.patch(url, data_in, content_type="application/json")
        self.assertEqual(response_in.status_code, 400)
        self.assertFalse(self.chatroom.has_admin_perms(self.user_in))

        data_out = {"username": self.user_out.username}
        response_out = self.client.patch(url, data_out, content_type="application/json")
        self.assertEqual(response_out.status_code, 400)
        self.assertFalse(self.chatroom.has_admin_perms(self.user_out))

        data_creator = {"username": self.creator_user.username}
        response_creator = self.client.patch(
            url, data_creator, content_type="application/json"
        )
        self.assertEqual(response_creator.status_code, 400)
        self.assertTrue(self.chatroom.has_admin_perms(self.creator_user))


class ChatroomForNonMemberTestCase(PatchingAndRedisTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user = UserFactory.create()

        cls.access_token, _ = generate_tokens(cls.user)
        cls.auth_headers = {"Authorization": f"Bearer {cls.access_token}"}

        cls.chatroom = GroupChatroomFactory.create()

    def setUp(self):
        super().setUp()
        self.client = Client(headers=self.auth_headers)

    def test_create_chatroom_as_non_member_no_members(self):
        url = reverse("api:chatroom_list")
        data = {"name": "Test Roommy"}
        response = self.client.post(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(GroupChatroom.objects.filter(pk=response.json()["id"]).exists())
        new_chatroom = GroupChatroom.objects.get(pk=response.json()["id"])
        self.assertEqual(new_chatroom.name, "Test Roommy")
        self.assertTrue(new_chatroom.is_creator(self.user))

    def test_create_chatroom_as_non_member_with_members(self):
        url = reverse("api:chatroom_list")

        user1 = UserFactory.create()
        user2 = UserFactory.create()

        data = {"name": "Test Roommy", "members_ids": [user1.pk, user2.pk]}
        response = self.client.post(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(GroupChatroom.objects.filter(pk=response.json()["id"]).exists())
        new_chatroom = GroupChatroom.objects.get(pk=response.json()["id"])
        self.assertEqual(new_chatroom.name, "Test Roommy")
        self.assertEqual(new_chatroom.members.count(), 3)
        self.assertTrue(new_chatroom.is_creator(self.user))
        self.assertTrue(new_chatroom.is_member(self.user))
        self.assertTrue(new_chatroom.is_member(user1))
        self.assertTrue(new_chatroom.is_member(user2))

    def test_create_chatroom_as_non_member_with_members_and_icon(self):
        url = reverse("api:chatroom_with_icon_create")

        user1 = UserFactory.create()
        user2 = UserFactory.create()

        icon = create_simple_uploaded_file(
            "pico_django/api/tests/test_files/test_photo.png",
            "test_photo.png",
            "image/png",
        )

        data = {
            "name": "Test Roommy",
            "members_ids": [user1.pk, user2.pk],
        }
        response = self.client.post(url, {"data": json.dumps(data), "upload": icon})
        self.assertEqual(response.status_code, 201)
        self.assertTrue(GroupChatroom.objects.filter(pk=response.json()["id"]).exists())
        new_chatroom = GroupChatroom.objects.get(pk=response.json()["id"])
        self.assertEqual(new_chatroom.name, "Test Roommy")
        self.assertEqual(new_chatroom.members.count(), 3)
        self.assertTrue(new_chatroom.is_creator(self.user))
        self.assertTrue(new_chatroom.is_member(self.user))
        self.assertTrue(new_chatroom.is_member(user1))
        self.assertTrue(new_chatroom.is_member(user2))
        self.assertTrue(new_chatroom.icon)
        self.assertRegex(new_chatroom.icon.file.name, r"test_photo\w*\.png")

    def test_list_chatrooms_as_non_member(self):
        url = reverse("api:chatroom_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            self.chatroom.pk in [chatroom["id"] for chatroom in response.json()]
        )

    def test_retrieve_chatroom_as_non_member(self):
        url = reverse("api:chatroom_detail", kwargs={"chatroom_id": self.chatroom.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_join_chatroom_as_non_member(self):
        url = reverse("api:chatroom_join", kwargs={"chatroom_id": self.chatroom.pk})
        response = self.client.patch(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.user in self.chatroom.members.all())

    def test_leave_chatroom_as_non_member(self):
        url = reverse("api:chatroom_leave", kwargs={"chatroom_id": self.chatroom.pk})
        response = self.client.patch(url)
        self.assertEqual(response.status_code, 404)


class ChatroomForCreatorTestCase(PatchingAndRedisTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.creator_user = UserFactory.create()
        client = Client()
        response = client.post(
            reverse("api:token_obtain_pair"),
            {"username": cls.creator_user.username, "password": "defaultpassword"},
            content_type="application/json",
        )
        cls.access_token = response.json()["access"]
        cls.auth_headers = {"Authorization": f"Bearer {cls.access_token}"}

        cls.user_old = UserFactory.create()
        cls.user_young = UserFactory.create()

        cls.chatroom = GroupChatroomFactory.create()
        cls.chatroom.add_members([cls.creator_user, cls.user_old, cls.user_young])

    def setUp(self):
        super().setUp()
        self.client = Client(headers=self.auth_headers)

    def test_leave_chatroom_as_creator(self):
        url = reverse("api:chatroom_leave", kwargs={"chatroom_id": self.chatroom.pk})
        response = self.client.patch(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.creator_user in self.chatroom.members.all())
        self.assertTrue(self.chatroom.is_creator(self.user_old))
        self.assertFalse(self.chatroom.is_creator(self.user_young))
