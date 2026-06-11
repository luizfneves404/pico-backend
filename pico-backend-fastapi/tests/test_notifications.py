import pytest
from arq import Worker
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.community.models import Community, CommunityUser
from app.fcm import fcm_service
from app.fcm.models import DeviceType, FCMDevice
from app.notifications.models import (
    FlowInAppNotification,
    InAppNotification,
)
from app.users.models import User
from tests.conftest import UserClientFactory
from tests.factories import (
    ChoiceFactory,
    CommunityFactory,
    ExternalInAppNotificationFactory,
    FlowFactory,
    FlowInAppNotificationFactory,
    FlowQuestionFactory,
    UserFactory,
)


@pytest.mark.usefixtures("user", "session")
async def test_list_notifications_empty(user_client: AsyncClient):
    """Test listing notifications when user has none."""
    response = await user_client.get("/api/in-app-notifications/list")
    assert response.status_code == 200
    notifications = response.json()
    assert notifications == []


async def test_list_notifications_with_external_notifications(
    user_client: AsyncClient, user: User, session: AsyncSession
):
    """Test listing external notifications."""
    async with session.begin():
        # Create notifications for the user
        notification1 = await ExternalInAppNotificationFactory.create(
            user=user,
            text="Check out our new feature!",
            external_url="https://example.com/feature",
            seen=False,
            session=session,
        )

    async with session.begin():
        notification2 = await ExternalInAppNotificationFactory.create(
            user=user,
            text="System maintenance scheduled",
            external_url="https://example.com/maintenance",
            seen=True,
            session=session,
        )

        # Create notification for another user (shouldn't appear)
        other_user = await UserFactory.create(session=session)
        await ExternalInAppNotificationFactory.create(
            user=other_user,
            text="Other user notification",
            session=session,
        )

    response = await user_client.get("/api/in-app-notifications/list")
    assert response.status_code == 200
    notifications = response.json()
    assert len(notifications) == 2

    # Check notifications are ordered by created_at desc (newest first)
    first_notification = notifications[0]
    assert first_notification["notification_type"] == "external"
    assert first_notification["text"] == "System maintenance scheduled"
    assert first_notification["external_url"] == "https://example.com/maintenance"
    assert first_notification["seen"] is True
    assert first_notification["id"] == notification2.id
    assert "created_at" in first_notification

    second_notification = notifications[1]
    assert second_notification["notification_type"] == "external"
    assert second_notification["text"] == "Check out our new feature!"
    assert second_notification["external_url"] == "https://example.com/feature"
    assert second_notification["seen"] is False
    assert second_notification["id"] == notification1.id


async def test_list_notifications_with_flow_notifications(
    user_client: AsyncClient, user: User, session: AsyncSession
):
    """Test listing flow notifications."""
    async with session.begin():
        # Create flows
        flow1 = await FlowFactory.create(created_by=user, session=session)
        flow2 = await FlowFactory.create(created_by=user, session=session)

        # Create flow notifications
        notification1 = await FlowInAppNotificationFactory.create(
            user=user,
            text="Your flow has new responses!",
            flow=flow1,
            seen=False,
            session=session,
        )
        notification2 = await FlowInAppNotificationFactory.create(
            user=user,
            text="Someone completed your flow",
            flow=flow2,
            seen=True,
            session=session,
        )

    response = await user_client.get("/api/in-app-notifications/list")
    assert response.status_code == 200
    notifications = response.json()
    assert len(notifications) == 2

    # Check first notification (newest)
    first_notification = notifications[0]
    assert first_notification["notification_type"] == "flow"
    assert first_notification["text"] == "Someone completed your flow"
    assert first_notification["flow_id"] == flow2.id
    assert first_notification["seen"] is True
    assert first_notification["id"] == notification2.id

    # Check second notification
    second_notification = notifications[1]
    assert second_notification["notification_type"] == "flow"
    assert second_notification["text"] == "Your flow has new responses!"
    assert second_notification["flow_id"] == flow1.id
    assert second_notification["seen"] is False
    assert second_notification["id"] == notification1.id


