from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.base import Base

if TYPE_CHECKING:
    from app.users.models import User


class DeviceType(StrEnum):
    ANDROID = "android"
    IOS = "ios"
    WEB = "web"


class FCMDevice(Base):
    registration_id: Mapped[str] = mapped_column(String(255), unique=True)
    device_type: Mapped[DeviceType] = mapped_column()
    active: Mapped[bool] = mapped_column(default=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), unique=True
    )
    user: Mapped["User"] = relationship(
        back_populates="fcm_device", lazy="raise_on_sql"
    )
