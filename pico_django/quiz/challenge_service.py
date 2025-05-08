import datetime
import json
import logging
from typing import Any, overload

import api.services.fcm_service as fcm_service
import quiz.question_service as question_service
import quiz.session_service as session_service
import quiz.utils as quiz_utils
from api.models import User
from asgiref.sync import sync_to_async
from currency.currency_service import handle_currency_transaction
from currency.models import CurrencyAction, CurrencyType
from django.db import IntegrityError, connection, transaction
from quiz.models import (
    UNIQUE_CONSTRAINT_SESSION_USER_PARTICIPATION,
    Challenge,
    QuestionSelectionMethod,
    QuestionType,
    SessionParticipation,
)
from shared import openai_utils

NUM_QUESTIONS_FOR_CHALLENGE = 20
CHALLENGE_TITLE_SYSTEM_MESSAGE = """
    Você é um professor que gosta de criar desafios para seus alunos.
    Agora você deve criar um título para um desafio baseado em informações do desafio.
    O título deve tentar resumir o assunto do desafio. Deve ser em português brasileiro e curto.
"""
CHALLENGE_TITLE_USER_MESSAGE = """
    Informações sobre o desafio: {info}
"""

logger = logging.getLogger(__name__)


class UserAlreadyInChallenge(Exception):
    pass


class AnswerAlreadySubmitted(Exception):
    pass


class ChallengeNotFound(Exception):
    pass


class QuestionNotFound(Exception):
    pass


async def acreate_and_prepare_challenge(
    user: User,
    to_user_ids: list[int],
    start_time: datetime.datetime,
    end_time: datetime.datetime,
    selection_method: QuestionSelectionMethod,
    query: str = "",
    question_blocks: list[str] = [],
    topic: str = "",
    subject: str = "",
    area: str = "",
    difficulty: str = "",
    source_filter: str = "",
    is_fast: bool = True,
):
    challenge = await acreate_challenge(
        user.id,
        to_user_ids,
        start_time,
        end_time,
        is_fast,
        selection_method,
        query,
        question_blocks,
        topic,
        subject,
        area,
        difficulty,
        source_filter,
    )
    logger.info(
        f"Created challenge by user {user.username}, to user {to_user_ids}, "
        f"with selection method {selection_method}"
    )

    if selection_method == QuestionSelectionMethod.USER_GENERATED:
        action = CurrencyAction.CUSTOM_CHALLENGE_CREATION
    else:
        action = CurrencyAction.CHALLENGE_CREATION
    await sync_to_async(handle_currency_transaction)(
        user=user,
        action=action,
        transaction_type=CurrencyType.PRICE,
        related_object=challenge,
    )

    for to_user_id in to_user_ids:
        title = f"{user.username} te desafiou para um duelo!"
        body = "Confirme sua participação para começar."
        await sync_to_async(fcm_service.send_notification)(
            [to_user_id],
            title,
            body,
        )

    return await sync_to_async(prepare_challenges)(user.id, challenge.id)