async def test_list_notifications_mixed_types(
    user_client: AsyncClient, user: User, session: AsyncSession
):
    """Test listing mixed notification types."""
    async with session.begin():
        flow = await FlowFactory.create(created_by=user, session=session)

        # Create different types of notifications
        await ExternalInAppNotificationFactory.create(
            user=user,
            text="External notification",
            external_url="https://example.com",
            session=session,
        )
        await FlowInAppNotificationFactory.create(
            user=user,
            text="Flow notification",
            flow=flow,
            session=session,
        )

    response = await user_client.get("/api/in-app-notifications/list")
    assert response.status_code == 200
    notifications = response.json()
    assert len(notifications) == 2

    # Verify we have one of each type
    notification_types = {n["notification_type"] for n in notifications}
    assert notification_types == {"external", "flow"}


async def test_count_unseen_notifications(
    user_client: AsyncClient, user: User, session: AsyncSession
):
    """Test counting unseen notifications."""
    async with session.begin():
        # Create notifications with different seen states
        await ExternalInAppNotificationFactory.create(
            user=user, seen=False, session=session
        )
        await ExternalInAppNotificationFactory.create(
            user=user, seen=False, session=session
        )
        await ExternalInAppNotificationFactory.create(
            user=user, seen=True, session=session
        )

        # Create notification for another user
        other_user = await UserFactory.create(
            name="other", username="other", email="other@other.com", session=session
        )
        await ExternalInAppNotificationFactory.create(
            user=other_user, seen=False, session=session
        )

    response = await user_client.get("/api/in-app-notifications/count-unseen")

    assert response.status_code == 200
    count = response.json()
    assert count == 2


async def test_count_unseen_notifications_zero(
    user_client: AsyncClient, user: User, session: AsyncSession
):
    """Test counting when all notifications are seen or no notifications exist."""
    async with session.begin():
        # Create only seen notifications
        await ExternalInAppNotificationFactory.create(
            user=user, seen=True, session=session
        )
        await ExternalInAppNotificationFactory.create(
            user=user, seen=True, session=session
        )

    response = await user_client.get("/api/in-app-notifications/count-unseen")
    assert response.status_code == 200
    count = response.json()
    assert count == 0


async def test_mark_all_as_seen(
    user_client: AsyncClient, user: User, session: AsyncSession
):
    """Test marking all notifications as seen."""
    async with session.begin():
        # Create unseen notifications
        flow = await FlowFactory.create(created_by=user, session=session)

        await ExternalInAppNotificationFactory.create(
            user=user, seen=False, session=session
        )
        await FlowInAppNotificationFactory.create(
            user=user, flow=flow, seen=False, session=session
        )
        await ExternalInAppNotificationFactory.create(
            user=user, seen=True, session=session
        )

        # Create notification for another user
        other_user = await UserFactory.create(session=session)
        other_notification = await ExternalInAppNotificationFactory.create(
            user=other_user, seen=False, session=session
        )

    # count unseen notifications
    response = await user_client.get("/api/in-app-notifications/count-unseen")
    assert response.status_code == 200
    count = response.json()
    assert count == 2

    # Mark all as seen
    response = await user_client.post("/api/in-app-notifications/mark-all-as-seen")
    assert response.status_code == 200

    # Verify all user's notifications are marked as seen
    async with session.begin():
        notifications = await session.execute(
            select(InAppNotification).where(InAppNotification.user_id == user.id)
        )
        user_notifications = notifications.scalars().all()
        assert len(user_notifications) == 3
        assert all(n.seen for n in user_notifications)

        # Verify other user's notification is still unseen
        other_notification_db = await session.get(
            InAppNotification, other_notification.id
        )
        assert other_notification_db is not None
        assert not other_notification_db.seen

    # now count unseen is 0
    response = await user_client.get("/api/in-app-notifications/count-unseen")
    assert response.status_code == 200
    count = response.json()
    assert count == 0


