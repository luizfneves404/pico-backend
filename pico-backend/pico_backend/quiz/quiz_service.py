import datetime
import json
import logging
import random
import re
from collections import defaultdict
from typing import Any, AsyncGenerator, Literal, overload

import challenges.tasks as challenges_tasks
import shared.openai_utils as openai_utils
from api.models import User
from asgiref.sync import sync_to_async
from babel.dates import format_date
from currency.currency_service import handle_currency_transaction
from currency.decorators import currency_transaction
from currency.models import CurrencyAction, CurrencyType
from django.core.files.uploadedfile import UploadedFile
from django.db import IntegrityError, connection, transaction
from django.db.models import Count, F, Max, OuterRef, Q, Subquery
from django.http import StreamingHttpResponse
from django.utils import timezone

import quiz.question_service as question_service
import quiz.session_service as session_service
import quiz.utils as quiz_utils
from quiz.models import (
    ENEM_AREAS,
    SUBJECT_TO_AREA,
    Question,
    QuestionDensity,
    QuestionSelectionMethod,
    QuestionType,
    Quiz,
    QuizType,
    SelectionSource,
    SessionQuestion,
    SessionQuestionUser,
    Transcription,
    UserInfo,
)
from quiz.schemas.quiz import Difficulty
from quiz.utils import (
    CATEGORIES,
    SUBCATEGORIES,
)

from .constants import (
    AVERAGE_SCORES_BY_CORRECT_QUESTIONS,
    MAX_QUESTIONS_FOR_SCORE,
    OPEN_ENDED_FEEDBACK_MODEL,
    OPEN_ENDED_FEEDBACK_SYSTEM_MESSAGE,
    OPEN_ENDED_FEEDBACK_USER_MESSAGE,
    OPEN_ENDED_TEMPERATURE,
)

PERSONALIZED_AREA = "Personalizado"
NUM_QUESTIONS_DAILY_QUIZ = 20
NUM_LEARNING_QUESTIONS = 10
SUBJECTS = sum(ENEM_AREAS.values(), [])

SUBJECT_TO_AREA_TUPLES = ",\n".join(
    "('{subject}', '{area}')".format(
        subject=subject.replace("'", "''"), area=area.replace("'", "''")
    )
    for subject, area in SUBJECT_TO_AREA.items()
)


COLLEGE_TO_PREDEFINED_QUIZ_ID = {
    "UFRJ": 12900,
    "USP": 12903,
    "UERJ": 12904,
    "FGV": 12911,
    "PUC": 12986,
}

TOTAL_QUESTIONS_IF_NONE = 20
MIN_ANSWERS_FOR_SUBJECT_IN_PERCENTAGE_RANKING = 50
MIN_ANSWERS_NO_SUBJECT_IN_PERCENTAGE_RANKING = 100
logger = logging.getLogger(__name__)


class QuizNotFound(Exception):
    pass


class UserNotFound(Exception):
    pass


class ChoiceNotInQuestionError(Exception):
    pass


class QuestionNotFoundInQuiz(Exception):
    pass


class QuestionAlreadyAnswered(Exception):
    pass


def _create_query_for_user(area_for_query: str, username: str) -> str:
    date_and_time = timezone.localtime().strftime("%d/%m - %H:%M")
    return f"{area_for_query} {date_and_time} - {username}"


async def _get_multiple_choice_questions_from_configs(
    configs: list[dict[str, Any]],
) -> list[Question]:
    """
    configs: list of dictionaries with the following keys
    - number: number of questions to get
    - area: area of the questions
    - subject: subject of the questions
    - source_filter: filter for the source of the questions
    - difficulty: difficulty of the questions
    """
    questions: list[Question] = []
    for config in configs:
        questions.extend(
            [
                question
                async for question in question_service.get_official_questions(
                    "",
                    config["number"],
                    area=config.get("area", ""),
                    subject=config.get("subject", ""),
                    source_filter=config.get("source_filter", ""),
                    difficulty=config.get("difficulty", ""),
                    question_type=QuestionType.MULTIPLE_CHOICE,
                )
            ]
        )
    return questions


def _shuffle_science_questions(questions: list[Question]) -> list[Question]:
    science_subjects = {"Física", "Química", "Biologia"}
    science_questions = [q for q in questions if q.subject in science_subjects]
    other_questions = [q for q in questions if q.subject not in science_subjects]
    random.shuffle(science_questions)
    return other_questions + science_questions


async def create_compound_multiple_choice_quiz(
    area_for_query: str,
    area_for_quiz: str,
    username: str,
    user_id: int,
    source_filter: str,
    question_configs: list[dict[str, Any]],
    shuffle_science: bool = False,
) -> Quiz:
    query = _create_query_for_user(area_for_query, username)
    quiz = await Quiz.objects.acreate(
        area=area_for_quiz,
        source_filter=source_filter,
        query=query,
        question_type=QuestionType.MULTIPLE_CHOICE,
        created_by_id=user_id,
        title=query,
    )
    questions = await _get_multiple_choice_questions_from_configs(question_configs)
    if shuffle_science:
        questions = _shuffle_science_questions(questions)
    await session_service.aadd_questions_to_session(quiz.id, questions)
    return quiz


