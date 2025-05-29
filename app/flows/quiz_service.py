import asyncio
import json
import logging
import random
import re
import string
from collections import defaultdict
from typing import Any, AsyncGenerator, Literal, overload

from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pylatexenc.latex2text import LatexNodes2Text
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.currency.currency_service import handle_currency_transaction
from app.currency.decorators import currency_transaction
from app.currency.models import CurrencyAction, CurrencyType
from app.flows.models import (
    CUSTOM_SOURCE,
    ENEM_AREAS,
    Choice,
    Question,
)
from app.flows.utils import (
    CATEGORIES,
    SUBCATEGORIES,
    SUBCATEGORIES_TO_PARENT_CATEGORIES,
)
from app.shared import openai_utils
from app.users.models import User

from .constants import (
    AVERAGE_SCORES_BY_CORRECT_QUESTIONS,
    MAX_QUESTIONS_FOR_SCORE,
    OPEN_ENDED_FEEDBACK_MODEL,
    OPEN_ENDED_FEEDBACK_SYSTEM_MESSAGE,
    OPEN_ENDED_FEEDBACK_USER_MESSAGE,
    OPEN_ENDED_TEMPERATURE,
    SYSTEM_MESSAGE_QUESTION_GENERATION_DESCRIPTION,
    SYSTEM_MESSAGE_QUESTION_GENERATION_THEME,
    SYSTEM_MESSAGE_QUESTION_GENERATION_THEME_MATH,
    USER_MESSAGE_QUESTION_GENERATION_DESCRIPTION_MATH,
)

PERSONALIZED_AREA = "Personalizado"


SUBJECTS = sum(ENEM_AREAS.values(), [])

SUBJECT_TO_AREA = {
    subject: area for area, subjects in ENEM_AREAS.items() for subject in subjects
}

SUBJECT_TO_AREA_TUPLES = ",\n".join(
    "('{subject}', '{area}')".format(
        subject=subject.replace("'", "''"), area=area.replace("'", "''")
    )
    for subject, area in SUBJECT_TO_AREA.items()
)

COLLEGE_TO_EXAM = {
    "UFRJ": "ENEM",
    "USP": "FUVEST",
    "PUC": "PUC-Rio",
    "FGV": "FGV",
    "UERJ": "UERJ",
}

COLLEGE_TO_PREDEFINED_QUIZ_ID = {
    "UFRJ": 12900,
    "USP": 12903,
    "UERJ": 12904,
    "FGV": 12911,
    "PUC": 12986,
}

NUM_QUESTIONS_DAILY_QUIZ = 20
NUM_LEARNING_QUESTIONS = 10
NUM_WEAK_SUBCATEGORIES = 5
NUM_QUESTIONS_FOR_WEAK_SUBCATEGORIES = 200
NUM_QUESTIONS_FOR_ALREADY_ANSWERED = 800
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


class QuestionInstance(BaseModel):
    text: str
    choices: list[str]
    correct_choice: str


class QuestionSet(BaseModel):
    questions: list[QuestionInstance]


def create_question(question: str, answer: str, source: str = "") -> Question:
    embedding = openai_utils.compute_embedding(question)
    return Question.objects.create(
        question=question, answer=answer, source=source, embedding=embedding
    )


def create_questions(
    questions: list[str], answers: list[str], source: str = ""
) -> list[Question]:
    embeddings = openai_utils.compute_embedding(questions)
    exam_questions = Question.objects.bulk_create(
        [
            Question(
                text=question,
                answer_text=answer,
                source=source,
                embedding=embedding,
            )
            for question, answer, embedding in zip(questions, answers, embeddings)
        ]
    )
    logger.debug(f"Created {len(exam_questions)} questions")
    return exam_questions


def _create_query_for_user(area_for_query: str, username: str) -> str:
    date_and_time = timezone.localtime().strftime("%d/%m - %H:%M")
    return f"{area_for_query} {date_and_time} - {username}"


