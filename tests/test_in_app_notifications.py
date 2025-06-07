from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.in_app_notifications.models import (
    InAppNotification,
)
from app.users.models import User
from tests.factories import (
    ExternalInAppNotificationFactory,
    FlowFactory,
    FlowInAppNotificationFactory,
    UserFactory,
)


async def test_list_notifications_empty(
    user_client: AsyncClient, user: User, session: AsyncSession
):
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