def create_simple_quiz(
    query: str,
    n: int,
    area: str = "",
    source_filter: str = "",
    difficulty: str = "",
    question_type: QuestionType = QuestionType.MULTIPLE_CHOICE,
    parent_session_id: int | None = None,
    user_id: int | None = None,
) -> Quiz:
    previous_questions_ids = []
    # If extending a quiz, exclude questions from the parent quiz and child quizzes
    if parent_session_id:
        previous_questions_ids = list(
            Question.objects.filter(
                Q(sessions__id=parent_session_id)
                | Q(sessions__parent_session_id=parent_session_id)
            )
            .values_list("id", flat=True)
            .distinct()
        )

    with transaction.atomic():
        quiz = Quiz.objects.create(
            title=query,
            selection_source=SelectionSource.TOPIC,
            selection_method=QuestionSelectionMethod.QUERY_OFFICIAL
            if query
            else QuestionSelectionMethod.RANDOM_OFFICIAL,
            query=query,
            area=area,
            source_filter=source_filter,
            difficulty=difficulty,
            question_type=question_type,
            parent_session_id=parent_session_id,
            created_by_id=user_id,
            quiz_type=QuizType.QUERY_BASED,
        )
        questions = question_service.get_official_questions(
            query,
            n,
            area=area,
            source_filter=source_filter,
            difficulty=difficulty,
            question_type=question_type,
            excluded_ids=previous_questions_ids,
            excluded_user_id=user_id,
            is_fast=None,
        )

        session_service.add_questions_to_session(quiz.id, list(questions))
        return quiz


def create_personalized_quiz(
    n: int,
    question_type: QuestionType,
    user: User,
    parent_quiz_id: int | None = None,
) -> Quiz:
    has_personalized_quiz = Quiz.objects.filter(
        created_by=user, quiz_type=QuizType.PERSONALIZED
    ).exists()

    if (
        not has_personalized_quiz
        and user.chosen_college
        and user.chosen_college.name in COLLEGE_TO_PREDEFINED_QUIZ_ID
    ):
        quiz_id = COLLEGE_TO_PREDEFINED_QUIZ_ID.get(user.chosen_college.name)
        quiz = Quiz.objects.filter(id=quiz_id).first()

        if quiz:
            return quiz
        else:
            # Log a warning if no quiz is found
            logger.warning(
                f"No quiz found with id {quiz_id} for college {user.chosen_college}"
            )

    elif not has_personalized_quiz:
        quiz_id = 12900
        quiz = Quiz.objects.filter(id=quiz_id).first()
        if quiz:
            return quiz
        else:
            logger.warning(
                f"No quiz found with id {quiz_id} for college {user.chosen_college}"
            )

    with transaction.atomic():
        quiz = Quiz.objects.create(
            area=PERSONALIZED_AREA,  # this should be temporary, but frontend asked
            selection_source=SelectionSource.RANDOM,
            selection_method=QuestionSelectionMethod.RANDOM_OFFICIAL,
            title=f"Personalizado - {user.username}",
            question_type=question_type,
            quiz_type=QuizType.PERSONALIZED,
            created_by=user,
            parent_session_id=parent_quiz_id,
        )

        # Get personalized questions, excluding those from the parent quiz if necessary
        questions = question_service.get_personalized_questions(
            n=n,
            question_type=question_type,
            user=user,
            parent_quiz_id=parent_quiz_id,
        )

        session_service.add_questions_to_session(quiz.id, questions)
        return quiz


@currency_transaction(
    action=CurrencyAction.QUIZ_CREATION, transaction_type=CurrencyType.PRICE
)
async def acreate_personalized_quiz(
    user: User,
    question_type: QuestionType = QuestionType.MULTIPLE_CHOICE,
    parent_quiz_id: int | None = None,
) -> dict[str, Any]:
    personalized_n = user.commitment
    quiz = await sync_to_async(create_personalized_quiz)(
        n=personalized_n,
        question_type=question_type,
        user=user,
        parent_quiz_id=parent_quiz_id,
    )

    return await aprepare_quiz_out(quiz.id, user.id)


async def aget_quiz_from_code(code: str, user_id: int) -> dict[str, Any]:
    return await sync_to_async(get_quiz_from_code)(code, user_id)


def get_quiz_from_code(code: str, user_id: int) -> dict[str, Any]:
    quiz = Quiz.objects.filter(code=code).first()
    if not quiz:
        raise QuizNotFound

    return prepare_quiz_outs(quiz.id, user_id)


@currency_transaction(
    action=CurrencyAction.QUIZ_CREATION, transaction_type=CurrencyType.PRICE
)
async def create_quiz(
    user: User,
    query: str,
    n: int,
    area: str = "",
    source_filter: str = "",
    difficulty: str = "",
    question_type: QuestionType = QuestionType.MULTIPLE_CHOICE,
    parent_quiz_id: int | None = None,
) -> dict[str, Any]:
    quiz = await sync_to_async(create_simple_quiz)(
        query,
        n,
        area,
        source_filter,
        difficulty,
        question_type,
        parent_session_id=parent_quiz_id,
        user_id=user.id,
    )

    return await aprepare_quiz_out(quiz.id, user.id)


async def create_quiz_with_files(
    user: User,
    topic: str,
    selection_source: SelectionSource,
    files: list[UploadedFile] = [],
) -> dict[str, Any]:
    quiz = await Quiz.objects.acreate(
        title=topic,
        query=topic,
        created_by=user,
        selection_source=selection_source,
    )
    await question_service.new_generate_transcriptions(files, str(quiz.id))

    return await aprepare_quiz_out(quiz.id, user.id)


async def add_questions_to_quiz(
    quiz_id: int,
    n_questions: int,
    question_density: QuestionDensity,
    area: str,
    source_filter: str,
    difficulty: Difficulty,
    question_type: QuestionType,
):
    question_blocks = [
        transcription.block_text
        for transcription in Transcription.objects.filter(quiz_id=quiz_id)
    ]
    questions = await question_service.get_questions_text_from_blocks_or_topic(
        question_blocks, "", None, None, True, "Português"
    )
    await session_service.add_questions_to_session(quiz_id, questions)


