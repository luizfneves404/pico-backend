from typing import TYPE_CHECKING

from base import Base
from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from users.models import User


class School(Base):
    name: Mapped[str] = mapped_column(String(120))
    user_submitted: Mapped[bool] = mapped_column(default=False)
    inep_code: Mapped[str] = mapped_column(String(40), default="")
    users: Mapped[list["User"]] = relationship(
        back_populates="school", lazy="raise_on_sql"
    )

    __table_args__ = (
        Index(
            "unique_inep_code",
            "inep_code",
            unique=True,
            postgresql_where=inep_code != "",
        ),
    )

    def __str__(self) -> str:
        return self.name