async def acreate_challenge(  # GOAT function for creating a challenge
    by_user_id: int,
    to_user_ids: list[int],
    start_time: datetime.datetime,
    end_time: datetime.datetime,
    is_fast: bool,
    selection_method: QuestionSelectionMethod,
    query: str,
    question_blocks: list[str] = [],
    topic: str = "",
    subject: str = "",
    area: str = "",
    difficulty: str = "",
    source_filter: str = "",
):
    """Creates a challenge, taking care of the participants and the questions as well.

    Args:
        to_user_ids (list[int]): the list of user ids to invite to the challenge
        start_time (datetime.datetime): the start time of the challenge
        end_time (datetime.datetime): the end time of the challenge
        is_fast (bool): whether the challenge is fast
        selection_method (QuestionSelectionMethod): the selection method of the challenge
        query (str): the query to use to get the questions
        question_blocks (list[str], optional): the list of question blocks to use to get the questions
        topic (str, optional): the topic to use to get the questions
        subject (str, optional): the subject to use to get the questions
        area (str, optional): the area to use to get the questions
        difficulty (str, optional): the difficulty to use to get the questions
        source_filter (str, optional): the source filter to use to get the questions

    Returns:
        Challenge: the created challenge
    """
    # Determine title based on selection method
    if selection_method == QuestionSelectionMethod.RANDOM_OFFICIAL:
        title = "aleatório"
    elif selection_method == QuestionSelectionMethod.QUERY_OFFICIAL:
        title = query
    elif selection_method == QuestionSelectionMethod.USER_GENERATED:
        title = (
            await openai_utils.aget_completion(
                model="gpt-4o-mini",
                temperature=0,
                messages=[
                    {"role": "system", "content": CHALLENGE_TITLE_SYSTEM_MESSAGE},
                    {
                        "role": "user",
                        "content": CHALLENGE_TITLE_USER_MESSAGE.format(
                            info=question_blocks if question_blocks else topic
                        ),
                    },
                ],
            )
        ).content
    else:
        title = ""

    challenge = await Challenge.objects.acreate(
        created_by_id=by_user_id,
        start_time=start_time,
        end_time=end_time,
        selection_method=selection_method,
        is_fast=is_fast,
        query=query,
        area=area,
        difficulty=difficulty,
        source_filter=source_filter,
        title=title,
    )

    participants = [
        SessionParticipation(
            session_id=challenge.id,
            user_id=by_user_id,
            confirmed=True,
        )
    ]

    for to_user_id in to_user_ids:
        participants.append(
            SessionParticipation(
                session_id=challenge.id,
                user_id=to_user_id,
                confirmed=False,
            )
        )
    if len(participants) > 0:
        await SessionParticipation.objects.abulk_create(
            participants, ignore_conflicts=True
        )

    if selection_method == QuestionSelectionMethod.RANDOM_OFFICIAL:
        questions = await sync_to_async(question_service.get_official_questions)(
            query="",
            n=NUM_QUESTIONS_FOR_CHALLENGE,
            question_type=QuestionType.MULTIPLE_CHOICE,
            area=area,
            subject=subject,
            difficulty=difficulty,
            source_filter=source_filter,
            is_fast=is_fast,
            excluded_user_id=by_user_id,
        )
        await session_service.aadd_questions_to_session(
            challenge.id, [question async for question in questions]
        )
    elif selection_method == QuestionSelectionMethod.QUERY_OFFICIAL:
        questions = await sync_to_async(question_service.get_official_questions)(
            query=query,
            n=NUM_QUESTIONS_FOR_CHALLENGE,
            question_type=QuestionType.MULTIPLE_CHOICE,
            area=area,
            subject=subject,
            difficulty=difficulty,
            source_filter=source_filter,
            is_fast=is_fast,
            excluded_user_id=by_user_id,
        )
        await session_service.aadd_questions_to_session(
            challenge.id, [question async for question in questions]
        )
    elif selection_method == QuestionSelectionMethod.USER_GENERATED:
        # n_questions_per_block should be chosen so that the total number of questions is NUM_QUESTIONS_FOR_CHALLENGE
        n_questions_per_block = (
            -(-NUM_QUESTIONS_FOR_CHALLENGE // len(question_blocks))
            if len(question_blocks) > 0
            else None
        )
        question_instances = (
            await question_service.get_questions_text_from_blocks_or_topic(
                question_blocks=question_blocks,
                topic=topic,
                n_questions_per_block=n_questions_per_block,
                n_questions_for_topic=NUM_QUESTIONS_FOR_CHALLENGE,
                is_fast=is_fast,
                subject=subject,
            )
        )
        # cut out the extra questions if there are more than NUM_QUESTIONS_FOR_CHALLENGE
        question_instances = question_instances[:NUM_QUESTIONS_FOR_CHALLENGE]
        questions = await sync_to_async(
            question_service.create_questions_from_question_instances
        )(question_instances)

        await session_service.aadd_questions_to_session(challenge.id, questions)

    return challenge


def list_challenges(asking_user_id: int) -> list[dict[str, Any]]:
    """Lists the challenges that the user is participating in.

    Args:
        asking_user_id (int): The id of the user asking for the challenges

    Returns:
        list[dict[str, Any]]: A list of challenges that the user is participating in
    """
    challenge_ids = list(
        Challenge.objects.filter(participants__id=asking_user_id)
        .values_list("id", flat=True)
        .distinct()
    )
    return prepare_challenges(asking_user_id, challenge_ids)


def get_challenge_question_detail(
    challenge_id: int, question_id: int
) -> dict[str, Any]:
    """
    Gets the detail of a question in a challenge.

    Args:
        challenge_id (int): The id of the challenge
        question_id (int): The id of the question

    Returns:
        dict[str, Any]: A dictionary containing the question details
    """
    sql = """
    SELECT jsonb_build_object(
        'id', q.id,
        'text', q.text,
        'answer_text', COALESCE(q.answer_text, ''),
        'image', q.image,
        'video_url', COALESCE(q.video_url, ''),
        'source', COALESCE(q.source, ''),
        'difficulty', COALESCE(q.difficulty, ''),
        'category', COALESCE(q.category, ''),
        'subcategory', COALESCE(q.subcategory, ''),
        'subject', COALESCE(q.subject, ''),
        'allow_resubmit', q.allow_resubmit,
        'answer_image', q.answer_image,
        'choices', (
            SELECT COALESCE(jsonb_agg(
                jsonb_build_object(
                    'id', c.id,
                    'text', c.text,
                    'image', c.image,
                    'is_correct', c.is_correct
                )
            ), '[]'::jsonb)
            FROM quiz_choice c
            WHERE c.question_id = q.id
        ),
        'answers', (
            SELECT COALESCE(jsonb_agg(
                jsonb_build_object(
                    'choice_id', squ.choice_id,
                    'submitted_text', squ.submitted_text,
                    'feedback', squ.feedback,
                    'grade', squ.grade,
                    'timestamp', squ.timestamp,
                    'timed_out', COALESCE(squ.timed_out, false),
                    'user', jsonb_build_object(
                        'id', squ.user_id,
                        'username', u.username
                    )
                )
            ), '[]'::jsonb)
            FROM quiz_sessionquestion sq
            JOIN quiz_sessionquestionuser squ ON sq.id = squ.session_question_id
            LEFT JOIN api_user u ON squ.user_id = u.id
            WHERE sq.session_id = %s AND sq.question_id = %s
        )
    ) AS question_data
    FROM quiz_question q
    JOIN quiz_sessionquestion sq ON q.id = sq.question_id
    WHERE sq.session_id = %s AND sq.question_id = %s
    LIMIT 1;
    """

    with connection.cursor() as cursor:
        cursor.execute(sql, [challenge_id, question_id, challenge_id, question_id])
        row = cursor.fetchone()

        if not row:
            raise QuestionNotFound

        result = json.loads(row[0])

        # Update URLs for images
        quiz_utils.update_urls_from_orm([result])

        return result


def invite_to_challenge(user: User, challenge_id: int, user_ids: list[int]):
    """invites a list of users to a challenge. If some of the users are already invited, nothing happens to those.

    Args:
        user (User): the user inviting the other users
        challenge_id (int): the id of the challenge to invite the users to
        user_ids (list[int]): the list of user ids to invite to the challenge
    """
    participants = []
    for user_id in user_ids:
        participants.append(
            SessionParticipation(
                session_id=challenge_id,
                user_id=user_id,
                confirmed=False,
            )
        )
    SessionParticipation.objects.bulk_create(participants, ignore_conflicts=True)

    logger.info(
        f"User {user.username} invited user {user_ids} to challenge {challenge_id}"
    )
    title = f"{user.username} te chamou para um desafio!"
    body = "Confirme sua participação para começar."
    fcm_service.send_notification(
        user_ids,
        title,
        body,
    )


async def join_challenge_by_code(user: User, code: str) -> dict[str, Any]:
    return await sync_to_async(join_challenge_by_code_sync)(user, code)


def join_challenge_by_code_sync(user: User, code: str) -> dict[str, Any]:
    user_id = user.id
    sql = """
    WITH inserted AS (
        INSERT INTO quiz_sessionparticipation (session_id, user_id, confirmed)
        SELECT id, %s, true 
        FROM quiz_session 
        WHERE code = %s AND session_type = 'challenge'
        RETURNING session_id
    )
    SELECT session_id AS challenge_id
    FROM inserted;
    """
    with transaction.atomic():
        with connection.cursor() as cursor:
            try:
                cursor.execute(sql, [user_id, code])
                result = cursor.fetchone()
            except IntegrityError as e:
                if UNIQUE_CONSTRAINT_SESSION_USER_PARTICIPATION in str(e):
                    raise UserAlreadyInChallenge from e
                raise e

        if not result:
            raise ChallengeNotFound

        challenge_id = result[0]
        challenge = Challenge.objects.get(id=challenge_id)

        # Process currency using the shared function
        process_challenge_currency(user, challenge)

    logger.info(f"User {user_id} joined challenge {challenge_id} by code {code}")
    return prepare_challenges(user_id, challenge_id)


async def confirm_challenge_participant(user: User, challenge_id: int):
    try:
        # Use sync_to_async for DB operations
        challenge = await sync_to_async(Challenge.objects.get)(id=challenge_id)

        # Process currency and confirm participation
        @sync_to_async
        def process_transaction():
            with transaction.atomic():
                # Handle currency using shared function
                process_challenge_currency(user, challenge)

                # Confirm participant
                return confirm_challenge_participant_sync(challenge, user.id)

        return await process_transaction()
    except Challenge.DoesNotExist:
        raise ChallengeNotFound


def confirm_challenge_participant_sync(challenge: Challenge, user_id: int):
    participation_qs = SessionParticipation.objects.filter(
        session_id=challenge.id, user_id=user_id
    )
    participation_qs.update(confirmed=True)

    logger.info(
        f"Confirmed participant with user_id {user_id} for challenge {challenge.id}"
    )
    return challenge


def reject_challenge_participant(user_id: int, challenge_id: int):
    SessionParticipation.objects.filter(
        session_id=challenge_id,
        user_id=user_id,
    ).delete()
    logger.info(
        f"Rejected participant with user_id {user_id} for challenge {challenge_id}"
    )


def process_challenge_currency(user: User, challenge: Challenge):
    """
    Process currency transactions for challenge participation.
    Handles both user payment and creator commission.
    """
    with transaction.atomic():
        # Determine action types
        if challenge.selection_method == QuestionSelectionMethod.USER_GENERATED:
            action = CurrencyAction.CUSTOM_CHALLENGE_JOIN
            action_commission = CurrencyAction.CUSTOM_CHALLENGE_COMMISSION
        else:
            action = CurrencyAction.CHALLENGE_JOIN
            action_commission = CurrencyAction.CHALLENGE_COMMISSION

        # Process user's payment
        handle_currency_transaction(
            user=user,
            action=action,
            transaction_type=CurrencyType.PRICE,
            related_object=challenge,
        )

        # Add commission for challenge creator (if different from joiner)
        creator = challenge.created_by
        if creator is not None and creator.id != user.id:
            handle_currency_transaction(
                user=creator,
                action=action_commission,
                transaction_type=CurrencyType.REWARD,
                related_object=challenge,
            )
            logger.info(
                f"Challenge creator (user id: {creator.id}) rewarded for challenge {challenge.id}"
            )


def mark_question_seen(user_id: int, challenge_id: int, question_id: int):
    session_service.mark_question_seen(user_id, challenge_id, question_id)


def mark_question_timed_out(user_id: int, challenge_id: int, question_id: int):
    session_service.mark_question_timed_out(user_id, challenge_id, question_id)


def submit_answer(
    user_id: int, challenge_id: int, question_id: int, answer_choice_id: int
):
    session_service.submit_answer(
        user_id,
        challenge_id,
        question_id,
        answer_choice_id,
    )


async def aprepare_challenges(user_id: int, challenge_ids: list[int]):
    return await sync_to_async(prepare_challenges)(user_id, challenge_ids)


@overload
def prepare_challenges(user_id: int, challenge_ids: int) -> dict[str, Any]: ...


@overload
def prepare_challenges(
    user_id: int, challenge_ids: list[int]
) -> list[dict[str, Any]]: ...


def prepare_challenges(
    user_id: int, challenge_ids: list[int] | int
) -> list[dict[str, Any]] | dict[str, Any]:
    """Prepares a list of challenges to be viewed by a specific user, prepared to comply with quiz/schemas/challenge.py. Should work for all challenge endpoints that return challenges.

    Args:
        user_id (int): the user id of the user to prepare the challenges for
        challenge_ids (list[int] | int): the list of challenge ids to prepare
    Returns:
        list[dict[str, Any]] | dict[str, Any]: a list of challenges with the questions and answers and the participations, and all their info
    Raises:
        ChallengeNotFound: If there is one challenge and it is not found
    """
    if isinstance(challenge_ids, list) and not challenge_ids:
        return []
    ids_list = [challenge_ids] if isinstance(challenge_ids, int) else challenge_ids
    # urls are '' since we want django to get the correct urls (if we get from the sql, it is just a relative path and not the full url)
    query = """
    WITH participation_stats AS (
        SELECT
            sp.session_id,
            sp.user_id,
            COUNT(squ.id) AS total_answers,
            SUM(CASE WHEN c.is_correct THEN 1 ELSE 0 END) AS correct_answers
        FROM quiz_sessionparticipation sp
        JOIN quiz_sessionquestion sq
            ON sp.session_id = sq.session_id
        LEFT JOIN quiz_sessionquestionuser squ
            ON sq.id = squ.session_question_id AND squ.user_id = sp.user_id
        LEFT JOIN quiz_choice c
            ON c.id = squ.choice_id
        GROUP BY sp.session_id, sp.user_id
    )
    SELECT COALESCE(jsonb_agg(challenge_data)::text, '[]') AS data
    FROM (
        SELECT jsonb_build_object(
            -- Challenge basic info (use whatever fields you need)
            'id', ch.id,
            'code', ch.code,
            'title', ch.title,
            'created_at', ch.created_at,
            'start_time', ch.start_time,
            'end_time', ch.end_time,
            'selection_method', ch.selection_method,
            'is_fast', ch.is_fast,
            'query', ch.query,
            'area', ch.area,
            'difficulty', ch.difficulty,
            'source_filter', ch.source_filter,

            -- Nested list of questions_and_answers
            'questions_and_answers',
            (
                SELECT COALESCE(jsonb_agg(
                    jsonb_build_object(
                        'id', q.id,
                        'allow_resubmit', q.allow_resubmit,
                        'subject', q.subject,
                        'text', q.text,
                        'answer_text', q.answer_text,
                        'answer_image', '',
                        'image', '',
                        'video_url', '',
                        'source', q.source,
                        'difficulty', q.difficulty,
                        'category', q.category,
                        'subcategory', q.subcategory,
                        'choices',
                        (
                            SELECT COALESCE(jsonb_agg(
                                jsonb_build_object(
                                    'id', c.id,
                                    'text', c.text,
                                    'image', '',
                                    'is_correct', c.is_correct
                                )
                            ), '[]'::jsonb)
                            FROM quiz_choice c
                            WHERE c.question_id = q.id
                        ),
                        'answers',
                        (
                            SELECT COALESCE(jsonb_agg(
                                jsonb_build_object(
                                    'choice_id', squ.choice_id,
                                    'submitted_text', squ.submitted_text,
                                    'feedback', squ.feedback,
                                    'grade', squ.grade,
                                    'timestamp', squ.timestamp,
                                    'timed_out', squ.timed_out,
                                    'user', jsonb_build_object(
                                        'id', squ.user_id,
                                        'username', u2.username
                                    )
                                )
                            ), '[]'::jsonb)
                            FROM quiz_sessionquestionuser squ
                            LEFT JOIN api_user u2 ON u2.id = squ.user_id
                            WHERE squ.session_question_id = sq.id
                              AND squ.user_id = %s
                        )
                    )
                ), '[]'::jsonb)
                FROM quiz_sessionquestion sq
                JOIN quiz_question q ON q.id = sq.question_id
                WHERE sq.session_id = ch.id
            ),

            -- Nested list of participations (including aggregated stats)
            'participations',
            (
               SELECT COALESCE(jsonb_agg(
                   jsonb_build_object(
                       'user', jsonb_build_object(
                           'id', sp.user_id,
                           'username', u1.username
                       ),
                       'confirmed', sp.confirmed,
                       'total_answers', COALESCE(ps.total_answers, 0),
                       'correct_answers', COALESCE(ps.correct_answers, 0)
                   )
               ), '[]'::jsonb)
               FROM quiz_sessionparticipation sp
               LEFT JOIN participation_stats ps
                  ON ps.session_id = sp.session_id AND ps.user_id = sp.user_id
               LEFT JOIN api_user u1
                  ON u1.id = sp.user_id
               WHERE sp.session_id = ch.id
            )
        ) AS challenge_data
        FROM quiz_session ch
        WHERE ch.id = ANY(%s)
    ) t
    ;
    """

    with connection.cursor() as cursor:
        cursor.execute(query, [user_id, ids_list])
        row = cursor.fetchone()

    sql_result = json.loads(row[0])

    questions_and_answers = [
        question
        for challenge in sql_result
        for question in challenge["questions_and_answers"]
    ]
    quiz_utils.update_urls_from_orm(questions_and_answers)

    try:
        return sql_result[0] if isinstance(challenge_ids, int) else sql_result
    except IndexError:
        raise ChallengeNotFound