def update_score(user_id: int, user_info: UserInfo | None = None) -> UserInfo:
    logger.debug(f"Updating score for user {user_id}.")

    area_expected_scores = calc_user_stats(user_id)["area_expected_scores"]

    scores = {
        "math_score": area_expected_scores["Matemática"],
        "language_score": area_expected_scores["Linguagens"],
        "humanities_score": area_expected_scores["Ciências Humanas"],
        "science_score": area_expected_scores["Ciências da Natureza"],
    }

    if user_info:
        update_existing_user_info(user_info, scores)
    else:
        user_info = UserInfo.objects.create(user_id=user_id, **scores)

    logger.debug(
        f"User {user_id} scores updated: math_score={user_info.math_score}, "
        f"language_score={user_info.language_score}, humanities_score={user_info.humanities_score}, "
        f"science_score={user_info.science_score}."
    )
    return user_info


def update_existing_user_info(user_info: UserInfo, scores: dict[str, float]):
    user_info.math_score = scores["math_score"]
    user_info.language_score = scores["language_score"]
    user_info.humanities_score = scores["humanities_score"]
    user_info.science_score = scores["science_score"]
    user_info.save()
    user_info.refresh_from_db()


async def asubmit_multiple_choice_answer(
    user_id: int,
    quiz_id: int,
    question_id: int,
    answer_choice_id: int,
) -> None:
    return await sync_to_async(session_service.submit_answer)(
        user_id,
        quiz_id,
        question_id,
        answer_choice_id,
    )


async def asubmit_open_ended_answers(
    user_id: int, quiz_id: int, question_id: int, submitted_text: str
) -> StreamingHttpResponse:
    try:
        session_question = await SessionQuestion.objects.aget(
            question_id=question_id, session_id=quiz_id
        )
    except SessionQuestion.DoesNotExist:
        raise QuestionNotFoundInQuiz
    try:
        session_question_user = await SessionQuestionUser.objects.acreate(
            session_question_id=session_question.id,
            user_id=user_id,
            submitted_text=submitted_text,
        )
    except IntegrityError:
        logger.warning(
            f"User {user_id} already answered question {question_id} in quiz {quiz_id}"
        )
        raise QuestionAlreadyAnswered
    else:
        session_question_user = await SessionQuestionUser.objects.select_related(
            "session_question__question"
        ).aget(id=session_question_user.id)
        return StreamingHttpResponse(
            generate_feedback_and_grade_and_save(session_question_user),
            content_type="text/plain",
        )


# Generator function to handle OpenAI feedback streaming
async def generate_feedback_and_grade_and_save(
    session_question_user: SessionQuestionUser,
) -> AsyncGenerator[bytes, None]:
    question = session_question_user.session_question.question
    image_url = question.image.url if question.image else None
    user_message = OPEN_ENDED_FEEDBACK_USER_MESSAGE.format(
        extra_embedding_text=question.extra_embedding_text,
        question_text=question.text,
        official_answer=question.answer_text,
        submitted_text=session_question_user.submitted_text,
    )
    feedback_iterator = openai_utils.stream_completion(
        model=OPEN_ENDED_FEEDBACK_MODEL,
        temperature=OPEN_ENDED_TEMPERATURE,
        messages=[
            {"role": "system", "content": OPEN_ENDED_FEEDBACK_SYSTEM_MESSAGE},
            {
                "role": "user",
                "content": (
                    [
                        {"type": "text", "text": user_message},
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url, "detail": "low"},
                        },
                    ]
                    if image_url
                    else user_message
                ),
            },
        ],
    )
    complete_feedback = ""

    async for feedback_chunk in feedback_iterator:
        complete_feedback += feedback_chunk
        logger.info(f"Feedback chunk: {feedback_chunk}")
        yield bytes(feedback_chunk, "utf-8")  # Stream each part to the client

    # try to get the grade using regex
    grade_match = re.search(r"Nota: (\d+)", complete_feedback)
    grade = int(grade_match.group(1)) if grade_match else None
    if not grade:  # if the grade is not in the feedback, try to get it by asking
        grade = await openai_utils.get_grade(complete_feedback)

    # Update the database entry with full feedback and grade
    session_question_user.feedback = complete_feedback
    session_question_user.grade = grade
    await session_question_user.asave()


def handle_answer_bulk_create(instances):
    logger.info("Handling answer bulk create")
    user_id = instances[0].user_id
    if not all(instance.user_id == user_id for instance in instances):
        logger.warning(
            "Not all SessionQuestionUser instances have the same user object, so won't send notifications for challenge commitment goal"
        )
        return
    # fetch the ids of the answers because they didnt come from bulk create with ignore conflicts true
    session_question_ids = [instance.session_question_id for instance in instances]
    instances_basic_info = list(
        SessionQuestionUser.objects.filter(
            user_id=user_id, session_question_id__in=session_question_ids
        ).values("id")
    )
    instance_ids = [instance["id"] for instance in instances_basic_info]
    logger.info(
        f"Checking if we need to send challenge notifications for answers {instance_ids}"
    )
    challenges_tasks.task_check_send_challenge_notifications.delay_on_commit(
        instance_ids
    )


def update_quiz_out_with_score_increases(quiz_out, score_increases):
    quiz_out["score_increase"] = score_increases["score_increase"]
    area_expected_score_increases = {
        "Matemática": score_increases["math_score_increase"],
        "Linguagens": score_increases["language_score_increase"],
        "Ciências Humanas": score_increases["humanities_score_increase"],
        "Ciências da Natureza": score_increases["science_score_increase"],
    }
    quiz_out["area_expected_score_increases"] = area_expected_score_increases


async def read_quiz(user: User, quiz_id: int) -> dict[str, Any]:
    return await sync_to_async(prepare_quiz_outs)(quiz_id, user.id)


