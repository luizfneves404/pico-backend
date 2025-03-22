import datetime
from typing import TYPE_CHECKING

from base import Base
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from users.models import User


class UserWebSocketInfo(Base):
    last_websocket_connection: Mapped[datetime.datetime] = mapped_column()
    last_websocket_disconnection: Mapped[datetime.datetime | None]

    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), unique=True)
    user: Mapped["User"] = relationship(back_populates="user_websocket_info")
