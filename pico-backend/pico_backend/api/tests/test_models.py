from api.models import EmbeddedFile, Membership, Message, User
from api.tests.factories import GroupChatroomFactory, MessageFactory, UserFactory
from django.test import TestCase


class UserModelTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Set up non-modified objects used by all test methods
        cls.user = UserFactory.create()
        cls.message = MessageFactory.create(sender=cls.user)

    def test_create_user(self):
        user = User.objects.create_user(
            username="newtestuser",
            phone_number="tel:+55-21-11171-2111",
            password="defaultpassword",
            email="testuser@example.com",
        )
        self.assertEqual(user.username, "newtestuser")
        self.assertEqual(user.phone_number, "tel:+55-21-11171-2111")
        self.assertEqual(user.email, "testuser@example.com")
        self.assertTrue(user.check_password("defaultpassword"))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_create_superuser(self):
        user = User.objects.create_superuser(
            username="newtestsuperuser",
            phone_number="tel:+55-21-11171-2111",
            password="defaultpassword",
            email="testuser@example.com",
        )
        self.assertEqual(user.username, "newtestsuperuser")
        self.assertEqual(user.phone_number, "tel:+55-21-11171-2111")
        self.assertEqual(user.email, "testuser@example.com")
        self.assertTrue(user.check_password("defaultpassword"))
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_user_str(self):
        self.assertEqual(str(self.user), self.user.username)

    def test_user_phone_number(self):
        self.assertTrue(str(self.user.phone_number).startswith("tel:+55-21-99933-"))

    def test_user_chatroom_set(self):
        self.assertEqual(self.user.chatroom_set.count(), 0)

    def test_delete_user(self):
        self.user.delete()
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.message.refresh_from_db()
        self.assertEqual(self.message.sender, User.objects.get_deleted_user())

    async def test_adelete_user(self):
        await self.user.adelete()
        self.assertFalse(await User.objects.filter(pk=self.user.pk).aexists())
        message = (
            await Message.objects.filter(pk=self.message.pk)
            .select_related("sender")
            .afirst()
        )
        self.assertEqual(message.sender, await User.objects.aget_deleted_user())


class ChatroomModelOneUserTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory.create()
        cls.chatroom = GroupChatroomFactory.create()
        cls.chatroom.add_member(cls.user)

    def test_chatroom_members(self):
        self.assertEqual(self.chatroom.members.count(), 1)

    def test_chatroom_admins(self):
        self.assertEqual(self.chatroom.allowed_admins.count(), 1)

    def test_chatroom_creator(self):
        self.assertEqual(self.chatroom.get_creator(), self.user)

    def test_chatroom_add_member_not_admin(self):
        new_user = UserFactory.create()
        self.chatroom.add_member(new_user)
        self.assertEqual(self.chatroom.members.count(), 2)
        self.assertEqual(self.chatroom.allowed_admins.count(), 1)
        self.assertEqual(self.chatroom.get_creator(), self.user)
        self.assertFalse(self.chatroom.has_admin_perms(new_user))
        self.assertFalse(self.chatroom.is_creator(new_user))

    def test_chatroom_add_member_admin(self):
        new_user = UserFactory.create()
        self.chatroom.add_member(new_user, admin=True)
        self.assertEqual(self.chatroom.members.count(), 2)
        self.assertEqual(self.chatroom.allowed_admins.count(), 2)
        self.assertEqual(self.chatroom.get_creator(), self.user)
        self.assertTrue(self.chatroom.has_admin_perms(new_user))
        self.assertFalse(self.chatroom.is_creator(new_user))

    def test_chatroom_remove_member(self):
        self.chatroom.remove_member(self.user)
        self.assertEqual(self.chatroom.members.count(), 0)
        self.assertEqual(self.chatroom.allowed_admins.count(), 0)
        self.assertRaises(Membership.DoesNotExist, self.chatroom.get_creator)


class ChatroomModelTwoUsersTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory.create()
        cls.admin_user = UserFactory.create()
        cls.creator_user = UserFactory.create()
        cls.chatroom = GroupChatroomFactory.create()
        cls.chatroom.add_members([cls.creator_user, cls.admin_user, cls.user])
        cls.chatroom.set_admin(cls.admin_user, True)
        cls.user_outside = UserFactory.create()

    def test_chatroom_str(self):
        self.assertEqual(
            str(self.chatroom), f"{self.chatroom.name}, id={self.chatroom.id}"
        )

    def test_chatroom_members(self):
        self.assertEqual(self.chatroom.members.count(), 3)

    def test_chatroom_admins(self):
        self.assertEqual(self.chatroom.allowed_admins.count(), 2)

    def test_chatroom_creator(self):
        self.assertEqual(self.chatroom.get_creator(), self.creator_user)

    def test_chatroom_timestamp(self):
        self.assertIsNotNone(self.chatroom.timestamp)

    def test_chatroom_messages(self):
        self.assertEqual(self.chatroom.messages.count(), 0)

    def test_chatroom_add_member_not_admin(self):
        self.chatroom.add_member(self.user_outside)
        self.assertEqual(self.chatroom.members.count(), 4)
        self.assertEqual(self.chatroom.allowed_admins.count(), 2)
        self.assertEqual(self.chatroom.get_creator(), self.creator_user)
        self.assertFalse(self.chatroom.has_admin_perms(self.user_outside))
        self.assertFalse(self.chatroom.is_creator(self.user_outside))

    def test_chatroom_add_member_admin(self):
        self.chatroom.add_member(self.user_outside, admin=True)
        self.assertEqual(self.chatroom.members.count(), 4)
        self.assertEqual(self.chatroom.allowed_admins.count(), 3)
        self.assertEqual(self.chatroom.get_creator(), self.creator_user)
        self.assertTrue(self.chatroom.has_admin_perms(self.user_outside))
        self.assertFalse(self.chatroom.is_creator(self.user_outside))

    def test_chatroom_remove_member(self):
        self.chatroom.remove_member(self.user)
        self.assertEqual(self.chatroom.members.count(), 2)
        self.assertEqual(self.chatroom.allowed_admins.count(), 2)
        self.assertEqual(self.chatroom.get_creator(), self.creator_user)
        self.assertFalse(self.chatroom.is_member(self.user))

    def test_chatroom_remove_member_creator(self):
        self.chatroom.remove_member(self.creator_user)
        self.assertEqual(self.chatroom.members.count(), 2)
        self.assertEqual(self.chatroom.allowed_admins.count(), 1)
        self.assertEqual(self.chatroom.get_creator(), self.admin_user)
        self.assertFalse(self.chatroom.is_member(self.creator_user))

    def test_chatroom_set_admin_true_on_member(self):
        self.chatroom.set_admin(self.user, True)
        self.assertTrue(self.chatroom.has_admin_perms(self.user))

    def test_chatroom_set_admin_false_on_member(self):
        self.chatroom.set_admin(self.user, False)
        self.assertFalse(self.chatroom.has_admin_perms(self.user))

    def test_chatroom_set_admin_true_on_admin(self):
        self.chatroom.set_admin(self.admin_user, True)
        self.assertTrue(self.chatroom.has_admin_perms(self.admin_user))

    def test_chatroom_set_admin_false_on_admin(self):
        self.chatroom.set_admin(self.admin_user, False)
        self.assertFalse(self.chatroom.has_admin_perms(self.admin_user))

    def test_chatroom_set_admin_true_on_creator(self):
        self.chatroom.set_admin(self.creator_user, True)
        self.assertTrue(self.chatroom.has_admin_perms(self.creator_user))
        self.assertTrue(self.chatroom.is_creator(self.creator_user))

    def test_chatroom_set_admin_false_on_creator(self):
        self.chatroom.set_admin(self.creator_user, False)
        self.assertTrue(self.chatroom.has_admin_perms(self.creator_user))
        self.assertTrue(self.chatroom.is_creator(self.creator_user))


class MessageModelTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.message = MessageFactory()
        cls.chatroom = cls.message.chatroom
        cls.sender = cls.message.sender
        cls.chatroom.add_member(cls.sender)

    def test_message_str(self):
        self.assertEqual(str(self.message), self.message.content)

    def test_message_chatroom(self):
        self.assertEqual(self.message.chatroom, self.chatroom)

    def test_message_sender(self):
        self.assertEqual(self.message.sender, self.sender)

    def test_thread_messages(self):
        thread_message = Message.objects.create(
            chatroom=self.chatroom,
            sender=self.sender,
            content="test",
            parent_message=self.message,
        )
        self.assertEqual(self.message.thread_messages.count(), 1)
        self.assertEqual(self.message.thread_messages.first(), thread_message)