async def redeem_quiz(user: User, quiz_code: str) -> dict[str, Any]:
    """
    Redeem a quiz code, handling currency transactions appropriately
    based on quiz type.
    """
    quiz_code = quiz_code.upper()[:5]

    # First get the quiz without applying any currency transaction
    quiz_data = await aget_quiz_from_code(quiz_code, user.id)

    # Determine the appropriate currency action based on quiz type
    if quiz_data.get("quiz_type") == QuizType.CUSTOM:
        action = CurrencyAction.CUSTOM_QUIZ_JOIN
    else:
        action = CurrencyAction.QUIZ_JOIN

    # Manually handle the currency transaction
    await sync_to_async(handle_currency_transaction)(
        user=user,
        action=action,
        transaction_type=CurrencyType.PRICE,
        related_object=await Quiz.objects.aget(id=quiz_data["id"]),
    )

    return quiz_data


def list_user_quizzes(user_id: int) -> list[Quiz]:
    latest_answer_subquery = (
        SessionQuestionUser.objects.filter(
            user_id=user_id, session_question__session_id=OuterRef("id")
        )
        .order_by("-timestamp")
        .values("timestamp")[:1]
    )
    quizzes_done = (
        Quiz.objects.filter(
            session_question_set__session_question_user_set__user_id=user_id,
        )
        .select_related("created_by")
        .annotate(latest_answered_at=Subquery(latest_answer_subquery))
        .distinct()
    )

    return list(quizzes_done)


async def alist_user_quizzes(user_id: int) -> list[Quiz]:
    return await sync_to_async(list_user_quizzes)(user_id)


async def list_quizzes(user: User) -> list[dict[str, Any]]:
    quizzes_done_ids = (
        SessionQuestionUser.objects.filter(user_id=user.id)
        .values_list("session_question__session_id", flat=True)
        .distinct()
    )
    return await sync_to_async(prepare_quiz_outs)(
        [quiz_id async for quiz_id in quizzes_done_ids], user.id
    )


def get_quiz_stats(quiz: Quiz) -> list[dict[str, Any]]:
    stats = (
        SessionQuestionUser.objects.filter(session_question__session_id=quiz.id)
        .filter_by_type("multiple_choice")
        .values("user__username")
        .annotate(
            total_answers=Count("id"),
            correct_answers=Count("id", filter=Q(choice__is_correct=True)),
            latest_timestamp=Max("timestamp"),
        )
    )
    return list(stats)


async def aprepare_quiz_out(quiz_id: int, user_id: int):
    return await sync_to_async(prepare_quiz_outs)(quiz_id, user_id)


@overload
def prepare_quiz_outs(quiz_ids: int, user_id: int) -> dict[str, Any]: ...


@overload
def prepare_quiz_outs(quiz_ids: list[int], user_id: int) -> list[dict[str, Any]]: ...


