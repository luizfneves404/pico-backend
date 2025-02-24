from datetime import datetime
from typing import TYPE_CHECKING

from base import Base
from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from users.models import User


class Membership(Base):
    __tablename__ = "membership"

    chatroom_id: Mapped[int] = mapped_column(
        ForeignKey("chatroom.id"), primary_key=True
    )
    chatroom: Mapped["Chatroom"] = relationship(back_populates="membership_set")
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), primary_key=True)
    user: Mapped["User"] = relationship(back_populates="membership_set")
    role: Mapped[int]


class Chatroom(Base):
    __tablename__ = "chatroom"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(unique=True)
    timestamp: Mapped[datetime] = mapped_column(server_default=func.now())
    members: Mapped[list["User"]] = relationship(
        back_populates="chatrooms", secondary="membership", viewonly=True
    )
    membership_set: Mapped[list["Membership"]] = relationship(back_populates="chatroom")
    messages: Mapped[list["Message"]] = relationship(back_populates="chatroom")


class Message(Base):
    __tablename__ = "message"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chatroom_id: Mapped[int] = mapped_column(ForeignKey("chatroom.id"))
    chatroom: Mapped["Chatroom"] = relationship(back_populates="messages")
    sender_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    sender: Mapped["User"] = relationship(back_populates="messages")
    timestamp: Mapped[datetime] = mapped_column(server_default=func.now())
    content: Mapped[str]
