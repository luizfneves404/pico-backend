from ninja import Schema
from pydantic import AwareDatetime

from .models import TournamentStatus


class TournamentCodeIn(Schema):
    tournament_code: str


class SimpleTournament(Schema):
    id: int
    code: str
    name: str
    description: str
    start_time: AwareDatetime
    end_time: AwareDatetime
    status: TournamentStatus


class TournamentParticipation(Schema):
    id: int
    username: str
    score: int
    rank: int
    prize: int


class DetailedTournament(SimpleTournament):
    participations: list[TournamentParticipation]


class SchoolInTournamentRanking(Schema):
    id: int
    name: str
    score: int
    rank: int