def prepare_quiz_outs(quiz_ids: list[int] | int, user_id: int) -> list[dict] | dict:
    """Prepares a list of quizzes to be viewed by a specific user, prepared to comply with quiz/schemas/quiz.py. Should work for all quiz endpoints that return quizzes.

    Args:
        user_id (int): the user id of the user to prepare the quizzes for
        quiz_ids (list[int] | int): the list of quiz ids to prepare
    Returns:
        list[dict[str, Any]] | dict[str, Any]: a list of quizzes with the questions and answers and the participations, and all their info
    Raises:
        QuizNotFound: If there is one quiz and it is not found
    """
    if isinstance(quiz_ids, int):
        ids_list = [quiz_ids]
    else:
        ids_list = quiz_ids
    if not ids_list:
        return []
    query = """
    WITH latest_answers AS (
        SELECT 
            squ.session_question_id,
            squ.choice_id,
            squ.submitted_text,
            squ.feedback,
            squ.grade
        FROM quiz_sessionquestionuser squ
        WHERE squ.user_id = %s
        AND squ.timestamp = (
            SELECT MAX(timestamp)
            FROM quiz_sessionquestionuser squ2 
            WHERE squ2.session_question_id = squ.session_question_id
            AND squ2.user_id = squ.user_id
        )
    ),
    question_counts AS (
        SELECT 
            sq.session_id,
            COUNT(*) AS num_questions
        FROM quiz_sessionquestion sq
        GROUP BY sq.session_id
    ),
    quiz_rankings AS (
        SELECT 
            sq.session_id,
            squ.user_id,
            u.username,
            u.school_id,
            COALESCE(s.name, '') AS school_name,
            COUNT(DISTINCT sq.question_id) AS total_answers,
            COUNT(DISTINCT CASE WHEN c.is_correct THEN sq.question_id END) AS correct_answers,
            RANK() OVER (PARTITION BY sq.session_id ORDER BY COUNT(DISTINCT CASE WHEN c.is_correct THEN sq.question_id END) DESC, squ.user_id) AS rank
        FROM quiz_sessionquestion sq
        JOIN quiz_sessionquestionuser squ ON squ.session_question_id = sq.id
        JOIN api_user u ON squ.user_id = u.id
        LEFT JOIN api_school s ON u.school_id = s.id
        LEFT JOIN quiz_choice c ON squ.choice_id = c.id
        GROUP BY sq.session_id, squ.user_id, u.username, u.school_id, s.name
    )
    SELECT COALESCE(jsonb_agg(quiz_data)::text, '[]') AS data
    FROM (
      SELECT jsonb_build_object(
          -- Quiz basic info
          'id', qz.id,
          'code', qz.code,
          'title', qz.title,
          'created_at', qz.created_at,
          'created_by', jsonb_build_object(
              'id', u.id,
              'username', u.username
          ),
          'selection_source', qz.selection_source,
          'selection_method', qz.selection_method,
          'topic', qz.topic,
          'sections', CASE 
              WHEN qz.selection_method = 'full' THEN 
                  jsonb_build_array(
                      jsonb_build_object('name', 'user_generated', 'num_questions', qc.num_questions / 2),
                      jsonb_build_object('name', 'query_official', 'num_questions', qc.num_questions / 2)
                  )
              ELSE 
                  jsonb_build_array(
                      jsonb_build_object('name', qz.selection_method, 'num_questions', qc.num_questions)
                  )
          END,
          'source_filter', qz.source_filter,
          'difficulty', qz.difficulty,
          'quiz_type', qz.quiz_type,
          'query', qz.query,
          'area', qz.area,
          'parent_session_id', qz.parent_session_id,
          'latest_answered_at', (
              SELECT MAX(squ.timestamp)
              FROM quiz_sessionquestion sq
              JOIN quiz_sessionquestionuser squ
                ON squ.session_question_id = sq.id
              WHERE sq.session_id = qz.id
                AND squ.user_id = %s
          ),
          -- Ranking of users in the quiz
          'ranking', (
              SELECT COALESCE(jsonb_agg(
                  jsonb_build_object(
                      'id', qr.user_id,
                      'username', qr.username,
                      'rank', qr.rank,
                      'school', qr.school_name,
                      'school_id', qr.school_id,
                      'total_answers', qr.total_answers,
                      'correct_answers', qr.correct_answers
                  )
              ), '[]'::jsonb)
              FROM quiz_rankings qr
              WHERE qr.session_id = qz.id
          ),
          -- Nested list of questions with choices and the user's latest answer
          'questions_and_answers', (
              SELECT COALESCE(jsonb_agg(
                  jsonb_build_object(
                      'id', qq.id,
                      'allow_resubmit', qq.allow_resubmit,
                      'subject', qq.subject,
                      'text', qq.text,
                      'answer_text', qq.answer_text,
                      'answer_image', '',
                      'image', '',
                      'video_url', '',
                      'source', qq.source,
                      'difficulty', qq.difficulty,
                      'category', qq.category,
                      'subcategory', qq.subcategory,
                      'choices', (
                          SELECT COALESCE(jsonb_agg(
                              jsonb_build_object(
                                  'id', qc.id,
                                  'text', qc.text,
                                  'image', '',
                                  'is_correct', qc.is_correct
                              )
                          ), '[]'::jsonb)
                          FROM quiz_choice qc
                          WHERE qc.question_id = qq.id
                      ),
                      'answer_choice_id', la.choice_id,
                      'submitted_text', la.submitted_text,
                      'feedback', la.feedback,
                      'grade', la.grade
                  )
              ), '[]'::jsonb)
              FROM quiz_sessionquestion sq
              JOIN quiz_question qq ON qq.id = sq.question_id
              LEFT JOIN latest_answers la ON la.session_question_id = sq.id
              WHERE sq.session_id = qz.id
          )
      ) AS quiz_data
      FROM quiz_session qz
      JOIN api_user u ON qz.created_by_id = u.id
      JOIN question_counts qc ON qc.session_id = qz.id
      WHERE qz.id = ANY(%s)
    ) t;
    """
    with connection.cursor() as cursor:
        cursor.execute(query, [user_id, user_id, ids_list])
        row = cursor.fetchone()

    quizzes = json.loads(row[0])
    questions_and_answers = [
        question for quiz in quizzes for question in quiz["questions_and_answers"]
    ]
    quiz_utils.update_urls_from_orm(questions_and_answers)

    try:
        return quizzes[0] if isinstance(quiz_ids, int) else quizzes
    except IndexError:
        raise QuizNotFound


def create_daily_quiz(user_id: int, username: str) -> Quiz:
    logger.info(f"Creating daily quiz for user: {username} (ID: {user_id})")

    formatted_date = format_date(
        timezone.localdate(), format="d 'de' MMMM", locale="pt_BR"
    )
    query = f"{username} - {formatted_date}"
    quiz = Quiz.objects.create(
        title=query,
        query=query,
        area="Quiz do Dia",
        question_type=QuestionType.MULTIPLE_CHOICE,
        quiz_type=QuizType.PERSONALIZED,
        created_by_id=user_id,
    )

    logger.info(f"Created new daily quiz (id: {quiz.id}) for user {username}.")

    selector = question_service.PersonalizedQuestionSelector(user_id)
    questions = selector.get_questions(NUM_QUESTIONS_DAILY_QUIZ, NUM_LEARNING_QUESTIONS)
    random.shuffle(questions)

    session_service.add_questions_to_session(quiz.id, questions)
    logger.info(f"Added {len(questions)} questions to the daily quiz (id: {quiz.id})")

    return quiz