async def _get_multiple_choice_questions_from_configs(
    configs: list[dict[str, Any]],
) -> list:
    """
    configs: list of dictionaries with the following keys
    - number: number of questions to get
    - area: area of the questions
    - subject: subject of the questions
    - source_filter: filter for the source of the questions
    - difficulty: difficulty of the questions
    """
    questions = []
    for config in configs:
        questions.extend(
            [
                question
                async for question in question_service.get_official_questions(
                    "",
                    config["number"],
                    config.get("area", ""),
                    config.get("subject", ""),
                    config.get("source_filter", ""),
                    config.get("difficulty", ""),
                    question_type=QuestionType.MULTIPLE_CHOICE,
                )
            ]
        )
    return questions


def _shuffle_science_questions(questions: list) -> list:
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
            area,
            source_filter=source_filter,
            difficulty=difficulty,
            question_type=question_type,
            excluded_ids=previous_questions_ids,
            is_fast=None,
        )

        session_service.add_questions_to_session(quiz.id, questions)
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
            question_type=question_type,
            quiz_type=QuizType.PERSONALIZED,
            created_by=user,
            parent_session_id=parent_quiz_id,
        )

        # Get personalized questions, excluding those from the parent quiz if necessary
        questions = _get_personalized_questions(
            n=n,
            question_type=question_type,
            user=user,
            parent_quiz_id=parent_quiz_id,
        )

        session_service.add_questions_to_session(quiz.id, questions)
        return quiz


""" @currency_transaction(
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

    return await aprepare_quiz_out(quiz.id, user.id) """


def _get_personalized_questions(
    n: int,
    question_type: QuestionType,
    user: User,
    parent_quiz_id: int | None = None,
):
    selector = QuestionSelector(user.id, parent_quiz_id)

    total_questions = n
    learning_questions = n // 2
    questions = selector.get_questions(total_questions, learning_questions)

    AREA_PRIORITY = {
        "Linguagens": 1,
        "Ciências Humanas": 2,
        "Ciências da Natureza": 3,
        "Matemática": 4,
    }

    def get_area_priority(question: Question):
        area = SUBJECT_TO_AREA.get(question.subject, None)
        return AREA_PRIORITY.get(area, 5)

    questions = sorted(questions, key=get_area_priority)

    return questions


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
        parent_quiz_id,
        user.id,
    )

    return await aprepare_quiz_out(quiz.id, user.id)


async def share_quiz_to_users(by_user: User, to_usernames: list[str], quiz_id: int):
    to_users = [
        user
        async for user in User.non_sentinel_objects.filter(
            username__in=to_usernames
        ).exclude(id=by_user.id)
    ]
    quiz = Quiz.objects.filter(id=quiz_id).first()

    if not to_users:
        raise UserNotFound
    if not quiz:
        raise QuizNotFound

    dm_chatrooms = await chatroom_service.get_or_create_dm_chatrooms(by_user, to_users)
    for chatroom in dm_chatrooms:
        await message_service.asend_message(
            sender="pico", chatroom=chatroom, session=quiz, have_embedding=False
        )

    logger.debug(
        f"Quiz with id {quiz_id} shared to users {[to_user.id for to_user in to_users]} by user {by_user.id}"
    )
    return dm_chatrooms


async def update_score(
    db_session: AsyncSession, user_id: int, user_info: UserInfo | None = None
) -> UserInfo:
    logger.debug(f"Updating score for user {user_id}.")

    area_expected_scores = (await calc_user_stats(db_session, user_id))[
        "area_expected_scores"
    ]

    scores = {
        "math_score": area_expected_scores["Matemática"],
        "language_score": area_expected_scores["Linguagens"],
        "humanities_score": area_expected_scores["Ciências Humanas"],
        "science_score": area_expected_scores["Ciências da Natureza"],
    }

    if user_info:
        await update_existing_user_info(db_session, user_info, scores)
    else:
        user_info = UserInfo(user_id=user_id, **scores)
        db_session.add(user_info)
        await db_session.flush()

    logger.debug(
        f"User {user_id} scores updated: math_score={user_info.math_score}, "
        f"language_score={user_info.language_score}, humanities_score={user_info.humanities_score}, "
        f"science_score={user_info.science_score}."
    )
    return user_info