async def test_mark_all_as_seen_idempotent(
    user_client: AsyncClient, user: User, session: AsyncSession
):
    """Test that marking all as seen is idempotent."""
    async with session.begin():
        # Create notifications
        await ExternalInAppNotificationFactory.create(
            user=user, seen=False, session=session
        )
        await ExternalInAppNotificationFactory.create(
            user=user, seen=True, session=session
        )

    # Mark all as seen twice
    response = await user_client.post("/api/in-app-notifications/mark-all-as-seen")
    assert response.status_code == 200

    response = await user_client.post("/api/in-app-notifications/mark-all-as-seen")
    assert response.status_code == 200

    # Verify all are still seen
    async with session.begin():
        notifications = await session.execute(
            select(InAppNotification).where(InAppNotification.user_id == user.id)
        )
        user_notifications = notifications.scalars().all()
        assert all(n.seen for n in user_notifications)


async def test_polymorphic_loading(
    user_client: AsyncClient, user: User, session: AsyncSession
):
    """Test that polymorphic types are loaded correctly."""
    async with session.begin():
        flow = await FlowFactory.create(created_by=user, session=session)

        # Create one of each type
        external = await ExternalInAppNotificationFactory.create(
            user=user,
            text="External",
            external_url="https://test.com",
            session=session,
        )
        flow_notif = await FlowInAppNotificationFactory.create(
            user=user,
            text="Flow",
            flow=flow,
            session=session,
        )

    # Verify correct types are returned from service
    response = await user_client.get("/api/in-app-notifications/list")
    assert response.status_code == 200
    notifications = response.json()

    # Find each notification by ID and verify type
    external_from_response = next(n for n in notifications if n["id"] == external.id)
    assert external_from_response["notification_type"] == "external"
    assert "external_url" in external_from_response
    assert "flow_id" not in external_from_response

    flow_from_response = next(n for n in notifications if n["id"] == flow_notif.id)
    assert flow_from_response["notification_type"] == "flow"
    assert "flow_id" in flow_from_response
    assert "external_url" not in flow_from_response


async def test_notifications_ordering(
    user_client: AsyncClient, user: User, session: AsyncSession
):
    """Test that notifications are ordered by created_at descending."""
    async with session.begin():
        # Create notifications with specific order
        oldest = await ExternalInAppNotificationFactory.create(
            user=user, text="Oldest", session=session
        )
        middle = await ExternalInAppNotificationFactory.create(
            user=user, text="Middle", session=session
        )
        newest = await ExternalInAppNotificationFactory.create(
            user=user, text="Newest", session=session
        )

    response = await user_client.get("/api/in-app-notifications/list")
    assert response.status_code == 200
    notifications = response.json()

    # Verify order (newest first)
    assert notifications[0]["id"] == newest.id
    assert notifications[1]["id"] == middle.id
    assert notifications[2]["id"] == oldest.id


async def test_unauthorized_access(client: AsyncClient):
    """Test that unauthenticated users cannot access notification endpoints."""
    # Test list endpoint
    response = await client.get("/api/in-app-notifications/list")
    assert response.status_code == 401

    # Test count endpoint
    response = await client.get("/api/in-app-notifications/count-unseen")
    assert response.status_code == 401

    # Test mark as seen endpoint
    response = await client.post("/api/in-app-notifications/mark-all-as-seen")
    assert response.status_code == 401


# Integration tests for notification service functions triggered by API endpoints