# remember to ignore area None
def get_user_statistics(user_list):
    logger.debug("Starting to compute user statistics by area.")

    # Initialize user statistics with default values
    user_statistics: dict[str, dict[str, Any]] = {
        user.username: {
            "areas": defaultdict(
                lambda: {
                    "total_answers": 0,
                    "correct_answers": 0,
                    "proportion_correct": 0.0,
                }
            ),
            "worst_area": None,
        }
        for user in user_list
    }

    # Step 1: Get all answers for the given users
    logger.debug("Fetching SessionQuestionUser objects for the provided user list.")
    session_question_users = SessionQuestionUser.objects.filter(
        user_id__in=user_list
    ).filter_by_type("multiple_choice")
    logger.debug(
        f"Fetched {session_question_users.count()} SessionQuestionUser objects."
    )

    if not session_question_users.exists():
        logger.debug("No SessionQuestionUser objects found for the given users.")

    # Step 2: Annotate each answer with whether it was correct and the area
    logger.debug(
        "Annotating SessionQuestionUser objects with 'is_correct' and 'subject'."
    )
    session_question_users = session_question_users.annotate(
        is_correct=F("choice__is_correct"),
        subject=F("session_question__question__subject"),
    )

    # Step 3: Calculate the total and correct answers per subject for each user
    logger.debug("Calculating the total and correct answers per subject for each user.")
    user_area_correct_counts = session_question_users.values(
        "user__username", "session_question__question__subject"
    ).annotate(
        total_answers=Count("id"),
        correct_answers=Count("id", filter=Q(is_correct=True)),
    )
    logger.debug("Calculated correct and total answer counts for each subject.")

    # Step 4: Aggregate the results by area
    logger.debug("Aggregating the results by area.")
    user_area_totals = defaultdict(
        lambda: defaultdict(
            lambda: {
                "total_answers": 0,
                "correct_answers": 0,
                "proportion_correct": 0.0,
            }
        )
    )
    skipped_subjects: set[str] = set()
    for entry in user_area_correct_counts:
        username = entry["user__username"]
        subject = entry["session_question__question__subject"]
        area = get_area_from_subject(subject)
        if not area:
            skipped_subjects.add(subject)
            continue
        user_area_totals[username][area]["total_answers"] += entry["total_answers"]
        user_area_totals[username][area]["correct_answers"] += entry["correct_answers"]

    logger.debug(
        f"Skipped subjects: {skipped_subjects}. These subjects are not mapped to any area."
    )

    # Step 5: Calculate proportions and find the worst area for each user
    logger.debug(
        "Calculating the proportion of correct answers and identifying the worst area for each user."
    )
    for username, area_totals in user_area_totals.items():
        area_proportions = {}
        for area, totals in area_totals.items():
            if totals["total_answers"] > 0:
                proportion_correct = totals["correct_answers"] / totals["total_answers"]
            else:
                proportion_correct = 0.0
            totals["proportion_correct"] = proportion_correct
            area_proportions[area] = proportion_correct

        worst_area = min(area_proportions, key=area_proportions.get)
        user_statistics[username]["areas"] = dict(area_totals)
        user_statistics[username]["worst_area"] = worst_area
        logger.debug(f"User {username} - Statistics: {user_statistics[username]}")

    logger.debug("Completed computing user statistics by area.")
    return user_statistics


def get_area_from_subject(subject: str) -> str | None:
    return SUBJECT_TO_AREA.get(subject, None)


def get_ranked_users_stats_by_dynamic_score(
    users_ids: list[int], n: int, asking_user_id: int
) -> list[dict]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            WITH ranked_users AS (
    SELECT
        ui.user_id AS id,
        u.username,
        COALESCE(ui.dynamic_score, 0) AS score,
        u.school_id,
        s.name AS school,
        COUNT(squ.id) FILTER (WHERE squ.choice_id IS NOT NULL OR squ.timed_out = true) AS total_answers,
        COUNT(squ.id) FILTER (WHERE c.is_correct) AS correct_answers,
        RANK() OVER (ORDER BY COALESCE(ui.dynamic_score, 0) DESC, ui.user_id ASC) AS rank
    FROM
        quiz_UserInfo ui
    JOIN
        api_User u ON ui.user_id = u.id
    LEFT JOIN
        api_School s ON u.school_id = s.id
    LEFT JOIN
        quiz_sessionquestionuser squ ON squ.user_id = u.id
            AND squ.choice_id IS NOT NULL
    LEFT JOIN
        quiz_Choice c ON squ.choice_id = c.id
    WHERE
        ui.user_id = ANY(%s::int[])
    GROUP BY
        ui.user_id,
        u.username,
        ui.dynamic_score,
        u.school_id,
        s.name
)
SELECT
    id,
    username,
    score,
    school_id,
    COALESCE(school, '') AS school,
    total_answers,
    correct_answers,
    rank
FROM
    ranked_users
WHERE
    rank <= %s
    OR id = %s
