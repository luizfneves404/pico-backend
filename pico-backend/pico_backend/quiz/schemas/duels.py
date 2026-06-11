from enum import StrEnum
from typing import Annotated

from api.schemas.users import SimpleUserOut
from ninja import Schema
from pydantic import AfterValidator, AwareDatetime, Field, model_validator
from quiz.models import DuelStatus, QuestionSelectionMethod
from quiz.schemas.quiz import SimpleQuestionOut


def force_1_round(v: int) -> int:
    return 1


class DuelIn(Schema):
    user_id: int | None = None
    n_rounds: Annotated[int, AfterValidator(force_1_round)]
    n_questions_per_round: int
    selection_method: QuestionSelectionMethod
    question_blocks: list[str] = Field(default_factory=list, max_length=200)
    topic: str = Field(default="", max_length=100)
    is_fast: bool = Field(default=True)
    subject: str = Field(default="", max_length=100)
    tournament_id: int | None = None

    @model_validator(mode="after")
    def validate_selection_method(self):
        if self.selection_method == QuestionSelectionMethod.USER_GENERATED:
            if not self.question_blocks and not self.topic:
                raise ValueError(
                    "At least one of question_blocks or topic must be provided for user-generated questions"
                )
        else:
            if bool(self.question_blocks) or bool(self.topic):
                raise ValueError(
                    "question_blocks and topic cannot be provided for official questions"
                )
        return self

    @model_validator(mode="after")
    def validate_tournament_id(self):
        if self.tournament_id and self.user_id:
            raise ValueError("Tournament ID and User ID cannot be provided together")
        return self


class DuelAddQuestionsIn(Schema):
    query: str  # if empty, random questions
    area: str = Field(default="", max_length=100)
    source_filter: str = Field(default="", max_length=100)
    difficulty: str = Field(default="", max_length=100)
    is_fast: bool = Field(default=True)


class DuelSubmitAnswerIn(Schema):
    question_id: int
    answer_choice_id: (
        int | None
    )  # to be deprecated. this should always have an int (at least until we implement open ended questions for duel)
    # before, we used None here to indicate that the user didnt answer in time, but now we use another endpoint


class DuelParticipationOut(Schema):
    user: SimpleUserOut
    confirmed: bool
    duel_score_change: float | None


class DuelAnswerOut(Schema):
    choice_id: (
        int | None
    )  # if its open_ended, then None. it could also be None if its multiple_choice and the user didnt answer in time
    submitted_text: str | None  # if no text, it will be empty string
    feedback: str | None  # if no feedback, it will be empty string
    grade: float | None  # if no grade, it will be None
    timestamp: AwareDatetime
    user: SimpleUserOut
    timed_out: bool


class DuelQuestionOut(SimpleQuestionOut):
    answers: list[DuelAnswerOut]

    @model_validator(mode="after")
    def exclude_unanswered_timed_out(self):
        """Exclude answers that were only seen but not answered or timed out"""
        self.answers = [
            answer
            for answer in self.answers
            if answer.choice_id is not None or answer.timed_out
        ]
        return self


class DuelRoundOut(Schema):
    query: str


class DuelPhaseOrEmpty(StrEnum):
    """this is needs to be kept in sync with the DuelTurnPhase enum in models.py"""

    ATTACK = "attack"
    DEFENSE = "defense"
    EMPTY = ""


class DuelOut(Schema):
    id: int
    code: str
    created_at: AwareDatetime
    is_fast: bool
    current_turn_user_id: int | None
    duel_phase: DuelPhaseOrEmpty
    n_rounds: int
    n_questions_per_round: int
    participations: list[DuelParticipationOut]
    questions_and_answers: list[DuelQuestionOut]
    selection_method: QuestionSelectionMethod
    status: DuelStatus = Field(alias="duel_status")
    winner_id: int | None
    current_turn_start_time: AwareDatetime | None
    rounds: list[DuelRoundOut]
    tournament_id: int | None


class DuelJoinByCodeIn(Schema):
    code: str


class DuelQuestionIdIn(Schema):
    question_id: int


class DuelInviteIn(Schema):
    user_id: int


class DuelJoinByTournamentIn(Schema):
    tournament_id: int
