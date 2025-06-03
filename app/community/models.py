from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql.schema import ForeignKey

from app.base import Base
from app.users.models import User


class CommunityUser(Base):
    __table_args__ = (UniqueConstraint("community_id", "user_id"),)

    community_id: Mapped[int] = mapped_column(
        ForeignKey("community.id", ondelete="CASCADE")
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))


class Community(Base):
    name: Mapped[str] = mapped_column(String(255))
    subtitle: Mapped[str] = mapped_column(String(255))

    users: Mapped[list["User"]] = relationship(
        back_populates="communities",
        secondary="community_user",
        lazy="raise_on_sql",
    )
