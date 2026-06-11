import logging

from celery import shared_task
from django.db import IntegrityError, connection
from django.utils import timezone

from quiz import stats_service
from quiz.models import (
    Choice,
    Question,
    SessionQuestion,
)

FAST_QUESTION_TIMEOUT = 60
SLOW_QUESTION_TIMEOUT = 130

SESSION_DATA_CTE = """
    SELECT 
        sq.id AS session_question_id
    FROM quiz_sessionquestion AS sq
    JOIN quiz_session AS s ON s.id = sq.session_id
    WHERE s.id = %s AND sq.question_id = %s
"""

logger = logging.getLogger(__name__)


class InvalidStateForAnswer(Exception):
    pass


class SessionQuestionNotFoundError(Exception):
    pass


class AnswerAlreadySubmitted(Exception):
    pass


class ChoiceNotFoundError(Exception):
    pass


class NoRowsAffectedError(Exception):
    pass


def add_questions_to_session(
    session_id: int, questions: list[Question]
) -> list[SessionQuestion]:
    """Add questions to a session using only the session ID.

    Args:
        session_id (int): The ID of the session to add questions to
        questions (list[Question]): List of Question objects to add

    Returns:
        list[SessionQuestion]: The created SessionQuestion objects
    """

    to_create = [SessionQuestion(session_id=session_id, question=q) for q in questions]
    if to_create:
        return SessionQuestion.objects.bulk_create(to_create)
    return []


async def aadd_questions_to_session(
    session_id: int, questions: list[Question]
) -> list[SessionQuestion]:
    """Async version to add questions to a session using only the session ID.

    Args:
        session_id (int): The ID of the session to add questions to
        questions (list[Question]): List of Question objects to add

    Returns:
        list[SessionQuestion]: The created SessionQuestion objects
    """

    to_create = [SessionQuestion(session_id=session_id, question=q) for q in questions]
    if to_create:
        return await SessionQuestion.objects.abulk_create(to_create)
    return []


@shared_task
def _task_mark_question_timed_out(
    user_id: int, session_id: int, question_id: int
) -> None:
    mark_question_timed_out(
        user_id,
        session_id,
        question_id,
    )


def schedule_question_timeout(user_id: int, session_id: int, question_id: int) -> None:
    """
    Schedules a question timeout for a user in a session.
    """
    is_fast = Question.objects.values("is_fast").get(id=question_id)["is_fast"]
    _task_mark_question_timed_out.apply_async(
        args=[user_id, session_id, question_id],
        countdown=FAST_QUESTION_TIMEOUT if is_fast else SLOW_QUESTION_TIMEOUT,
    )


def mark_question_seen(user_id: int, session_id: int, question_id: int) -> None:
    """Mark a question as seen by a user."""
    sql = f"""
    WITH session_data AS ({SESSION_DATA_CTE})
    INSERT INTO quiz_sessionquestionuser (
        session_question_id, user_id, choice_id, submitted_text, timestamp, feedback, grade, timed_out
    )
    VALUES ((SELECT session_question_id FROM session_data), %s, NULL, '', %s, '', NULL, FALSE)
    ON CONFLICT (session_question_id, user_id) DO NOTHING
    """
    with connection.cursor() as cursor:
        try:
            cursor.execute(sql, [session_id, question_id, user_id, timezone.now()])
            if cursor.rowcount == 0:
                logger.warning(
                    f"No rows were affected by the seen query for session {session_id}, question {question_id}, user {user_id}"
                )
            else:
                logger.info(
                    f"Marked question {question_id} as seen for session {session_id}, user {user_id}"
                )
        except IntegrityError as e:
            if 'null value in column "session_question_id"' in str(e):
                logger.warning(
                    f"Could not mark question {question_id} as seen for session {session_id}, user {user_id} because the session question does not exist"
                )
                raise SessionQuestionNotFoundError
            else:
                raise e

    schedule_question_timeout(user_id, session_id, question_id)


def mark_question_timed_out(user_id: int, session_id: int, question_id: int) -> None:
    """Mark a question as timed out for a user."""
    sql = f"""
    WITH session_data AS ({SESSION_DATA_CTE})
    UPDATE quiz_sessionquestionuser
    SET timed_out = TRUE
    FROM session_data
    WHERE quiz_sessionquestionuser.session_question_id = session_data.session_question_id
    AND quiz_sessionquestionuser.user_id = %s
    AND quiz_sessionquestionuser.choice_id IS NULL
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [session_id, question_id, user_id])
        if cursor.rowcount == 0:
            logger.info(
                f"No rows were affected by the timed out query for session {session_id}, question {question_id}, user {user_id}"
            )
        else:
            logger.info(
                f"Marked question {question_id} as timed out for session {session_id}, user {user_id}"
            )


def submit_answer(
    user_id: int,
    session_id: int,
    question_id: int,
    answer_choice_id: int,
) -> None:
    """Submit an answer for a question by a user, inserting if needed."""
    sql = f"""
    WITH session_data AS ({SESSION_DATA_CTE})
    INSERT INTO quiz_sessionquestionuser (
        session_question_id,
        user_id,
        choice_id,
        submitted_text,
        timed_out,
        timestamp,
        feedback,
        grade
    )
    SELECT
        sd.session_question_id,
        %s,                -- user_id
        %s,                -- answer_choice_id
        '',                -- submitted_text (empty string default)
        FALSE,             -- timed_out
        NOW(),             -- timestamp
        '',                -- feedback (empty string default)
        NULL               -- grade (null default)
    FROM session_data sd
    ON CONFLICT (session_question_id, user_id) DO UPDATE
    SET choice_id = EXCLUDED.choice_id
    WHERE quiz_sessionquestionuser.choice_id IS NULL
      AND quiz_sessionquestionuser.timed_out = FALSE
    RETURNING choice_id;
    """
    with connection.cursor() as cursor:
        cursor.execute(
            sql,
            [
                # params for SESSION_DATA_CTE:
                session_id,
                question_id,
                # params for INSERT … SELECT:
                user_id,
                answer_choice_id,
            ],
        )
        result = cursor.fetchone()
        if cursor.rowcount == 0:
            logger.warning(
                f"No rows were affected by the submit answer query for "
                f"session {session_id}, question {question_id}, "
                f"user {user_id}, choice {answer_choice_id}"
            )
            raise NoRowsAffectedError

    if not result:
        raise ChoiceNotFoundError

    choice_id = result[0]
    logger.info(
        f"Successfully submitted answer for session {session_id}, "
        f"question {question_id}, user {user_id}, choice {choice_id}"
    )
    is_correct = Choice.objects.values("is_correct").get(id=choice_id)["is_correct"]

    if is_correct:
        stats_service.update_dynamic_score(user_id, 1)