async def test_notify_user_flow_question_done_via_flow_submission(
    user_client_factory: UserClientFactory,
    session: AsyncSession,
    arq_worker: Worker,
):
    """Test notify_user_flow_question_done by submitting an answer to a flow
    question."""
    users, clients = await user_client_factory(2)
    # Setup: Create flow with question by another user
    async with session.begin():
        flow = await FlowFactory.create(created_by=users[0], session=session)
        flow_question = await FlowQuestionFactory.create(flow=flow, session=session)
        correct_choice = await ChoiceFactory.create(
            question=flow_question.question, is_correct=True, session=session
        )

    # create fcm device
    response = await clients[0].post(
        "/api/fcm_devices",
        json={
            "registration_id": "test_registration_id",
            "device_type": "android",
        },
    )
    assert response.status_code == 200
    fcm_device = response.json()
    assert fcm_device["registration_id"] == "test_registration_id"
    assert fcm_device["device_type"] == "android"

    # check that the device is active
    async with session.begin():
        device = await session.execute(
            select(FCMDevice).where(FCMDevice.user_id == users[0].id)
        )
        device = device.scalar_one_or_none()
        assert device is not None
        assert device.active

    # Act: Submit answer to trigger notification
    answer_data = {
        "question_id": flow_question.question_id,
        "choice_id": correct_choice.id,
    }
    response = await clients[1].post(f"/api/flows/{flow.id}/submit", json=answer_data)
    assert response.status_code == 200

    # Process notification queue
    await arq_worker.async_run()

    # Verify in-app notification was created
    async with session.begin():
        notifications = await session.execute(
            select(InAppNotification).where(InAppNotification.user_id == users[0].id)
        )
        user_notifications = list(notifications.scalars())
        assert len(user_notifications) == 1

        notification = user_notifications[0]
        assert isinstance(notification, FlowInAppNotification)
        assert (
            notification.text
            == f"{users[1].name} respondeu uma questão no seu flow {flow.title}!"
        )
        assert notification.flow_id == flow.id
        assert not notification.seen

    # Verify FCM notification was sent
    fcm_messages = fcm_service.get_last_sent_messages()
    assert len(fcm_messages) == 1
    fcm_message = fcm_messages[0]
    assert (
        fcm_message.notification.title
        == f"{users[1].name} respondeu questão num flow seu!"
    )
    assert (
        fcm_message.notification.body
        == f"O usuário {users[1].name} respondeu uma questão no seu flow {flow.title}"
    )
    assert fcm_message.token == fcm_device["registration_id"]


async def test_notify_communities_flow_posted_via_add_questions_official(
    user_client_factory: UserClientFactory,
    session: AsyncSession,
    arq_worker: Worker,
):
    """Test notify_communities_flow_posted by adding official questions to a flow."""
    users, clients = await user_client_factory(2)
    # Setup: Create flow and community with users
    async with session.begin():
        # Create community with multiple users
        community = await CommunityFactory.create(session=session)

        # Add users to community (including flow creator)
        session.add(CommunityUser(community_id=community.id, user_id=users[0].id))
        session.add(CommunityUser(community_id=community.id, user_id=users[1].id))

        # Create a flow by the current user
        flow = await FlowFactory.create(created_by=users[0], session=session)

    # create the fcm device
    response = await clients[1].post(
        "/api/fcm_devices",
        json={
            "registration_id": "test_registration_id",
            "device_type": "android",
        },
    )
    assert response.status_code == 200
    fcm_device = response.json()
    assert fcm_device["registration_id"] == "test_registration_id"
    assert fcm_device["device_type"] == "android"

    # Act: Add official questions to trigger community notification
    add_questions_data = {
        "question_density": "low",
        "exam_id": None,
        "exam_country_code": "BR",
        "exam_education_level_id": 1,
        "source_year": None,
    }

    response = await clients[0].post(
        f"/api/flows/{flow.id}/add-questions-official", json=add_questions_data
    )
    assert response.status_code == 200

    # Process notification queue
    await arq_worker.async_run()

    # Verify in-app notifications were created for community members (excluding flow
    # creator)
    async with session.begin():
        notifications = await session.execute(
            select(InAppNotification).where(
                InAppNotification.user_id.in_([users[1].id])
            )
        )
        user_notifications = list(notifications.scalars())
        assert len(user_notifications) == 1

        for notification in user_notifications:
            assert isinstance(notification, FlowInAppNotification)
            assert community.name in notification.text
            assert flow.title in notification.text
            assert users[0].name in notification.text
            assert notification.flow_id == flow.id
            assert not notification.seen

    # Verify FCM notifications were sent for community members
    fcm_messages = fcm_service.get_last_sent_messages()
    assert len(fcm_messages) == 1
    fcm_message = fcm_messages[0]

    assert (
        fcm_message.notification.title == f"{users[0].name} postou em {community.name}!"
    )
    assert (
        fcm_message.notification.body
        == f"O usuário {users[0].name} postou o flow {flow.title} em {community.name}"
    )


