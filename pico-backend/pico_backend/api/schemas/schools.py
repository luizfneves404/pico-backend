from ninja import Schema
from pydantic import Field


class SchoolIn(Schema):
    name: str = Field(..., min_length=1, max_length=255)


class SchoolOut(Schema):
    id: int
    name: str


class SchoolInRanking(Schema):
    id: int
    name: str
    rank: int
    score: float