ORDER BY
    rank;
            """,
            [users_ids, n, asking_user_id],
        )

        columns = [col[0] for col in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]

    return results


def get_user_percentage_score(user_id: int, subject: str | None = None) -> float:
    """
    Calculate percentage score for a single user.
    Returns the ratio of correct answers to total answers.
    """
    with connection.cursor() as cursor:
        sql = """
            SELECT
                COUNT(squ.id) FILTER (WHERE squ.choice_id IS NOT NULL OR squ.timed_out = true) AS total_answers,
                COUNT(squ.id) FILTER (WHERE c.is_correct) AS correct_answers
            FROM
                quiz_sessionquestionuser squ
            LEFT JOIN
                quiz_choice c ON squ.choice_id = c.id
            JOIN
                quiz_sessionquestion sq ON squ.session_question_id = sq.id
            JOIN
                quiz_question q ON sq.question_id = q.id
            WHERE
                squ.user_id = %s
                {subject_filter}
        """

        params: list[Any] = [user_id]
        if subject:
            sql = sql.format(
                subject_filter="AND q.subject = %s",
            )
            params.append(subject)
        else:
            sql = sql.format(
                subject_filter="",
            )

        cursor.execute(sql, params)
        row = cursor.fetchone()
        if not row:
            return 0.0
        total_answers, correct_answers = row
        return correct_answers / total_answers if total_answers else 0.0


def get_ranked_users_stats_by_percentage(
    users_ids: list[int], n: int, asking_user_id: int, subject: str | None = None
) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        sql = """
            WITH answers_count AS (
                SELECT
                    squ.user_id AS id,
                    COUNT(squ.id) FILTER (WHERE squ.choice_id IS NOT NULL OR squ.timed_out = true) AS total_answers,
                    COUNT(squ.id) FILTER (WHERE c.is_correct) AS correct_answers
                FROM
                    quiz_sessionquestionuser squ
                LEFT JOIN
                    quiz_choice c ON squ.choice_id = c.id
                JOIN
                    quiz_sessionquestion sq ON squ.session_question_id = sq.id
                JOIN
                    quiz_question q ON sq.question_id = q.id
                WHERE
                    squ.user_id = ANY(%s::int[])
                    {subject_filter}
                GROUP BY
                    squ.user_id
                HAVING
                    COUNT(squ.id) > {min_answers}
            ),
            ranked_users AS (
            SELECT
                ac.id,
                u.username,
                COALESCE(ac.correct_answers::float / NULLIF(ac.total_answers, 0), 0) AS score,
                u.school_id,
                s.name AS school,
                ac.total_answers,
                ac.correct_answers,
                RANK() OVER (ORDER BY COALESCE(ac.correct_answers::float / NULLIF(ac.total_answers, 0), 0) DESC, ac.id ASC) AS rank
            FROM
                answers_count ac
            JOIN
                api_User u ON ac.id = u.id
            LEFT JOIN
                api_School s ON u.school_id = s.id
            GROUP BY
                ac.id,
                u.username,
                u.school_id,
                s.name,
                ac.total_answers,
                ac.correct_answers
            )
            SELECT
                id,
                username,
                score,
                school_id,
                COALESCE(school, '') AS school,
                total_answers,
                correct_answers,
                rank
            FROM
                ranked_users
            WHERE
                rank <= %s
                OR id = %s
            ORDER BY
                rank;
            """

        params: list[Any] = [users_ids]
        if subject:
            sql = sql.format(
                subject_filter="AND q.subject = %s",
                min_answers=MIN_ANSWERS_FOR_SUBJECT_IN_PERCENTAGE_RANKING,
            )
            params.append(subject)
        else:
            sql = sql.format(
                subject_filter="",
                min_answers=MIN_ANSWERS_NO_SUBJECT_IN_PERCENTAGE_RANKING,
            )

        params.extend([n, asking_user_id])
        cursor.execute(sql, params)

        columns = [col[0] for col in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]

    return results


def calc_user_stats(user_id: int) -> dict[str, Any]:
    sql_query = f"""
WITH subject_to_area AS (
        VALUES
            {SUBJECT_TO_AREA_TUPLES}
    ),
subcategory_stats AS (
    SELECT
        q_inner.subject,
        q_inner.category,
        q_inner.subcategory,
        COUNT(DISTINCT q_inner.id) AS total_answers,
        COUNT(DISTINCT CASE WHEN qc_inner.is_correct THEN q_inner.id END) AS correct_answers
    FROM
        quiz_sessionquestionuser squ_inner
    JOIN
        quiz_choice qc_inner ON squ_inner.choice_id = qc_inner.id
    JOIN
        quiz_sessionquestion sq_inner ON squ_inner.session_question_id = sq_inner.id
    JOIN
        quiz_question q_inner ON sq_inner.question_id = q_inner.id
    WHERE
        squ_inner.user_id = %s
    GROUP BY
        q_inner.subject,
        q_inner.category,
        q_inner.subcategory
),
limited_answers AS (
        SELECT
            squ_inner.id,
            sq_inner.question_id,
            qc_inner.is_correct,
            sta.column2 AS area,
            ROW_NUMBER() OVER (
                PARTITION BY sta.column2
                ORDER BY squ_inner.timestamp DESC
            ) AS rn
        FROM
            quiz_sessionquestionuser squ_inner
        JOIN
            quiz_choice qc_inner ON squ_inner.choice_id = qc_inner.id
        JOIN
            quiz_sessionquestion sq_inner ON squ_inner.session_question_id = sq_inner.id
        JOIN
            quiz_question q_inner ON sq_inner.question_id = q_inner.id
        JOIN
            subject_to_area sta ON q_inner.subject = sta.column1
        WHERE
            squ_inner.user_id = %s
    ),
    area_correct_counts AS (
        SELECT
            area,
            COUNT(DISTINCT CASE WHEN is_correct THEN question_id END) AS correct_answers
        FROM
            limited_answers
        WHERE
            rn <= %s
        GROUP BY
            area
    ),
total_stats AS (
    SELECT
        SUM(total_answers) AS total_answers,
        SUM(correct_answers) AS correct_answers
    FROM
        subcategory_stats
),
subjects_json AS (
    SELECT
        COALESCE(
            json_agg(
                json_build_object(
                    'subject', ss.subject,
                    'category', ss.category,
                    'subcategory', ss.subcategory,
                    'total_answers', ss.total_answers,
                    'correct_answers', ss.correct_answers
                )
            ), '[]'
        ) AS subjects
    FROM
        subcategory_stats ss
),
area_corrects_json AS (
    SELECT
        COALESCE(
            json_agg(
                json_build_object(
                    'area', acc.area,
                    'correct_answers', acc.correct_answers
                )
            ), '[]'
        ) AS area_corrects
    FROM
        area_correct_counts acc
)
SELECT
    ts.total_answers,
    ts.correct_answers,
    sj.subjects,
    acj.area_corrects
