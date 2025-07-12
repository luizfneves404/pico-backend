import logging
from collections import defaultdict
from typing import Literal, overload

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.community.models import Community
from app.fcm import fcm_service
from app.flows.models import Flow
from app.notifications.models import (
    ExternalInAppNotification,
    FlowInAppNotification,
    InAppNotification,
)
from app.users.models import User

logger = logging.getLogger(__name__)


async def list_notifications(
    db_session: AsyncSession,
    *,
    user_id: int,
) -> list[ExternalInAppNotification | FlowInAppNotification]:
    query = (
        select(InAppNotification)
        .where(InAppNotification.user_id == user_id)
        .order_by(InAppNotification.created_at.desc(), InAppNotification.id.desc())
    )
    result = await db_session.execute(query)
    notifications = list(result.scalars())
    return notifications  # type: ignore # i don't know how to do the correct type hints


async def count_unseen_notifications_for_user(
    db_session: AsyncSession,
    *,
    user_id: int,
) -> int:
    return (await count_unseen_notifications_for_users(db_session, user_ids=[user_id]))[
        user_id
    ]


async def count_unseen_notifications_for_users(
    db_session: AsyncSession,
    *,
    user_ids: list[int],
) -> dict[int, int]:
    counts: defaultdict[int, int] = defaultdict(int)

    query = (
        select(InAppNotification.user_id, func.count(InAppNotification.id))
        .where(
            InAppNotification.user_id.in_(user_ids), InAppNotification.seen.is_(False)
        )
        .group_by(InAppNotification.user_id)
    )
    result = await db_session.execute(query)

    for user_id, count in result.tuples():
        counts[user_id] = count

    return counts


async def mark_all_as_seen(
    db_session: AsyncSession,
    *,
    user_id: int,
) -> None:
    query = (
        update(InAppNotification)
        .where(InAppNotification.user_id == user_id)
        .values(seen=True)
    )
    await db_session.execute(query)


@overload
def create_notification(
    db_session: AsyncSession,
    *,
    user_id: int,
    text: str,
    notification_type: Literal["external"],
    external_url: str,
) -> None:
    pass


@overload
def create_notification(
    db_session: AsyncSession,
    *,
    user_id: int,
    text: str,
    notification_type: Literal["flow"],
    flow_id: int,
) -> None:
    pass


def create_notification(
    db_session: AsyncSession,
    *,
    user_id: int,
    text: str,
    notification_type: Literal["flow", "external"],
    flow_id: int | None = None,
    external_url: str | None = None,
) -> None:
    if notification_type == "flow" and flow_id is not None:
        notification = FlowInAppNotification(
            user_id=user_id,
            text=text,
            flow_id=flow_id,
        )
    elif notification_type == "external" and external_url is not None:
        notification = ExternalInAppNotification(
            user_id=user_id,
            text=text,
            external_url=external_url,
        )
    else:
        raise ValueError(f"Invalid notification type: {notification_type}")

    db_session.add(notification)


def render_flow_posted_notification_text(
    actor_name: str, community_name: str, flow_title: str
) -> str:
    return f"{actor_name} postou o flow {flow_title} em {community_name}!"


def render_flow_question_done_notification_text(
    actor_name: str, flow_title: str
) -> str:
    return f"{actor_name} respondeu uma questão no seu flow {flow_title}!"


def render_user_joined_notification_text(actor_name: str, community_name: str) -> str:
    return f"{actor_name} entrou em {community_name}!"


async def notify_communities_flow_posted(
    db_session: AsyncSession,
    *,
    actor: User,
    flow: Flow,
):
    """Notifies all users in communities that a flow was posted by a user in that community."""

    community_query = (
        select(Community)
        .where(Community.users.any(User.id == actor.id))
        .options(selectinload(Community.users))
    )
    result = await db_session.scalars(community_query)
    communities = result.all()

    notification_data: list[fcm_service.NotificationData] = []

    for community in communities:
        for user in community.users:
            if user.id == actor.id:
                continue
            text = render_flow_posted_notification_text(
                actor_name=actor.name,
                community_name=community.name,
                flow_title=flow.title,
            )
            create_notification(
                db_session=db_session,
                user_id=user.id,
                text=text,
                notification_type="flow",
                flow_id=flow.id,
            )
            notification_data.append(
                fcm_service.NotificationData(
                    user_id=user.id,
                    title=f"{actor.name} postou em {community.name}!",
                    body=f"O usuário {actor.name} postou o flow {flow.title} em {community.name}",
                )
            )

    await fcm_service.send_notifications(db_session, notification_data)


async def notify_user_flow_question_done(
    db_session: AsyncSession,
    *,
    actor: User,
    flow: Flow,
):
    """Notifies a user that a question was answered on a flow of theirs."""
    if actor.id == flow.created_by_id:
        return

    text = render_flow_question_done_notification_text(
        actor_name=actor.name, flow_title=flow.title
    )

    create_notification(
        db_session=db_session,
        user_id=flow.created_by_id,
        text=text,
        notification_type="flow",
        flow_id=flow.id,
    )
    await fcm_service.send_notifications(
        db_session,
        notification_data=[
            fcm_service.NotificationData(
                user_id=flow.created_by_id,
                title=f"{actor.name} respondeu questão num flow seu!",
                body=f"O usuário {actor.name} respondeu uma questão no seu flow {flow.title}",
            )
        ],
    )


async def notify_community_user_joined(
    db_session: AsyncSession,
    *,
    user: User,
    community: Community,
) -> None:
    """Notifies a community that a user joined it."""
    notification_data: list[fcm_service.NotificationData] = []
    await db_session.refresh(community, ["users"])
    for community_user in community.users:
        if community_user.id == user.id:
            continue
        notification_data.append(
            fcm_service.NotificationData(
                user_id=community_user.id,
                title=f"{user.name} entrou em {community.name}!",
                body=f"O usuário {user.name} agora faz parte de {community.name} também!",
            )
        )
    await fcm_service.send_notifications(
        db_session,
        notification_data=notification_data,
    )
