import datetime
import decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from base import Base, auto_now_update_timestamp
from shared.code_generation import HasCode
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.quiz.models import Duel
    from app.users.models import User


class TournamentStatus(StrEnum):
    UPCOMING = "upcoming"
    ONGOING = "ongoing"
    COMPLETED = "completed"


class Tournament(Base, HasCode):
    updated_at: Mapped[auto_now_update_timestamp]
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)

    start_time: Mapped[datetime.datetime] = mapped_column()
    end_time: Mapped[datetime.datetime] = mapped_column()

    status: Mapped[TournamentStatus] = mapped_column()

    participants: Mapped[list["User"]] = relationship(
        secondary="tournament_participation",
        back_populates="tournaments_participating",
        lazy="raise_on_sql",
        viewonly=True,
    )

    participations: Mapped[list["TournamentParticipation"]] = relationship(
        back_populates="tournament",
        lazy="raise_on_sql",
        cascade="save-update, merge, expunge, delete, delete-orphan",
        passive_deletes=True,
    )

    prizes: Mapped[list["TournamentPrize"]] = relationship(
        back_populates="tournament",
        lazy="raise_on_sql",
        cascade="save-update, merge, expunge, delete, delete-orphan",
        passive_deletes=True,
    )

    duels: Mapped[list["Duel"]] = relationship(
        back_populates="tournament", lazy="raise_on_sql"
    )


class TournamentPrize(Base):
    rank: Mapped[int] = mapped_column(
        CheckConstraint("rank >= 0", name="tournament_prize_rank_check")
    )
    amount: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2))
    tournament_id: Mapped[int] = mapped_column(
        ForeignKey("tournament.id", ondelete="CASCADE")
    )
    tournament: Mapped["Tournament"] = relationship(back_populates="prizes")

    __table_args__ = (UniqueConstraint("tournament_id", "rank"),)


class TournamentParticipation(Base):
    __table_args__ = (UniqueConstraint("user_id", "tournament_id"),)

    tournament_id: Mapped[int] = mapped_column(
        ForeignKey("tournament.id", ondelete="CASCADE")
    )
    tournament: Mapped["Tournament"] = relationship(back_populates="participations")
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    user: Mapped["User"] = relationship(back_populates="tournament_participations")