async def test_notify_community_user_joined_via_user_education_update(
    user_client_factory: UserClientFactory,
    session: AsyncSession,
    arq_worker: Worker,
):
    """Test notify_community_user_joined by updating user education information."""
    users, clients = await user_client_factory(3)

    assert users[0].current_education is not None
    assert users[1].current_education is not None
    assert users[2].current_education is not None

    # create fcm device for user 0
    response = await clients[0].post(
        "/api/fcm_devices",
        json={
            "registration_id": "test_registration_id",
            "device_type": "android",
        },
    )
    assert response.status_code == 200
    fcm_device = response.json()
    assert fcm_device["registration_id"] == "test_registration_id"
    assert fcm_device["device_type"] == "android"

    # Act: Update user 0's education to user 2's education

    update_data = {
        "updates": {
            "current_education": {
                "institution_id": users[2].current_education.institution_id,
                "course_id": users[2].current_education.course_id,
                "education_level_id": users[2].current_education.level_id,
            }
        }
    }

    response = await clients[0].patch("/api/users/me", json=update_data)

    # get user 0's community
    async with session.begin():
        community = await session.execute(
            select(Community).where(Community.users.contains(users[0]))
        )
        community = community.scalar_one_or_none()
        assert community is not None

    # update user 1's education to user 2's education
    update_data = {
        "updates": {
            "current_education": {
                "institution_id": users[2].current_education.institution_id,
                "course_id": users[2].current_education.course_id,
                "education_level_id": users[2].current_education.level_id,
            }
        }
    }

    response = await clients[1].patch("/api/users/me", json=update_data)

    assert response.status_code == 200

    # Process notification queue
    await arq_worker.async_run()

    # Verify FCM notification was sent to user 0 about user 1 joining the community
    fcm_messages = fcm_service.get_last_sent_messages()
    assert len(fcm_messages) == 1
    fcm_message = fcm_messages[0]
    assert (
        f"{users[1].name} entrou em {community.name}!" == fcm_message.notification.title
    )
    assert (
        fcm_message.notification.body
        == f"O usuário {users[1].name} agora faz parte de {community.name} também!"
    )
    assert fcm_message.token == fcm_device["registration_id"]


async def test_notify_flow_question_done_only_when_different_user(
    user_client: AsyncClient,
    user: User,
    session: AsyncSession,
    arq_worker: Worker,
):
    """Test that notify_user_flow_question_done is NOT triggered when user answers their
    own flow."""
    # Setup: Create flow by the current user
    async with session.begin():
        flow = await FlowFactory.create(created_by=user, session=session)
        flow_question = await FlowQuestionFactory.create(flow=flow, session=session)
        correct_choice = await ChoiceFactory.create(
            question=flow_question.question, is_correct=True, session=session
        )

    # Act: Submit answer to own flow
    answer_data = {
        "question_id": flow_question.question_id,
        "choice_id": correct_choice.id,
    }
    response = await user_client.post(f"/api/flows/{flow.id}/submit", json=answer_data)
    assert response.status_code == 200

    # Process notification queue
    await arq_worker.async_run()

    # Verify no in-app notification was created (user answering own flow)
    async with session.begin():
        notifications = await session.execute(
            select(InAppNotification).where(InAppNotification.user_id == user.id)
        )
        user_notifications = list(notifications.scalars())
        # Should be empty since user answered their own flow
        flow_notifications = [
            n for n in user_notifications if isinstance(n, FlowInAppNotification)
        ]
        assert len(flow_notifications) == 0