async def update_existing_user_info(
    db_session: AsyncSession, user_info: UserInfo, scores: dict[str, Any]
):
    user_info.math_score = scores["math_score"]
    user_info.language_score = scores["language_score"]
    user_info.humanities_score = scores["humanities_score"]
    user_info.science_score = scores["science_score"]
    await db_session.add(user_info)
    await db_session.flush()


def submit_multiple_choice_answers(
    user: User,
    quiz_id: int,
    questions_and_answers: list[dict[str, Any]],
) -> dict[str, Any]:
    """Submit multiple choice answers for a quiz."""
    with transaction.atomic():
        # Get all session questions for this quiz
        session_questions = list(
            SessionQuestion.objects.select_related("question").filter(
                session_id=quiz_id
            )
        )

        # Create a mapping of question_id to submitted answer data
        question_id_to_submitted_answer = {
            qa["question_id"]: qa for qa in questions_and_answers
        }

        # Get existing answers for these session questions
        session_question_id_to_existing_answer_id = {
            answer.session_question_id: answer.id
            for answer in SessionQuestionUser.objects.filter(
                session_question__in=session_questions, user=user
            )
        }

        answers_to_create = []
        answers_to_update = []
        already_answered_question_ids = []

        # Iterate through session questions and prepare bulk operations
        for session_question in session_questions:
            submitted_answer = question_id_to_submitted_answer.get(
                session_question.question_id
            )
            if not submitted_answer:
                continue

            if session_question.id in session_question_id_to_existing_answer_id:
                if session_question.question.allow_resubmit:
                    answers_to_update.append(
                        SessionQuestionUser(
                            id=session_question_id_to_existing_answer_id[
                                session_question.id
                            ],
                            choice_id=submitted_answer["answer_choice_id"],
                        )
                    )
                else:
                    already_answered_question_ids.append(session_question.question_id)
            else:
                answers_to_create.append(
                    SessionQuestionUser(
                        session_question_id=session_question.id,
                        user_id=user.id,
                        choice_id=submitted_answer["answer_choice_id"],
                    )
                )

        # Log skipped questions if any
        if already_answered_question_ids:
            logger.warning(
                f"Questions {already_answered_question_ids} already submitted and do not allow resubmission. Skipping those and saving the rest."
            )

        # Perform bulk create and update operations
        newly_created_answers = []
        if answers_to_create:
            newly_created_answers = SessionQuestionUser.objects.bulk_create(
                answers_to_create, ignore_conflicts=True
            )
        if answers_to_update:
            SessionQuestionUser.objects.bulk_update(answers_to_update, ["choice_id"])

        # Update user scores
        user_info = UserInfo.objects.filter(user_id=user.id).first()
        scores_before_update = get_scores(user_info)
        updated_user_info = update_score(user.id, user_info)
        scores_after_update = get_scores(updated_user_info)

        # Calculate score increases
        score_increases = calculate_score_increases(
            scores_before_update, scores_after_update
        )

        correct_answer_count = Choice.objects.filter(
            id__in=[answer.choice_id for answer in newly_created_answers],
            is_correct=True,
        ).count()
        if correct_answer_count > 0:
            stats_service.update_dynamic_score(user.id, correct_answer_count)

        # Prepare quiz output
        quiz_out = prepare_quiz_outs(quiz_id, user.id)
        update_quiz_out_with_score_increases(quiz_out, score_increases)

    if newly_created_answers:
        handle_answer_bulk_create(newly_created_answers)
        tasks.task_maybe_track_commitment_hit.delay_on_commit(
            user.id, len(newly_created_answers)
        )
    return quiz_out


async def asubmit_multiple_choice_answers(
    user: User,
    quiz_id: int,
    questions_and_answers: list[dict[str, Any]],
) -> dict[str, Any]:
    return await sync_to_async(submit_multiple_choice_answers)(
        user, quiz_id, questions_and_answers
    )


