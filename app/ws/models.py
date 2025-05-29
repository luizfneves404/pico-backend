import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.base import Base

if TYPE_CHECKING:
    from app.users.models import User


class UserWebsocketInfo(Base):
    last_websocket_connection: Mapped[datetime.datetime] = mapped_column()
    last_websocket_disconnection: Mapped[datetime.datetime | None]

    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), unique=True
    )
    user: Mapped["User"] = relationship(back_populates="user_websocket_info")