async def test_notify_communities_flow_posted_only_notifies_community_members(
    user_client_factory: UserClientFactory,
    session: AsyncSession,
    arq_worker: Worker,
):
    """Test that notify_communities_flow_posted only notifies users in the same
    communities as the flow creator."""
    users, clients = await user_client_factory(3)

    # Setup: Create communities and users
    async with session.begin():
        # Create two communities
        community1 = await CommunityFactory.create(session=session)
        community2 = await CommunityFactory.create(session=session)

        # Add flow creator and user_in_same_community to community1
        session.add(CommunityUser(community_id=community1.id, user_id=users[0].id))
        session.add(CommunityUser(community_id=community1.id, user_id=users[1].id))

        # Add user_in_different_community to community2 only
        session.add(CommunityUser(community_id=community2.id, user_id=users[2].id))

        # user_in_no_community is not added to any community

        # Create a flow by the current user
        flow = await FlowFactory.create(created_by=users[0], session=session)

    # create fcm device for user 1
    response = await clients[1].post(
        "/api/fcm_devices",
        json={
            "registration_id": "test_registration_id",
            "device_type": "android",
        },
    )
    assert response.status_code == 200
    fcm_device = response.json()
    assert fcm_device["registration_id"] == "test_registration_id"
    assert fcm_device["device_type"] == "android"

    # Act: Add questions to trigger community notification
    add_questions_data = {
        "question_density": "low",
        "exam_id": None,
        "exam_country_code": "BR",
        "exam_education_level_id": 1,
        "source_year": None,
    }

    response = await clients[0].post(
        f"/api/flows/{flow.id}/add-questions-official", json=add_questions_data
    )
    assert response.status_code == 200

    # Process notification queue
    await arq_worker.async_run()

    # Verify in-app notification was created only for user in the same community
    async with session.begin():
        notifications = await session.execute(
            select(InAppNotification).where(
                InAppNotification.user_id.in_(
                    [
                        users[1].id,
                        users[2].id,
                        users[0].id,
                    ]
                )
            )
        )
        user_notifications = list(notifications.scalars())

        # Should only have one notification for user_in_same_community
        assert len(user_notifications) == 1
        assert user_notifications[0].user_id == users[1].id

    # Verify FCM notification was sent only for user in same community
    fcm_messages = fcm_service.get_last_sent_messages()
    assert len(fcm_messages) == 1
    fcm_message = fcm_messages[0]
    assert (
        f"{users[0].name} postou em {community1.name}!"
        == fcm_message.notification.title
    )
    assert (
        fcm_message.notification.body
        == f"O usuário {users[0].name} postou o flow {flow.title} em {community1.name}"
    )
    assert fcm_message.token == fcm_device["registration_id"]


async def test_create_or_update_device_creates_new(
    session: AsyncSession,
):
    async with session.begin():
        user = await UserFactory.create(session=session)

    # Act
    async with session.begin():
        device = await fcm_service.create_or_update_device(
            session, user.id, "reg_token_new", DeviceType.ANDROID
        )

    # Assert
    async with session.begin():
        result = await session.execute(
            select(FCMDevice).where(FCMDevice.user_id == user.id)
        )
        db_device = result.scalar_one_or_none()
        assert db_device is not None
        assert device.id == db_device.id
        assert db_device.registration_id == "reg_token_new"
        assert db_device.device_type == DeviceType.ANDROID
        assert db_device.active is True


async def test_create_or_update_device_updates_device_type_same_token(
    session: AsyncSession,
):
    async with session.begin():
        user = await UserFactory.create(session=session)
        # Existing device for the same user and token
        session.add(
            FCMDevice(
                user_id=user.id,
                registration_id="reg_token_same",
                device_type=DeviceType.ANDROID,
                active=True,
            )
        )

    # Act: update same token with different device type
    async with session.begin():
        device = await fcm_service.create_or_update_device(
            session, user.id, "reg_token_same", DeviceType.IOS
        )

    # Assert
    async with session.begin():
        result = await session.execute(
            select(FCMDevice).where(FCMDevice.user_id == user.id)
        )
        db_device = result.scalar_one_or_none()
        assert db_device is not None
        assert device.id == db_device.id
        assert db_device.registration_id == "reg_token_same"
        assert db_device.device_type == DeviceType.IOS
        assert db_device.active is True


