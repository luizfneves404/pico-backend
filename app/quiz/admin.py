from app.quiz.models import (
    Challenge,
    Choice,
    Duel,
    Question,
    Quiz,
    Round,
    Session,
    SessionParticipation,
    Turn,
    UserInfo,
)
from app.shared.admin import Admin


class QuizAdmin(Admin, model=Quiz):
    column_list = [
        Quiz.id,
        Quiz.code,
        Quiz.created_at,
        Quiz.query,
        Quiz.area,
        Quiz.quiz_type,
        Quiz.question_type,
    ]
    column_searchable_list = [Quiz.id, Quiz.code, Quiz.query, Quiz.area]
    column_sortable_list = [Quiz.id, Quiz.created_at, Quiz.area]
    column_details_list = [
        Quiz.id,
        Quiz.code,
        Quiz.created_at,
        Quiz.query,
        Quiz.area,
        Quiz.source_filter,
        Quiz.difficulty,
        Quiz.quiz_type,
        Quiz.question_type,
    ]


class SessionAdmin(Admin, model=Session):
    column_list = [
        Session.id,
        Session.code,
        Session.created_at,
        Session.session_type,
        Session.query,
        Session.area,
    ]
    column_searchable_list = [
        Session.id,
        Session.code,
        Session.query,
        Session.area,
        Session.session_type,
    ]
    column_sortable_list = [Session.id, Session.created_at, Session.session_type]
    column_details_list = [
        Session.id,
        Session.code,
        Session.created_at,
        Session.session_type,
        Session.query,
        Session.area,
        Session.source_filter,
        Session.difficulty,
    ]


class QuestionAdmin(Admin, model=Question):
    column_list = [
        Question.id,
        Question.subject,
        Question.source,
        Question.difficulty,
        Question.is_active,
    ]
    column_searchable_list = [
        Question.id,
        Question.text,
        Question.subject,
        Question.source,
    ]
    column_sortable_list = [
        Question.id,
        Question.created_at,
        Question.subject,
        Question.difficulty,
    ]
    column_details_list = [
        Question.id,
        Question.text,
        Question.subject,
        Question.source,
        Question.difficulty,
        Question.is_active,
        Question.created_at,
    ]


class ChoiceAdmin(Admin, model=Choice):
    column_list = [Choice.id, Choice.question_id, Choice.text, Choice.is_correct]
    column_searchable_list = [Choice.id, Choice.text, Choice.question_id]
    column_sortable_list = [Choice.id, Choice.question_id, Choice.is_correct]


class DuelAdmin(Admin, model=Duel):
    column_list = [Duel.id, Duel.code, Duel.created_at, Duel.duel_status]
    column_searchable_list = [Duel.id, Duel.code]
    column_sortable_list = [Duel.id, Duel.created_at, Duel.duel_status]
    column_details_list = [
        Duel.id,
        Duel.code,
        Duel.created_at,
        Duel.duel_status,
        Duel.selection_method,
        Duel.n_questions_per_round,
    ]


class ChallengeAdmin(Admin, model=Challenge):
    column_list = [
        Challenge.id,
        Challenge.code,
        Challenge.created_at,
        Challenge.start_time,
        Challenge.end_time,
    ]
    column_searchable_list = [Challenge.id, Challenge.code, Challenge.query]
    column_sortable_list = [
        Challenge.id,
        Challenge.created_at,
        Challenge.start_time,
        Challenge.end_time,
    ]


class UserInfoAdmin(Admin, model=UserInfo):
    column_list = [
        UserInfo.id,
        UserInfo.user_id,
        UserInfo.average_score,
        UserInfo.math_score,
        UserInfo.language_score,
        UserInfo.humanities_score,
        UserInfo.science_score,
    ]
    column_sortable_list = [
        UserInfo.id,
        UserInfo.average_score,
        UserInfo.dynamic_score,
        UserInfo.duel_score,
    ]


class RoundAdmin(Admin, model=Round):
    column_list = [Round.id, Round.duel_id, Round.query]
    column_searchable_list = [Round.id, Round.duel_id, Round.query]
    column_sortable_list = [Round.id, Round.duel_id]


class TurnAdmin(Admin, model=Turn):
    column_list = [Turn.id, Turn.round_id, Turn.user_id, Turn.phase, Turn.start_time]
    column_searchable_list = [Turn.id, Turn.round_id, Turn.user_id]
    column_sortable_list = [Turn.id, Turn.start_time, Turn.phase]


class SessionParticipationAdmin(Admin, model=SessionParticipation):
    column_list = [
        SessionParticipation.id,
        SessionParticipation.session_id,
        SessionParticipation.user_id,
        SessionParticipation.confirmed,
    ]
    column_searchable_list = [
        SessionParticipation.id,
        SessionParticipation.session_id,
        SessionParticipation.user_id,
    ]
    column_sortable_list = [
        SessionParticipation.id,
        SessionParticipation.confirmed,
        SessionParticipation.duel_score_change,
    ]