FROM
    total_stats ts,
    subjects_json sj,
    area_corrects_json acj;
    """

    with connection.cursor() as cursor:
        cursor.execute(sql_query, [user_id, user_id, MAX_QUESTIONS_FOR_SCORE])
        row = cursor.fetchone()

    # Initialize subject_performance with known areas, subjects, categories, subcategories
    subject_performance: dict[
        str,
        dict[
            str,
            dict[
                str, dict[str, dict[Literal["total_answers", "correct_answers"], int]]
            ],
        ],
    ] = {
        area: {
            subject: {
                category: {
                    subcategory: {"total_answers": 0, "correct_answers": 0}
                    for subcategory in SUBCATEGORIES.get(category, [])
                }
                for category in CATEGORIES.get(subject, [])
            }
            for subject in subjects
        }
        for area, subjects in ENEM_AREAS.items()
    }

    # Add 'Outros' area for unknown entries
    subject_performance["Outros"] = {
        "Outros": {"Outros": {"Outros": {"total_answers": 0, "correct_answers": 0}}}
    }

    # Initialize overall stats
    final_stats = {
        "total_answers": 0,
        "correct_answers": 0,
        "subject_performance": subject_performance,
        "area_expected_scores": {
            area: AVERAGE_SCORES_BY_CORRECT_QUESTIONS.get(area, {}).get(0, 0.0)
            for area in ENEM_AREAS.keys()
        },
        "score": 0.0,
    }

    # Process SQL result
    if row:
        total_answers, correct_answers, subjects_json, area_corrects_json = row
        final_stats["total_answers"] = total_answers or 0
        final_stats["correct_answers"] = correct_answers or 0

        if subjects_json:
            for subj in subjects_json:
                subject = subj.get("subject", "Outros")
                category = subj.get("category", "Outros")
                subcategory = subj.get("subcategory", "Outros")
                total = subj.get("total_answers", 0)
                correct = subj.get("correct_answers", 0)

                area = SUBJECT_TO_AREA.get(subject, "Outros")

                # Update known subject
                if area != "Outros" and subject in CATEGORIES:
                    if category in CATEGORIES[subject]:
                        if subcategory in SUBCATEGORIES.get(category, []):
                            subject_performance[area][subject][category][subcategory][
                                "total_answers"
                            ] += total
                            subject_performance[area][subject][category][subcategory][
                                "correct_answers"
                            ] += correct
                        else:
                            # Unknown subcategory
                            subject_performance[area][subject][category].setdefault(
                                "Outros", {"total_answers": 0, "correct_answers": 0}
                            )
                            subject_performance[area][subject][category]["Outros"][
                                "total_answers"
                            ] += total
                            subject_performance[area][subject][category]["Outros"][
                                "correct_answers"
                            ] += correct
                    else:
                        # Unknown category
                        subject_performance[area][subject].setdefault(
                            "Outros",
                            {"Outros": {"total_answers": 0, "correct_answers": 0}},
                        )
                        subject_performance[area][subject]["Outros"]["Outros"][
                            "total_answers"
                        ] += total
                        subject_performance[area][subject]["Outros"]["Outros"][
                            "correct_answers"
                        ] += correct
                else:
                    # Unknown subject
                    subject_performance["Outros"]["Outros"]["Outros"]["Outros"][
                        "total_answers"
                    ] += total
                    subject_performance["Outros"]["Outros"]["Outros"]["Outros"][
                        "correct_answers"
                    ] += correct

    # Calculate expected_scores
    for area_entry in area_corrects_json:
        area = area_entry.get("area", "Outros")
        if area in ENEM_AREAS.keys():
            correct_count = area_entry.get("correct_answers", 0)
            expected_score = AVERAGE_SCORES_BY_CORRECT_QUESTIONS.get(area, {}).get(
                correct_count, 0.0
            )
            final_stats["area_expected_scores"][area] = expected_score

    # Calculate overall score as the average of expected scores
    expected_scores = list(final_stats["area_expected_scores"].values())
    final_stats["score"] = (
        sum(expected_scores) / len(expected_scores) if expected_scores else 0.0
    )
    return final_stats


async def acalc_user_stats(
    user_id: int,
) -> dict[str, Any]:
    return await sync_to_async(calc_user_stats)(
        user_id,
    )


async def get_answers_grouped_by_day(
    user: User,
) -> list[dict[str, Any]]:
    answers = (
        SessionQuestionUser.objects.filter(user_id=user.id)
        .select_related(
            "session_question"
        )  # AnswerOut uses session_question, dont remove
        .order_by("timestamp")
        .values(
            "id",
            "timestamp",
            "session_question__session_id",
            "session_question__question_id",
        )
    )

    grouped_answers: dict[datetime.date, dict[str, Any]] = {}
    async for answer in answers:
        date = timezone.localdate(answer["timestamp"])
        if date not in grouped_answers:
            grouped_answers[date] = {"date": date, "total_answers": 0, "answers": []}
        grouped_answers[date]["total_answers"] += 1
        grouped_answers[date]["answers"].append(answer)

    return list(grouped_answers.values())


@currency_transaction(
    action=CurrencyAction.CUSTOM_QUIZ_CREATION,
    transaction_type=CurrencyType.PRICE,
)
async def generate_quiz_from_transcriptions_or_topic(
    user: User,
    is_fast: bool,
    question_blocks: list[str],
    topic: str,
    question_type: QuestionType,
    n_questions_per_block: int | None,
    n_questions_for_topic: int | None,
    subject: str,
) -> dict[str, Any]:
    """
    Generate quiz questions from either transcription blocks or a theme.
    """
    quiz = await Quiz.objects.acreate(
        query=topic if topic else "",
        title=topic if topic else "Quiz de Material",
        question_type=question_type,
        quiz_type=QuizType.CUSTOM,
        created_by=user,
    )

    n_questions_per_block = (
        -(-20 // len(question_blocks)) if len(question_blocks) > 0 else None
    )

    question_instances = await question_service.get_questions_text_from_blocks_or_topic(
        question_blocks=question_blocks,
        topic=topic,
        n_questions_per_block=n_questions_per_block,
        n_questions_for_topic=n_questions_for_topic,
        is_fast=is_fast,
        subject=subject,
    )

    if len(question_instances) > 20:
        question_instances = question_instances[:20]

    questions = await sync_to_async(
        question_service.create_questions_from_question_instances
    )(
        question_instances=question_instances,
    )

    await session_service.aadd_questions_to_session(quiz.id, questions)

    return await aprepare_quiz_out(quiz.id, user.id)
