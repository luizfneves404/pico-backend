from enum import StrEnum
from typing import TYPE_CHECKING, Final

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.base import Base

if TYPE_CHECKING:
    from app.flows.models import Flow
    from app.users.models import User


class InAppNotificationType(StrEnum):
    IN_APP_NOTIFICATION = "in_app_notification"
    EXTERNAL = "external_in_app_notification"
    FLOW = "flow_in_app_notification"


class InAppNotification(Base, kw_only=True):
    text: Mapped[str] = mapped_column(Text)
    seen: Mapped[bool] = mapped_column(default=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), default=None
    )
    user: Mapped["User"] = relationship(lazy="raise_on_sql", default=None)

    in_app_notification_type: Mapped[InAppNotificationType] = mapped_column()

    __mapper_args__ = {  # noqa: RUF012
        "polymorphic_on": in_app_notification_type,
        "polymorphic_identity": InAppNotificationType.IN_APP_NOTIFICATION,
    }


class ExternalInAppNotification(InAppNotification, kw_only=True):
    in_app_notification_type: Mapped[InAppNotificationType] = mapped_column(
        use_existing_column=True,
        init=False,
        insert_default=InAppNotificationType.IN_APP_NOTIFICATION,
    )
    __mapper_args__: Final = {
        "polymorphic_identity": InAppNotificationType.EXTERNAL,
        "polymorphic_load": "inline",
    }

    external_url: Mapped[str] = mapped_column(Text, default="")


class FlowInAppNotification(InAppNotification, kw_only=True):
    in_app_notification_type: Mapped[InAppNotificationType] = mapped_column(
        use_existing_column=True, init=False, insert_default=InAppNotificationType.FLOW
    )
    __mapper_args__: Final = {
        "polymorphic_identity": InAppNotificationType.FLOW,
        "polymorphic_load": "inline",
    }
    flow_id: Mapped[int] = mapped_column(
        ForeignKey("flow.id", ondelete="CASCADE"), default=None, nullable=True
    )
    flow: Mapped["Flow"] = relationship(lazy="raise_on_sql", default=None)
