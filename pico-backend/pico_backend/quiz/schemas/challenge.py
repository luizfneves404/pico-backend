from datetime import datetime as AwareDatetime

from api.schemas.users import SimpleUserOut
from ninja import Schema
from pydantic import model_validator
from quiz.models import QuestionSelectionMethod
from quiz.schemas.duels import DuelQuestionOut


class AnswerChoiceOut(Schema):
    id: int


class ChallengeQuestionOut(DuelQuestionOut):
    pass


class ChallengeParticipationOut(Schema):
    user: SimpleUserOut
    confirmed: bool
    total_answers: int
    correct_answers: int


class ChallengeOut(Schema):
    id: int
    code: str
    created_at: AwareDatetime
    title: str
    start_time: AwareDatetime
    end_time: AwareDatetime
    is_fast: bool
    selection_method: QuestionSelectionMethod
    participations: list[ChallengeParticipationOut] = []
    questions_and_answers: list[ChallengeQuestionOut] = []
    query: str = ""
    area: str = ""
    difficulty: str = ""
    source_filter: str = ""


class ChallengeCreateIn(Schema):
    selection_method: QuestionSelectionMethod
    start_time: AwareDatetime
    end_time: AwareDatetime
    user_ids: list[int] = []
    question_blocks: list[str] = []
    topic: str = ""
    subject: str = ""
    query: str = ""
    area: str = ""
    difficulty: str = ""
    source_filter: str = ""
    is_fast: bool = True

    @model_validator(mode="after")
    def validate_start_time_before_end_time(self):
        if self.start_time >= self.end_time:
            raise ValueError("Start time must be before end time")
        return self


class ChallengeInviteIn(Schema):
    user_ids: list[int]


class ChallengeJoinByCodeIn(Schema):
    challenge_code: str


class ChallengeSubmitAnswerIn(Schema):
    question_id: int
    answer_choice_id: int


class ChallengeQuestionIdIn(Schema):
    question_id: int
