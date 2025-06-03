from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.base import Base

if TYPE_CHECKING:
    from app.flows.models import Flow
    from app.users.models import User


class InAppNotification(Base):
    seen: Mapped[bool] = mapped_column(default=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    user: Mapped["User"] = relationship(lazy="raise_on_sql")

    text: Mapped[str] = mapped_column(Text)

    in_app_notification_type: Mapped[str] = mapped_column(String(50))

    __mapper_args__ = {
        "polymorphic_on": in_app_notification_type,
        "polymorphic_identity": "in_app_notification",
    }


class ExternalInAppNotification(InAppNotification):
    __mapper_args__ = {
        "polymorphic_identity": "external_in_app_notification",
        "polymorphic_load": "inline",
    }

    external_url: Mapped[str] = mapped_column(Text)


class FlowInAppNotification(InAppNotification):
    __mapper_args__ = {
        "polymorphic_identity": "flow_in_app_notification",
        "polymorphic_load": "inline",
    }

    flow_id: Mapped[int] = mapped_column(ForeignKey("flow.id", ondelete="CASCADE"))
    flow: Mapped["Flow"] = relationship(lazy="raise_on_sql")