def get_scores(user_info: UserInfo | None):
    default_scores = {
        "average_score": 0.0,
        "math_score": 0.0,
        "language_score": 0.0,
        "humanities_score": 0.0,
        "science_score": 0.0,
    }
    if not user_info:
        return default_scores

    return {field: getattr(user_info, field) or 0.0 for field in default_scores.keys()}


def calculate_score_increases(before_scores, after_scores):
    return {
        "score_increase": after_scores["average_score"]
        - before_scores["average_score"],
        "math_score_increase": after_scores["math_score"] - before_scores["math_score"],
        "language_score_increase": after_scores["language_score"]
        - before_scores["language_score"],
        "humanities_score_increase": after_scores["humanities_score"]
        - before_scores["humanities_score"],
        "science_score_increase": after_scores["science_score"]
        - before_scores["science_score"],
    }


async def asubmit_open_ended_answers(
    user_id: int, quiz_id: int, question_id: int, submitted_text: str
) -> StreamingResponse:
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
        return StreamingResponse(
            generate_feedback_and_grade_and_save(session_question_user),
            media_type="text/plain",
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


def get_quiz_stats(quiz: Quiz) -> list:
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
    )
    SELECT COALESCE(jsonb_agg(quiz_data)::text, '[]') AS data
    FROM (
      SELECT jsonb_build_object(
          -- Quiz basic info
          'id', qz.id,
          'code', qz.code,
          'created_at', qz.created_at,
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
      WHERE qz.id = ANY(%s)
    ) t;
    """
    with connection.cursor() as cursor:
        cursor.execute(query, [user_id, user_id, ids_list])
        row = cursor.fetchone()

    quizzes = json.loads(row[0])
    quiz_utils.update_urls_from_orm(quizzes, Quiz)

    try:
        return quizzes[0] if isinstance(quiz_ids, int) else quizzes
    except IndexError:
        raise QuizNotFound


class QuestionSelector:
    def __init__(self, user_id: int, parent_quiz_id: int | None = None):
        self.user_id = user_id
        self.excluded_ids = set()
        self.recently_answered_ids = self._get_recently_answered_ids()
        if parent_quiz_id:
            self.parent_related_ids = self._get_parent_related_question_ids(
                parent_quiz_id
            )
        else:
            self.parent_related_ids = set()

        self.excluded_ids.update(self.parent_related_ids)

        logger.debug(f"Initialized QuestionSelector for user_id: {user_id}")

    def get_questions(
        self, total_questions: int, weakest_questions: int
    ) -> list[Question]:
        logger.info(f"Getting {total_questions} questions for user_id: {self.user_id}")

        strategies = [
            (self._get_weak_subcategory_questions, weakest_questions),
            (self._get_weak_category_questions, weakest_questions),
            (self._get_exploring_questions, total_questions),
            (self._get_random_questions, total_questions),
        ]

        questions = []
        learning_questions = 0
        for strategy, limit in strategies:
            if len(questions) < total_questions:
                remaining = min(
                    total_questions - len(questions), limit - learning_questions
                )
                if remaining > 0:
                    new_questions = strategy(remaining)
                    questions.extend(new_questions)
                    self.excluded_ids.update(q.id for q in new_questions)
                    if strategy in [
                        self._get_weak_subcategory_questions,
                        self._get_weak_category_questions,
                    ]:
                        learning_questions += len(new_questions)
                    logger.debug(
                        f"Added {len(new_questions)} questions from {strategy.__name__}"
                    )
            else:
                break

        logger.info(f"Total questions selected: {len(questions)}")
        return questions[:total_questions]

    def _get_weak_subcategory_questions(self, count: int) -> list[Question]:
        weak_subcategories = identify_weak_subcategories(self.user_id)
        logger.debug(f"Weak subcategories: {weak_subcategories}")
        return self._get_questions_for_subcategories(weak_subcategories, count)

    def _get_weak_category_questions(self, count: int) -> list[Question]:
        weak_subcategories = identify_weak_subcategories(self.user_id)
        weak_categories = get_parent_categories(weak_subcategories)
        logger.debug(f"Weak categories: {weak_categories}")
        return self._get_questions_for_categories(weak_categories, count)

    def _get_exploring_questions(self, count: int) -> list[Question]:
        chosen_college = User.objects.get(id=self.user_id).chosen_college
        college_name = chosen_college.name if chosen_college else "Outra"

        source_filter = COLLEGE_TO_EXAM.get(college_name, "All")

        return (
            self._get_more_unanswered_questions(count, source__startswith=source_filter)
            if source_filter != "All"
            else self._get_more_unanswered_questions(count)
        )

    def _get_random_questions(self, count: int) -> list[Question]:
        questions = list(
            Question.objects.exclude_inactive()
            .filter_by_type(QuestionType.MULTIPLE_CHOICE)
            .exclude(id__in=self.excluded_ids)
            .order_by("?")[:count]
        )
        logger.debug(f"Retrieved {len(questions)} random questions")
        return questions

    def _get_more_unanswered_questions(self, count: int, **filters) -> list[Question]:
        questions = list(
            Question.objects.exclude_inactive()
            .filter_by_type(QuestionType.MULTIPLE_CHOICE)
            .exclude(id__in=self.excluded_ids)
            .exclude(id__in=self.recently_answered_ids)
            .filter(**filters)
            .order_by("?")[:count]
        )
        logger.debug(f"Retrieved {len(questions)} unanswered questions")
        return questions

    def _get_questions_for_subcategories(
        self, subcategories: set[str], count: int
    ) -> list[Question]:
        return self._get_more_unanswered_questions(count, subcategory__in=subcategories)

    def _get_questions_for_categories(
        self, categories: set[str], count: int
    ) -> list[Question]:
        return self._get_more_unanswered_questions(count, category__in=categories)

    def _get_recently_answered_ids(self) -> set[int]:
        ids = set(
            SessionQuestionUser.objects.filter(user_id=self.user_id)
            .filter_by_type("multiple_choice")
            .order_by("-timestamp")
            .values_list("session_question__question_id", flat=True)[
                :NUM_QUESTIONS_FOR_ALREADY_ANSWERED
            ]
        )
        logger.debug(f"Retrieved {len(ids)} recently answered question IDs")
        return ids

    def _get_parent_related_question_ids(self, parent_quiz_id: int) -> set[int]:
        """Fetch the IDs of questions from the parent quiz and its child quizzes."""
        parent_question_ids = set(
            Question.objects.filter(sessions__id=parent_quiz_id).values_list(
                "id", flat=True
            )
        )
        logger.debug(
            f"Parent quiz {parent_quiz_id} contains {len(parent_question_ids)} questions"
        )

        child_question_ids = set(
            Question.objects.filter(
                sessions__parent_session_id=parent_quiz_id
            ).values_list("id", flat=True)
        )
        logger.debug(
            f"Child quizzes of parent quiz {parent_quiz_id} contain {len(child_question_ids)} questions"
        )

        return parent_question_ids.union(child_question_ids)


def create_daily_quiz(user_id: int, username: str) -> Quiz:
    logger.info(f"Creating daily quiz for user: {username} (ID: {user_id})")

    formatted_date = format_date(
        timezone.localdate(), format="d 'de' MMMM", locale="pt_BR"
    )
    query = f"{username} - {formatted_date}"
    quiz = Quiz.objects.create(
        query=query,
        area="Quiz do Dia",
        question_type=QuestionType.MULTIPLE_CHOICE,
        quiz_type=QuizType.PERSONALIZED,
        created_by_id=user_id,
    )

    logger.info(f"Created new daily quiz (id: {quiz.id}) for user {username}.")

    selector = QuestionSelector(user_id)
    questions = selector.get_questions(NUM_QUESTIONS_DAILY_QUIZ, NUM_LEARNING_QUESTIONS)
    random.shuffle(questions)

    session_service.add_questions_to_session(quiz.id, questions)
    logger.info(f"Added {len(questions)} questions to the daily quiz (id: {quiz.id})")

    return quiz


def get_total_multiple_choice_questions_per_subcategory():
    return {
        item["subcategory"]: item["total_questions"]
        for item in Question.objects.filter_by_type(QuestionType.MULTIPLE_CHOICE)
        .values("subcategory")
        .annotate(total_questions=Count("id", distinct=True))
        if item["subcategory"]
    }


def get_parent_categories(subcategories: set[str]):
    return set(
        SUBCATEGORIES_TO_PARENT_CATEGORIES.get(subcategory, "")
        for subcategory in subcategories
    )


def get_area_from_subject(subject: str) -> str | None:
    return SUBJECT_TO_AREA.get(subject, None)


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
    skipped_subjects = set()
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


def get_subcategory_data(user_answers) -> list[dict[str, str | int | float]]:
    if not user_answers:
        return []

    subcategory_data = defaultdict(lambda: {"correct": 0, "total_answers": 0})
    for answer in user_answers:
        subcategory = answer["session_question__question__subcategory"]
        if not subcategory:
            continue
        subcategory_data[subcategory]["total_answers"] += 1
        if answer["choice__is_correct"]:
            subcategory_data[subcategory]["correct"] += 1
    total_questions_dict = get_total_multiple_choice_questions_per_subcategory()
    return [
        {
            "subcategory": subcategory,
            "accuracy": (
                (data["correct"] / data["total_answers"])
                if data["total_answers"] > 0
                else 0.0
            ),
            "questions_done": data["total_answers"],
            "total_questions": total_questions_dict.get(subcategory, 0),
        }
        for subcategory, data in subcategory_data.items()
    ]


def identify_weak_subcategories(user_id: int) -> set[str]:
    user_answers = (
        SessionQuestionUser.objects.filter(user_id=user_id)
        .filter_by_type("multiple_choice")
        .order_by("-timestamp")
    )
    user_answers_for_weak_subcategories = user_answers[
        :NUM_QUESTIONS_FOR_WEAK_SUBCATEGORIES
    ].values("session_question__question__subcategory", "choice__is_correct")

    subcategory_data = get_subcategory_data(user_answers_for_weak_subcategories)

    all_subcategories = set(
        get_total_multiple_choice_questions_per_subcategory().keys()
    )

    # Sort subcategories by accuracy (ascending), then by questions done (descending), then by total questions (descending)
    sorted_subcategories = sorted(
        subcategory_data,
        key=lambda x: (x["accuracy"], -x["questions_done"], -x["total_questions"]),
    )

    # Get the weakest subcategories from user data
    weak_subcategories = {
        item["subcategory"] for item in sorted_subcategories[:NUM_WEAK_SUBCATEGORIES]
    }

    # Calculate the number of additional subcategories needed
    num_additional_needed = NUM_WEAK_SUBCATEGORIES - len(weak_subcategories)

    remaining_subcategories = all_subcategories - weak_subcategories

    # Adjust the sample size to the number of available remaining subcategories
    num_to_sample = min(num_additional_needed, len(remaining_subcategories))

    additional_subcategories = set(
        random.sample(
            list(remaining_subcategories),
            num_to_sample,
        )
    )

    return weak_subcategories.union(additional_subcategories)


async def aidentify_weak_subcategories(user_id: int) -> set[str]:
    return await sync_to_async(identify_weak_subcategories)(user_id)


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
) -> list[dict]:
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


async def calc_user_stats(db_session: AsyncSession, user_id: int) -> dict[str, Any]:
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
        session_question_user squ_inner
    JOIN
        choice qc_inner ON squ_inner.choice_id = qc_inner.id
    JOIN
        session_question sq_inner ON squ_inner.session_question_id = sq_inner.id
    JOIN
        question q_inner ON sq_inner.question_id = q_inner.id
    WHERE
        squ_inner.user_id = :user_id
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
            session_question_user squ_inner
        JOIN
            choice qc_inner ON squ_inner.choice_id = qc_inner.id
        JOIN
            session_question sq_inner ON squ_inner.session_question_id = sq_inner.id
        JOIN
            question q_inner ON sq_inner.question_id = q_inner.id
        JOIN
            subject_to_area sta ON q_inner.subject = sta.column1
        WHERE
            squ_inner.user_id = :user_id
    ),
    area_correct_counts AS (
        SELECT
            area,
            COUNT(DISTINCT CASE WHEN is_correct THEN question_id END) AS correct_answers
        FROM
            limited_answers
        WHERE
            rn <= :max_questions
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

    result = await db_session.execute(
        text(sql_query), {"user_id": user_id, "max_questions": MAX_QUESTIONS_FOR_SCORE}
    )
    row = result.fetchone()

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


async def get_answers_grouped_by_day(user: User) -> list[dict]:
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

    grouped_answers = {}
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
        question_type=question_type,
        quiz_type=QuizType.CUSTOM,
        created_by=user,
    )

    n_questions_per_block = (
        -(-20 // len(question_blocks)) if len(question_blocks) > 0 else None
    )

    question_instances = await get_questions_text_from_blocks_or_topic(
        question_blocks=question_blocks,
        topic=topic,
        n_questions_per_block=n_questions_per_block,
        n_questions_for_topic=n_questions_for_topic,
        is_fast=is_fast,
        subject=subject,
    )

    if len(question_instances) > 20:
        question_instances = question_instances[:20]

    questions = await sync_to_async(create_questions_from_question_instances)(
        question_instances=question_instances,
    )

    await session_service.aadd_questions_to_session(quiz.id, questions)

    return await aprepare_quiz_out(quiz.id, user.id)


async def get_questions_text_from_blocks_or_topic(
    question_blocks: list[str],
    topic: str,
    n_questions_per_block: int | None,
    n_questions_for_topic: int | None,
    is_fast: bool,
    subject: str,
) -> list[QuestionInstance]:
    """
    Generate question text from either transcription blocks or a theme.
    Returns a list of QuestionInstance objects.
    """
    all_questions = []
    logger.debug(f"Getting questions from blocks: {question_blocks}")

    is_math = True if subject in ["Matemática", "Física", "Química"] else False

    if question_blocks:
        # Filter out empty blocks and create tasks for each valid block
        tasks = [
            generate_question_set_from_description(
                block.strip(), "", n_questions_per_block, is_math
            )
            for block in question_blocks
            if block and block.strip() and n_questions_per_block
        ]

        if tasks:
            # Execute all tasks concurrently
            question_sets = await asyncio.gather(*tasks)
            # Extend all_questions with questions from each set
            for question_set in question_sets:
                all_questions.extend(question_set.questions)
    else:
        if topic.strip() and n_questions_for_topic:
            question_set = await generate_questions_from_topic(
                topic.strip(), "", n_questions_for_topic, is_math
            )
            all_questions.extend(question_set.questions)

    logger.debug(f"Got questions from blocks or topic: {all_questions}")
    return all_questions


def create_questions_from_question_instances(
    question_instances: list[QuestionInstance],
) -> list[Question]:
    """
    Generate questions from a question set.
    Returns a list of Question objects.
    """
    all_questions = []
    all_choices = []

    with transaction.atomic():
        # Prepare questions and choices for bulk create
        questions_to_create = [
            Question(
                text=q.text,
                source=CUSTOM_SOURCE,
                is_active=False,
            )
            for q in question_instances
        ]

        # Bulk create questions
        created_questions = Question.objects.bulk_create(questions_to_create)
        all_questions.extend(created_questions)

        # Prepare choices for bulk create
        for question, q in zip(created_questions, question_instances):
            choices = [
                Choice(
                    question=question,
                    text=choice_text,
                    is_correct=string.ascii_uppercase[i] == q.correct_choice.upper(),
                    _order=i,
                )
                for i, choice_text in enumerate(q.choices)
            ]
            all_choices.extend(choices)

        # Bulk create all choices
        if all_choices:
            Choice.objects.bulk_create(all_choices)

    return all_questions


async def generate_question_set_from_description(
    description: str, extra_instructions: str, num_questions: int, is_math: bool
) -> QuestionSet:
    if not is_math:
        # Regular non-math question generation
        user_message = (
            f"Com base no seguinte conteúdo, gere {num_questions} questões:\n\n"
            f"Descrição: {description}\n\n"
        )

        if extra_instructions:
            user_message += f"\nInstruções extras: {extra_instructions}"

        return (
            await openai_utils.get_completion_parsed(
                model="gpt-4o",
                temperature=0.5,
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_MESSAGE_QUESTION_GENERATION_DESCRIPTION,
                    },
                    {"role": "user", "content": user_message},
                ],
                response_format=QuestionSet,
                timeout=30,
            )
        ).content
    else:
        # Math question generation using o3-mini model
        user_message = (
            f"Com base no seguinte conteúdo, gere {num_questions} questões:\n\n"
            f"Descrição:\n{description}"
        )

        if extra_instructions:
            user_message += f"\nInstruções extras: {extra_instructions}"

        response = await openai_utils.get_completion_parsed(
            model="o3-mini",
            messages=[
                {
                    "role": "system",
                    "content": USER_MESSAGE_QUESTION_GENERATION_DESCRIPTION_MATH,
                },
                {"role": "user", "content": user_message},
            ],
            response_format=QuestionSet,
            reasoning_effort="high",
            timeout=60,
        )

        # Retorna o conteúdo analisado e os tokens utilizados
        question_set = response.content
        tokens_used = response.tokens_used
        logger.info(f"Tokens used: {tokens_used}")

        # Create new QuestionInstance objects with delatexified text
        delatexified_questions = []
        for question in question_set.questions:
            delatexified_question = QuestionInstance(
                text=LatexNodes2Text().latex_to_text(question.text),
                choices=[
                    LatexNodes2Text().latex_to_text(choice)
                    for choice in question.choices
                ],
                correct_choice=question.correct_choice,
            )
            delatexified_questions.append(delatexified_question)

        return QuestionSet(questions=delatexified_questions)


async def generate_questions_from_topic(
    topic: str, extra_instructions: str, num_questions: int, is_math: bool
) -> QuestionSet:
    if not is_math:
        # Regular non-math question generation
        user_message = (
            f"Com base no seguinte tema, gere {num_questions} questões:\n\n"
            f"Tema: {topic}\n\n"
        )

        if extra_instructions:
            user_message += f"\nInstruções extras: {extra_instructions}"

        response = await openai_utils.get_completion_parsed(
            model="gpt-4o",
            temperature=0.5,
            messages=[
                {"role": "system", "content": SYSTEM_MESSAGE_QUESTION_GENERATION_THEME},
                {"role": "user", "content": user_message},
            ],
            response_format=QuestionSet,
            timeout=60,
        )
        logger.info(f"Tokens used: {response.tokens_used}")
        return response.content
    else:
        user_message = (
            f"Com base no seguinte tema, gere {num_questions} questões:\n\n"
            f"Tema:\n{topic}"
        )

        response = await openai_utils.get_completion_parsed(
            model="o3-mini",
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_MESSAGE_QUESTION_GENERATION_THEME_MATH,
                },
                {"role": "user", "content": user_message},
            ],
            response_format=QuestionSet,  # Especifica o formato de resposta esperado
            reasoning_effort="high",
            timeout=60,
        )

    # Retorna o conteúdo analisado e os tokens utilizados
    question_set = response.content
    tokens_used = response.tokens_used
    logger.info(f"Tokens used: {tokens_used}")

    # Create new QuestionInstance objects with delatexified text
    delatexified_questions = []
    for question in question_set.questions:
        delatexified_question = QuestionInstance(
            text=LatexNodes2Text().latex_to_text(question.text),
            choices=[
                LatexNodes2Text().latex_to_text(choice) for choice in question.choices
            ],
            correct_choice=question.correct_choice,
        )
        delatexified_questions.append(delatexified_question)

    return QuestionSet(questions=delatexified_questions)
