import datetime

from ninja import Schema
from pydantic import AliasChoices, AwareDatetime, Field


class AnswerOut(Schema):
    quiz_id: int = Field(
        validation_alias=AliasChoices("session_question__session_id", "session_id")
    )
    question_id: int = Field(
        validation_alias=AliasChoices("session_question__question_id", "question_id")
    )
    timestamp: AwareDatetime


class AnswerDayOut(Schema):
    date: datetime.date
    answers: list[AnswerOut]
    total_answers: int