async def test_create_or_update_device_reassigns_token_to_new_user(
    session: AsyncSession,
):
    # Setup: user A has token t1, user B has token t2
    async with session.begin():
        user_a = await UserFactory.create(session=session)
        user_b = await UserFactory.create(session=session)
        session.add(
            FCMDevice(
                user_id=user_a.id,
                registration_id="t1",
                device_type=DeviceType.ANDROID,
                active=True,
            )
        )
        session.add(
            FCMDevice(
                user_id=user_b.id,
                registration_id="t2",
                device_type=DeviceType.ANDROID,
                active=True,
            )
        )

    # Act: assign t1 to user B
    async with session.begin():
        device = await fcm_service.create_or_update_device(
            session, user_b.id, "t1", DeviceType.IOS
        )

    # Assert: user B now has t1, user A has no device, t2 is gone
    async with session.begin():
        res_t1 = await session.execute(
            select(FCMDevice).where(FCMDevice.registration_id == "t1")
        )
        dev_t1 = res_t1.scalar_one_or_none()
        assert dev_t1 is not None
        assert device.id == dev_t1.id
        assert dev_t1.user_id == user_b.id
        assert dev_t1.device_type == DeviceType.IOS
        assert dev_t1.active is True

        res_user_a = await session.execute(
            select(FCMDevice).where(FCMDevice.user_id == user_a.id)
        )
        assert res_user_a.scalar_one_or_none() is None

        res_t2 = await session.execute(
            select(FCMDevice).where(FCMDevice.registration_id == "t2")
        )
        assert res_t2.scalar_one_or_none() is None


async def test_create_or_update_device_replaces_existing_user_device_with_new_token(
    session: AsyncSession,
):
    async with session.begin():
        user = await UserFactory.create(session=session)
        session.add(
            FCMDevice(
                user_id=user.id,
                registration_id="old_token",
                device_type=DeviceType.WEB,
                active=True,
            )
        )

    # Act: replace with a new token
    async with session.begin():
        device = await fcm_service.create_or_update_device(
            session, user.id, "new_token", DeviceType.WEB
        )

    # Assert: user now has only new_token, old_token is gone
    async with session.begin():
        res_user = await session.execute(
            select(FCMDevice).where(FCMDevice.user_id == user.id)
        )
        db_device = res_user.scalar_one_or_none()
        assert db_device is not None
        assert device.id == db_device.id
        assert db_device.registration_id == "new_token"

        res_old = await session.execute(
            select(FCMDevice).where(FCMDevice.registration_id == "old_token")
        )
        assert res_old.scalar_one_or_none() is None


async def test_create_or_update_device_reactivates_inactive_token(
    session: AsyncSession,
):
    # Setup: token belongs to user A and is inactive
    async with session.begin():
        user_a = await UserFactory.create(session=session)
        user_b = await UserFactory.create(session=session)
        session.add(
            FCMDevice(
                user_id=user_a.id,
                registration_id="inactive_token",
                device_type=DeviceType.ANDROID,
                active=False,
            )
        )

    # Act: assign same token to user B, should set active=True
    async with session.begin():
        device = await fcm_service.create_or_update_device(
            session, user_b.id, "inactive_token", DeviceType.IOS
        )

    # Assert
    async with session.begin():
        res = await session.execute(
            select(FCMDevice).where(FCMDevice.registration_id == "inactive_token")
        )
        db_device = res.scalar_one_or_none()
        assert db_device is not None
        assert device.id == db_device.id
        assert db_device.user_id == user_b.id
        assert db_device.device_type == DeviceType.IOS
        assert db_device.active is True


async def test_create_or_update_device_is_idempotent(
    session: AsyncSession,
):
    async with session.begin():
        user = await UserFactory.create(session=session)

    # Act: call twice with same data
    async with session.begin():
        await fcm_service.create_or_update_device(
            session, user.id, "same_token", DeviceType.ANDROID
        )
    async with session.begin():
        await fcm_service.create_or_update_device(
            session, user.id, "same_token", DeviceType.ANDROID
        )

    # Assert: single row for the token and user with latest values
    async with session.begin():
        res = await session.execute(
            select(FCMDevice).where(FCMDevice.registration_id == "same_token")
        )
        db_device = res.scalar_one_or_none()
        assert db_device is not None
        assert db_device.user_id == user.id
        assert db_device.device_type == DeviceType.ANDROID
        assert db_device.active is True
