from unittest.mock import MagicMock, patch

import api.services.chatroom_service as chatroom_service
from api.models import MembershipRole, Message
from api.tests.factories import GroupChatroomFactory, MembershipFactory, UserFactory
from shared.testing import PatchingAndRedisTestCase


class ChatroomServiceBasicTestCase(PatchingAndRedisTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user_creator = UserFactory.create()
        cls.user_not_admin = UserFactory.create()
        cls.new_user = UserFactory.create()

        # Create chatrooms
        cls.chatroom1 = GroupChatroomFactory.create()
        cls.chatroom2 = GroupChatroomFactory.create()

        # Define memberships
        MembershipFactory.create(
            user=cls.user_creator, chatroom=cls.chatroom1, role=MembershipRole.CREATOR
        )
        MembershipFactory.create(
            user=cls.user_not_admin, chatroom=cls.chatroom1, role=MembershipRole.MEMBER
        )
        MembershipFactory.create(
            user=cls.user_creator, chatroom=cls.chatroom2, role=MembershipRole.CREATOR
        )

    def setUp(self):
        super().setUp()
        self.addCleanup(patch.stopall)
        self.mock_asend_message = patch(
            "api.services.message_service.asend_message",
            autospec=True,
        ).start()
        self.mock_notification_batch = MagicMock(
            spec=chatroom_service.notifications_utils.NotificationBatch
        )
        self.mock_prepare_chatroom_rename_notifications = patch(
            "api.services.chatroom_service.notifications_utils.prepare_chatroom_rename_notifications",
        ).start()
        self.mock_prepare_chatroom_rename_notifications.return_value = (
            self.mock_notification_batch
        )
        self.mock_prepare_add_member_notifications_on_create = patch(
            "api.services.chatroom_service.notifications_utils.prepare_add_member_notifications_on_create",
        ).start()
        self.mock_prepare_add_member_notifications_on_create.return_value = (
            self.mock_notification_batch
        )

    async def test_list_chatrooms_for_user(self):
        chatrooms = (
            await chatroom_service.list_chatrooms_for_user_with_members_is_admin(
                self.user_creator
            )
        )
        self.assertEqual(len(chatrooms), 2)
        self.assertTrue(any(chatroom.id == self.chatroom1.id for chatroom in chatrooms))
        self.assertTrue(any(chatroom.id == self.chatroom2.id for chatroom in chatrooms))

        self.assertTrue(any(member.is_admin for member in chatrooms[0].members.all()))
        self.assertFalse(
            any(
                member.is_admin and member != self.user_creator
                for member in chatrooms[0].members.all()
            )
        )

        chatrooms = (
            await chatroom_service.list_chatrooms_for_user_with_members_is_admin(
                self.user_not_admin
            )
        )
        self.assertEqual(len(chatrooms), 1)
        self.assertTrue(chatrooms[0].id, self.chatroom1.id)
        self.assertFalse(
            any(
                member.is_admin
                for member in chatrooms[0].members.all()
                if member == self.user_not_admin
            )
        )

    async def test_create_group_chatroom(self):
        creator = self.user_creator
        member = self.user_not_admin

        chatroom = await chatroom_service.create_group_chatroom(
            creator, "new chatroom", [creator.id, member.id]
        )

        self.assertTrue(await chatroom.ais_member(creator))
        self.assertTrue(await chatroom.ais_creator(creator))

        self.assertEqual(chatroom.name, "new chatroom")

        self.mock_prepare_add_member_notifications_on_create.assert_called_once()

        self.mock_notification_batch.send_async.assert_awaited_once()

        actual_call = (
            self.mock_prepare_add_member_notifications_on_create.call_args_list[0]
        )
        expected_members = {creator, member}
        actual_members = set(actual_call.args[0])

        self.assertEqual(
            actual_members,
            expected_members,
            "Members passed to notifications do not match expected values",
        )

        self.assertEqual(actual_call.args[1], chatroom.id)
        self.assertEqual(actual_call.args[2], creator)

    async def test_rename_chatroom_by_id(self):
        await chatroom_service.rename_chatroom_by_id(
            self.chatroom1.id, self.user_creator, "new name"
        )
        await self.chatroom1.arefresh_from_db()
        self.assertEqual(self.chatroom1.name, "new name")

        self.mock_prepare_chatroom_rename_notifications.assert_called_once()

        self.mock_notification_batch.send_async.assert_awaited_once()

        actual_call = self.mock_prepare_chatroom_rename_notifications.call_args_list[0]

        expected_member_ids = {
            self.user_creator.id,
            self.user_not_admin.id,
        }

        actual_member_ids = set(actual_call.args[0])

        self.assertEqual(
            actual_member_ids,
            expected_member_ids,
            "Member IDs do not match expected values",
        )

        self.assertEqual(actual_call.args[1], self.chatroom1.id)
        self.assertEqual(actual_call.args[2], self.user_creator)
        self.assertEqual(actual_call.args[3], "new name")

        self.mock_asend_message.assert_awaited_once_with(
            sender="system",
            content=f"User {self.user_creator.username} renamed the chatroom to 'new name'",
            chatroom=self.chatroom1,
        )

    async def test_rename_chatroom_by_id_not_found(self):
        with self.assertRaises(chatroom_service.ChatroomForUserNotFound):
            await chatroom_service.rename_chatroom_by_id(
                9999, self.user_creator, "new name"
            )

    async def test_rename_chatroom_by_id_not_member(self):
        with self.assertRaises(chatroom_service.ChatroomForUserNotFound):
            await chatroom_service.rename_chatroom_by_id(
                self.chatroom2.id, self.user_not_admin, "new name"
            )

    async def test_rename_chatroom_by_id_permission_denied(self):
        with self.assertRaises(chatroom_service.ChatroomPermissionDenied):
            await chatroom_service.rename_chatroom_by_id(
                self.chatroom1.id, self.user_not_admin, "new name"
            )

    async def test_create_predefined_chatroom_with_messages(self):
        messages = [
            {
                "username": self.user_creator.username,
                "content": "Hello",
            },
            {
                "username": self.user_not_admin.username,
                "content": "Hi",
            },
        ]
        chatroom = await chatroom_service.create_predefined_chatroom_with_messages(
            "new chatroom", self.user_creator, [self.user_not_admin], messages
        )
        self.assertTrue(await chatroom.ais_member(self.user_creator))
        self.assertTrue(await chatroom.ais_member(self.user_not_admin))
        self.assertEqual(chatroom.name, "new chatroom")

        messages_in_db = [
            message
            async for message in Message.objects.select_related("sender")
            .order_by("id")
            .all()
        ]
        self.assertEqual(len(messages_in_db), 2)
        self.assertEqual(messages_in_db[0].content, "Hello")
        self.assertEqual(messages_in_db[0].sender, self.user_creator)
        self.assertEqual(messages_in_db[1].content, "Hi")
        self.assertEqual(messages_in_db[1].sender, self.user_not_admin)


class ChatroomServiceMembershipTestCase(PatchingAndRedisTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user_creator = UserFactory.create()
        cls.user_not_admin = UserFactory.create()
        cls.new_user = UserFactory.create()

        # Create chatrooms
        cls.chatroom1 = GroupChatroomFactory.create()
        cls.chatroom2 = GroupChatroomFactory.create()

        # Define memberships
        MembershipFactory.create(
            user=cls.user_creator, chatroom=cls.chatroom1, role=MembershipRole.CREATOR
        )
        MembershipFactory.create(
            user=cls.user_not_admin, chatroom=cls.chatroom1, role=MembershipRole.MEMBER
        )
        MembershipFactory.create(
            user=cls.user_creator, chatroom=cls.chatroom2, role=MembershipRole.CREATOR
        )

    def setUp(self):
        super().setUp()
        self.addCleanup(patch.stopall)
        self.mock_asend_message = patch(
            "api.services.message_service.asend_message",
            autospec=True,
        ).start()

        self.mock_notification_batch = MagicMock(
            spec=chatroom_service.notifications_utils.NotificationBatch
        )
        self.mock_prepare_leave_notifications = patch(
            "api.services.chatroom_service.notifications_utils.prepare_leave_notifications",
        ).start()
        self.mock_prepare_leave_notifications.return_value = (
            self.mock_notification_batch
        )
        self.mock_prepare_add_member_notifications = patch(
            "api.services.chatroom_service.notifications_utils.prepare_add_member_notifications",
        ).start()
        self.mock_prepare_add_member_notifications.return_value = (
            self.mock_notification_batch
        )
        self.mock_prepare_remove_member_notifications = patch(
            "api.services.chatroom_service.notifications_utils.prepare_remove_member_notifications",
        ).start()
        self.mock_prepare_remove_member_notifications.return_value = (
            self.mock_notification_batch
        )

    async def test_leave_chatroom_by_id(self):
        await chatroom_service.leave_chatroom_by_id(
            self.chatroom1.id, self.user_not_admin
        )
        self.assertFalse(await self.chatroom1.ais_member(self.user_not_admin))

        self.mock_prepare_leave_notifications.assert_called_once()

        self.mock_notification_batch.send_async.assert_awaited_once()

        actual_call = self.mock_prepare_leave_notifications.call_args_list[0]

        expected_member_ids = {self.user_creator.id, self.user_not_admin.id}

        actual_member_ids = set(actual_call.args[0])

        self.assertEqual(
            actual_member_ids,
            expected_member_ids,
            "Member IDs do not match expected values",
        )

        self.assertEqual(actual_call.args[1], self.chatroom1.id)
        self.assertEqual(actual_call.args[2], self.user_not_admin)
        self.mock_asend_message.assert_awaited_once_with(
            sender="system",
            content=f"User {self.user_not_admin.username} left the chatroom",
            chatroom=self.chatroom1,
        )

    async def test_leave_chatroom_by_id_not_found(self):
        with self.assertRaises(chatroom_service.ChatroomForUserNotFound):
            await chatroom_service.leave_chatroom_by_id(
                self.chatroom1.id, self.new_user
            )

    async def test_add_member_by_chatroom_id_user_username(self):
        await chatroom_service.add_member_by_chatroom_id_user_username(
            self.chatroom1.id, self.user_creator, self.new_user.username
        )
        self.assertTrue(await self.chatroom1.ais_member(self.new_user))

        self.mock_prepare_add_member_notifications.assert_called_once()

        self.mock_notification_batch.send_async.assert_awaited_once()

        actual_call = self.mock_prepare_add_member_notifications.call_args_list[0]

        expected_member_ids = {
            self.user_creator.id,
            self.user_not_admin.id,
            self.new_user.id,
        }

        actual_member_ids = set(actual_call.args[0])

        self.assertEqual(
            actual_member_ids,
            expected_member_ids,
            "Member IDs do not match expected values",
        )

        self.assertEqual(actual_call.args[1], self.chatroom1.id)
        self.assertEqual(actual_call.args[2], self.user_creator)
        self.assertEqual(actual_call.args[3], self.new_user)
        self.mock_asend_message.assert_awaited_once_with(
            sender="system",
            content=f"User {self.user_creator.username} added user {self.new_user.username}",
            chatroom=self.chatroom1,
        )

    async def test_add_member_by_chatroom_id_user_username_by_user_not_member(self):
        with self.assertRaises(chatroom_service.ChatroomForUserNotFound):
            await chatroom_service.add_member_by_chatroom_id_user_username(
                self.chatroom2.id, self.user_not_admin, self.new_user.username
            )

    async def test_add_member_by_chatroom_id_user_username_permission_denied(self):
        with self.assertRaises(chatroom_service.ChatroomPermissionDenied):
            await chatroom_service.add_member_by_chatroom_id_user_username(
                self.chatroom1.id, self.user_not_admin, self.new_user.username
            )

    async def test_add_member_by_chatroom_id_user_username_to_user_not_found(self):
        with self.assertRaises(chatroom_service.ToUserNotFound):
            await chatroom_service.add_member_by_chatroom_id_user_username(
                self.chatroom1.id, self.user_creator, "notfound"
            )

    async def test_add_member_by_chatroom_id_user_username_to_user_already_member(self):
        with self.assertRaises(chatroom_service.AlreadyMember):
            await chatroom_service.add_member_by_chatroom_id_user_username(
                self.chatroom1.id, self.user_creator, self.user_not_admin.username
            )

    async def test_remove_member_by_chatroom_id_user_username(self):
        await chatroom_service.remove_member_by_chatroom_id_user_username(
            self.chatroom1.id, self.user_creator, self.user_not_admin.username
        )
        self.assertFalse(await self.chatroom1.ais_member(self.user_not_admin))

        self.mock_prepare_remove_member_notifications.assert_called_once()

        self.mock_notification_batch.send_async.assert_awaited_once()

        actual_call = self.mock_prepare_remove_member_notifications.call_args_list[0]

        expected_member_ids = {
            self.user_creator.id,
            self.user_not_admin.id,
        }

        actual_member_ids = set(actual_call.args[0])

        self.assertEqual(
            actual_member_ids,
            expected_member_ids,
            "Member IDs do not match expected values",
        )

        self.assertEqual(actual_call.args[1], self.chatroom1.id)
        self.assertEqual(actual_call.args[2], self.user_creator)
        self.assertEqual(actual_call.args[3], self.user_not_admin)
        self.mock_asend_message.assert_awaited_once_with(
            sender="system",
            content=f"User {self.user_creator.username} removed user {self.user_not_admin.username}",
            chatroom=self.chatroom1,
        )

    async def test_remove_member_by_chatroom_id_user_username_by_user_not_member(self):
        with self.assertRaises(chatroom_service.ChatroomForUserNotFound):
            await chatroom_service.remove_member_by_chatroom_id_user_username(
                self.chatroom2.id, self.user_not_admin, self.user_creator.username
            )

    async def test_remove_member_by_chatroom_id_user_username_permission_denied(self):
        with self.assertRaises(chatroom_service.ChatroomPermissionDenied):
            await chatroom_service.remove_member_by_chatroom_id_user_username(
                self.chatroom1.id, self.user_not_admin, self.user_creator.username
            )

    async def test_remove_member_by_chatroom_id_user_username_to_user_not_found(self):
        with self.assertRaises(chatroom_service.ToUserNotFound):
            await chatroom_service.remove_member_by_chatroom_id_user_username(
                self.chatroom1.id, self.user_creator, "notfound"
            )

    async def test_remove_member_by_chatroom_id_user_username_to_user_not_member(self):
        with self.assertRaises(chatroom_service.NotMember):
            await chatroom_service.remove_member_by_chatroom_id_user_username(
                self.chatroom1.id, self.user_creator, self.new_user.username
            )

    async def test_remove_member_by_chatroom_id_user_username_cannot_remove_creator(
        self,
    ):
        with self.assertRaises(chatroom_service.CannotRemoveCreator):
            await chatroom_service.remove_member_by_chatroom_id_user_username(
                self.chatroom1.id, self.user_creator, self.user_creator.username
            )


class ChatroomServiceAdminTestCase(PatchingAndRedisTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user_creator = UserFactory.create()
        cls.user_to_be_admin = UserFactory.create()
        cls.user_not_admin = UserFactory.create()
        cls.user_admin = UserFactory.create()
        cls.user_outside = UserFactory.create()

        cls.chatroom = GroupChatroomFactory.create()

        MembershipFactory.create(
            user=cls.user_creator, chatroom=cls.chatroom, role=MembershipRole.CREATOR
        )
        MembershipFactory.create(
            user=cls.user_admin, chatroom=cls.chatroom, role=MembershipRole.ADMIN
        )
        MembershipFactory.create(
            user=cls.user_to_be_admin, chatroom=cls.chatroom, role=MembershipRole.MEMBER
        )
        MembershipFactory.create(
            user=cls.user_not_admin, chatroom=cls.chatroom, role=MembershipRole.MEMBER
        )

    def setUp(self):
        super().setUp()
        self.addCleanup(patch.stopall)
        self.mock_notification_batch = MagicMock(
            spec=chatroom_service.notifications_utils.NotificationBatch
        )
        self.mock_prepare_make_admin_notifications = patch(
            "api.services.chatroom_service.notifications_utils.prepare_make_admin_notifications",
        ).start()
        self.mock_prepare_make_admin_notifications.return_value = (
            self.mock_notification_batch
        )
        self.mock_prepare_remove_admin_notifications = patch(
            "api.services.chatroom_service.notifications_utils.prepare_remove_admin_notifications",
        ).start()
        self.mock_prepare_remove_admin_notifications.return_value = (
            self.mock_notification_batch
        )

    async def test_make_admin_by_chatroom_id_user_username(self):
        await chatroom_service.make_admin_by_chatroom_id_user_username(
            self.chatroom.id, self.user_creator, self.user_to_be_admin.username
        )
        self.assertTrue(await self.chatroom.ahas_admin_perms(self.user_to_be_admin))

        self.mock_prepare_make_admin_notifications.assert_called_once()

        self.mock_notification_batch.send_async.assert_awaited_once()

        actual_call = self.mock_prepare_make_admin_notifications.call_args_list[0]

        expected_member_ids = {
            self.user_creator.id,
            self.user_admin.id,
            self.user_to_be_admin.id,
            self.user_not_admin.id,
        }

        actual_member_ids = set(actual_call.args[0])

        self.assertEqual(
            actual_member_ids,
            expected_member_ids,
            "Member IDs do not match expected values",
        )

        self.assertEqual(actual_call.args[1], self.chatroom.id)
        self.assertEqual(actual_call.args[2], self.user_creator)
        self.assertEqual(actual_call.args[3], self.user_to_be_admin)

    async def test_make_admin_by_chatroom_id_user_username_by_user_not_member(self):
        with self.assertRaises(chatroom_service.ChatroomForUserNotFound):
            await chatroom_service.make_admin_by_chatroom_id_user_username(
                self.chatroom.id, self.user_outside, self.user_to_be_admin.username
            )

    async def test_make_admin_by_chatroom_id_user_username_permission_denied(self):
        with self.assertRaises(chatroom_service.ChatroomPermissionDenied):
            await chatroom_service.make_admin_by_chatroom_id_user_username(
                self.chatroom.id, self.user_to_be_admin, self.user_not_admin.username
            )

    async def test_make_admin_by_chatroom_id_user_username_to_user_not_found(self):
        with self.assertRaises(chatroom_service.ToUserNotFound):
            await chatroom_service.make_admin_by_chatroom_id_user_username(
                self.chatroom.id, self.user_creator, "notfound"
            )

    async def test_make_admin_by_chatroom_id_user_username_to_user_not_member(self):
        with self.assertRaises(chatroom_service.NotMember):
            await chatroom_service.make_admin_by_chatroom_id_user_username(
                self.chatroom.id, self.user_creator, self.user_outside.username
            )

    async def test_make_admin_by_chatroom_id_user_username_already_admin(self):
        with self.assertRaises(chatroom_service.AlreadyAdmin):
            await chatroom_service.make_admin_by_chatroom_id_user_username(
                self.chatroom.id, self.user_creator, self.user_admin.username
            )

    async def test_remove_admin_by_chatroom_id_user_username(self):
        await chatroom_service.remove_admin_by_chatroom_id_user_username(
            self.chatroom.id, self.user_creator, self.user_admin.username
        )
        self.assertFalse(await self.chatroom.ahas_admin_perms(self.user_admin))

        self.mock_prepare_remove_admin_notifications.assert_called_once()

        self.mock_notification_batch.send_async.assert_awaited_once()

        actual_call = self.mock_prepare_remove_admin_notifications.call_args_list[0]

        expected_member_ids = {
            self.user_creator.id,
            self.user_to_be_admin.id,
            self.user_admin.id,
            self.user_not_admin.id,
        }

        actual_member_ids = set(actual_call.args[0])

        self.assertEqual(
            actual_member_ids,
            expected_member_ids,
            "Member IDs do not match expected values",
        )

        self.assertEqual(actual_call.args[1], self.chatroom.id)
        self.assertEqual(actual_call.args[2], self.user_creator)
        self.assertEqual(actual_call.args[3], self.user_admin)

    async def test_remove_admin_by_chatroom_id_user_username_by_user_not_member(self):
        with self.assertRaises(chatroom_service.ChatroomForUserNotFound):
            await chatroom_service.remove_admin_by_chatroom_id_user_username(
                self.chatroom.id, self.user_outside, self.user_admin.username
            )

    async def test_remove_admin_by_chatroom_id_user_username_permission_denied(self):
        with self.assertRaises(chatroom_service.ChatroomPermissionDenied):
            await chatroom_service.remove_admin_by_chatroom_id_user_username(
                self.chatroom.id, self.user_to_be_admin, self.user_admin.username
            )

    async def test_remove_admin_by_chatroom_id_user_username_to_user_not_found(self):
        with self.assertRaises(chatroom_service.ToUserNotFound):
            await chatroom_service.remove_admin_by_chatroom_id_user_username(
                self.chatroom.id, self.user_creator, "notfound"
            )

    async def test_remove_admin_by_chatroom_id_user_username_to_user_not_member(self):
        with self.assertRaises(chatroom_service.NotMember):
            await chatroom_service.remove_admin_by_chatroom_id_user_username(
                self.chatroom.id, self.user_creator, self.user_outside.username
            )

    async def test_remove_admin_by_chatroom_id_user_username_to_user_not_admin(self):
        with self.assertRaises(chatroom_service.NotAdmin):
            await chatroom_service.remove_admin_by_chatroom_id_user_username(
                self.chatroom.id, self.user_creator, self.user_not_admin.username
            )

    async def test_remove_admin_by_chatroom_id_user_username_cannot_remove_creator(
        self,
    ):
        with self.assertRaises(chatroom_service.CannotRemoveAdminCreator):
            await chatroom_service.remove_admin_by_chatroom_id_user_username(
                self.chatroom.id, self.user_creator, self.user_creator.username
            )


class ChatroomServiceGetChatroomForUserTestCase(PatchingAndRedisTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user_creator = UserFactory.create()
        cls.user_member = UserFactory.create()
        cls.user_outside = UserFactory.create()
        cls.chatroom = GroupChatroomFactory.create()
        cls.chatroom.add_members([cls.user_creator, cls.user_member])

    async def test_get_chatroom_for_user_member(self):
        chatroom = await chatroom_service.aget_chatroom_for_user(
            self.user_member, self.chatroom.id
        )
        self.assertEqual(chatroom, self.chatroom)

        self.assertTrue(any(member.is_admin for member in chatroom.members.all()))
        self.assertFalse(
            any(
                member.is_admin and member != self.user_creator
                for member in chatroom.members.all()
            )
        )

    async def test_get_chatroom_for_user_creator(self):
        chatroom = await chatroom_service.aget_chatroom_for_user(
            self.user_creator, self.chatroom.id
        )
        self.assertEqual(chatroom, self.chatroom)

        self.assertTrue(any(member.is_admin for member in chatroom.members.all()))
        self.assertTrue(
            any(
                member.is_admin and member == self.user_creator
                for member in chatroom.members.all()
            )
        )

    async def test_get_chatroom_for_user_not_member(self):
        with self.assertRaises(ValueError):
            await chatroom_service.aget_chatroom_for_user(
                self.user_outside, self.chatroom.id
            )

    async def test_get_chatroom_for_user_not_found(self):
        with self.assertRaises(ValueError):
            await chatroom_service.aget_chatroom_for_user(self.user_member, 9999)

    async def test_get_chatroom_for_user_not_member_not_found(self):
        with self.assertRaises(ValueError):
            await chatroom_service.aget_chatroom_for_user(self.user_outside, 9999)
