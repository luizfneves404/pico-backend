import logging
from datetime import date
from typing import Any

from api.services import fcm_service
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.db import connection, transaction
from django.db.models import Prefetch
from django.db.utils import IntegrityError

from .models import Challenge, ChallengeParticipation, ChallengeRole, ScoringSystem

logger = logging.getLogger(__name__)

User = get_user_model()


class InvalidChallengeCodeError(Exception):
    pass


class ChallengeNotFoundError(Exception):
    pass


class ChallengeServiceError(Exception):
    pass


class UserNotInChallengeError(Exception):
    pass


class UserAlreadyInChallengeError(Exception):
    pass


def create_challenge(
    name: str,
    description: str,
    start_date: date,
    end_date: date,
    creator: AbstractBaseUser,
    scoring_system: ScoringSystem,
    questions_per_day: int | None = None,
) -> Challenge:
    logger.info(f"Creating challenge: {name} for creator: {creator.id}")
    with transaction.atomic():
        challenge = Challenge.objects.create(
            name=name,
            description=description,
            start_date=start_date,
            end_date=end_date,
            scoring_system=scoring_system,
            questions_per_day=questions_per_day,
        )
        ChallengeParticipation.objects.create(
            challenge=challenge,
            user=creator,
            role=ChallengeRole.CREATOR,
        )
    logger.info(f"Challenge created successfully: {challenge.id}")
    return prepare_challenge(challenge.id)


async def acreate_challenge(
    name: str,
    description: str,
    start_date: date,
    end_date: date,
    creator: AbstractBaseUser,
    scoring_system: ScoringSystem,
    questions_per_day: int | None = None,
) -> Challenge:
    return await sync_to_async(create_challenge)(
        name,
        description,
        start_date,
        end_date,
        creator,
        scoring_system,
        questions_per_day,
    )


def get_challenge(challenge_id: int) -> Challenge:
    logger.info(f"Fetching challenge: {challenge_id}")
    try:
        challenge = Challenge.objects.get(id=challenge_id)
    except Challenge.DoesNotExist:
        raise ChallengeNotFoundError()
    return prepare_challenge(challenge.id)


async def aget_challenge(challenge_id: int) -> Challenge:
    return await sync_to_async(get_challenge)(challenge_id)


def list_challenges(user_id: int) -> list[Challenge]:
    logger.info(f"Listing challenges for user: {user_id}")
    challenges_ids = list(
        Challenge.objects.filter(participations__user_id=user_id).values_list(
            "id", flat=True
        )
    )
    logger.debug(f"Found {len(challenges_ids)} challenges for user: {user_id}")
    return prepare_challenges(challenges_ids)


async def alist_challenges(user_id: int) -> list[Challenge]:
    return await sync_to_async(list_challenges)(user_id)


def add_users_to_challenge(
    challenge_id: int, users_ids: list[int], added_by_user_id: int | None = None
):
    logger.info(f"Adding users {users_ids} to challenge: {challenge_id}")
    challenge_name = Challenge.objects.values_list("name", flat=True).get(
        id=challenge_id
    )
    if added_by_user_id:
        added_by_user_username = User.objects.values_list("username", flat=True).get(
            id=added_by_user_id
        )
    participations = []
    for user_id in users_ids:
        participation = ChallengeParticipation(
            challenge_id=challenge_id,
            user_id=user_id,
            role=ChallengeRole.PARTICIPANT,
        )
        participations.append(participation)
    try:
        ChallengeParticipation.objects.bulk_create(participations)
    except IntegrityError:
        raise UserAlreadyInChallengeError()

    if added_by_user_id:
        fcm_service.send_notification(
            users_ids,
            f"Você foi adicionado ao desafio {challenge_name}",
            f"O usuário {added_by_user_username} acabou de adicionar você ao desafio {challenge_name}. Que comecem os estudos!",
        )
    else:
        fcm_service.send_notification(
            users_ids,
            f"Você foi adicionado ao desafio {challenge_name}",
            f"Você acabou de ser adicionado ao desafio {challenge_name}. Que comecem os estudos!",
        )
    logger.debug(
        f"Added {len(users_ids)} users to challenge {challenge_id} by user {added_by_user_id}"
    )


async def aadd_users_to_challenge(
    challenge_id: int,
    users_ids: list[int],
    added_by_user_id: int | None = None,
):
    return await sync_to_async(add_users_to_challenge)(
        challenge_id, users_ids, added_by_user_id
    )


def join_challenge(challenge_code: str, user_id: int) -> Challenge:
    logger.info(f"User {user_id} joining challenge with code: {challenge_code}")
    challenge_code = challenge_code.upper()[:5]
    validate_challenge_code_format(challenge_code)
    try:
        challenge_id = Challenge.objects.values_list("id", flat=True).get(
            code=challenge_code
        )
    except Challenge.DoesNotExist:
        raise ChallengeNotFoundError()
    try:
        ChallengeParticipation.objects.create(
            challenge_id=challenge_id,
            user_id=user_id,
            role=ChallengeRole.PARTICIPANT,
        )
    except IntegrityError:
        raise UserAlreadyInChallengeError()
    logger.info(f"User {user_id} successfully joined challenge: {challenge_id}")
    return prepare_challenge(challenge_id)


def validate_challenge_code_format(challenge_code: str):
    if not challenge_code.isalnum() or len(challenge_code) != 5:
        raise InvalidChallengeCodeError()


async def ajoin_challenge(challenge_code: str, user_id: int) -> Challenge:
    return await sync_to_async(join_challenge)(challenge_code, user_id)


def leave_challenge(challenge_id: int, user_id: int):
    logger.info(f"User {user_id} leaving challenge: {challenge_id}")
    try:
        ChallengeParticipation.objects.get(
            challenge_id=challenge_id, user_id=user_id
        ).delete()
        logger.info(f"User {user_id} successfully left challenge: {challenge_id}")
    except ChallengeParticipation.DoesNotExist:
        raise UserNotInChallengeError()


async def aleave_challenge(challenge_id: int, user_id: int):
    return await sync_to_async(leave_challenge)(challenge_id, user_id)


def prepare_challenges(challenges_ids: list[int]) -> list[Challenge]:
    logger.info(f"Preparing challenges: {challenges_ids}")
    if not challenges_ids:
        logger.debug("No challenges to prepare")
        return []

    challenges = Challenge.objects.filter(id__in=challenges_ids).prefetch_related(
        Prefetch(
            "participations",
            queryset=ChallengeParticipation.objects.select_related("user"),
        )
    )
    challenges_dict = {challenge.id: challenge for challenge in challenges}

    # total points behavior:
    # 1. get all answers for the challenge (row number 1 will get the first correct answer (if it exists) INSIDE THE CHALLENGE INTERVAL for each question)
    # 2. for each answer, get the bonus event multiplier (only correct answers will be considered. multiplier of the bonus event
    # will be applied only if the answer is associated to the bonus event through the quiz and challenge)
    # 3. answer points will be the product of the bonus event multipliers
    # 4. sum all the answers points
    sql_query = """
WITH answers_for_participation AS (
    SELECT 
        squ.id AS answer_id,
        cp.id AS participation_id,
        squ.timestamp AS answer_timestamp,
        DATE(squ.timestamp AT TIME ZONE 'America/Sao_Paulo') AS answer_date,
        qc.is_correct,
        sq.session_id,
        cp.challenge_id,
        ROW_NUMBER() OVER (
            PARTITION BY cp.id, sq.question_id 
            ORDER BY 
                CASE WHEN qc.is_correct THEN 0 ELSE 1 END,  -- Prioritize correct answers
                squ.timestamp, 
                squ.id
        ) AS row_num
    FROM quiz_sessionquestionuser squ
    JOIN quiz_choice qc ON squ.choice_id = qc.id
    JOIN quiz_sessionquestion sq ON squ.session_question_id = sq.id
    JOIN challenges_challengeparticipation cp ON squ.user_id = cp.user_id
    JOIN challenges_challenge c ON cp.challenge_id = c.id
    WHERE cp.challenge_id = ANY(%s)
      AND DATE(squ.timestamp AT TIME ZONE 'America/Sao_Paulo') BETWEEN c.start_date AND c.end_date
),
correct_answers_with_multipliers AS (
    SELECT
        ap.answer_id,
        ap.participation_id,
        ap.answer_date,
        COALESCE(EXP(SUM(LN(be_c.multiplier))), 1) AS multiplier
    FROM answers_for_participation ap
    LEFT JOIN bonus_events_bonusevent_sessions bes ON bes.session_id = ap.session_id
    LEFT JOIN bonus_events_bonusevent be_q ON bes.bonusevent_id = be_q.id
        AND (be_q.start_time IS NULL OR ap.answer_timestamp >= be_q.start_time)
        AND (be_q.end_time IS NULL OR ap.answer_timestamp <= be_q.end_time)
    LEFT JOIN bonus_events_bonusevent_challenges bec ON bec.challenge_id = ap.challenge_id
    LEFT JOIN bonus_events_bonusevent be_c ON bec.bonusevent_id = be_c.id
        AND be_q.id = bec.bonusevent_id
        AND (be_c.start_time IS NULL OR ap.answer_timestamp >= be_c.start_time)
        AND (be_c.end_time IS NULL OR ap.answer_timestamp <= be_c.end_time)
    WHERE ap.is_correct = TRUE 
      AND ap.row_num = 1
    GROUP BY ap.answer_id, ap.participation_id, ap.answer_date
),
stats_for_participation_in_day AS (
    SELECT 
        ap.participation_id,
        ap.answer_date,
        COUNT(*) AS total_questions_done,
        COALESCE(SUM(ca.multiplier), 0) AS total_points
    FROM answers_for_participation ap
    LEFT JOIN correct_answers_with_multipliers ca
        ON ap.participation_id = ca.participation_id
        AND ap.answer_id = ca.answer_id
    GROUP BY 
        ap.participation_id, 
        ap.answer_date
),
commitment_and_correct AS (
    SELECT 
        sud.participation_id,
        COUNT(DISTINCT sud.answer_date) FILTER (WHERE sud.total_questions_done >= c.questions_per_day) AS active_days,
        SUM(sud.total_points) AS total_points
    FROM stats_for_participation_in_day sud
    JOIN challenges_challengeparticipation cp ON sud.participation_id = cp.id
    JOIN challenges_challenge c ON cp.challenge_id = c.id
    GROUP BY sud.participation_id
)
SELECT
    cp.challenge_id,
    cp.user_id,
    u.username,
    ui.average_score,
    COALESCE(cc.active_days, 0) AS active_days,
    ROUND(COALESCE(cc.total_points, 0)) AS total_points
FROM challenges_challengeparticipation cp
LEFT JOIN commitment_and_correct cc ON cc.participation_id = cp.id
LEFT JOIN quiz_userinfo ui ON cp.user_id = ui.user_id
JOIN api_user u ON cp.user_id = u.id
JOIN challenges_challenge c ON cp.challenge_id = c.id
WHERE cp.challenge_id = ANY(%s);
    """

    with connection.cursor() as cursor:
        cursor.execute(
            sql_query,
            [challenges_ids, challenges_ids],
        )
        user_rankings_data = cursor.fetchall()

    logger.debug("Fetched user rankings data")

    # Organize rankings
    # Structure: {challenge_id: {'commitment': [...], 'correct_questions': [...], 'score_ranking': [...]}}
    rankings_dict: dict[int, dict[str, list[dict[str, Any]]]] = {}
    score_ranking_dict: dict[int, list[dict[str, Any]]] = {}
    for row in user_rankings_data:
        (challenge_id, user_id, username, average_score, active_days, correct_count) = (
            row
        )
        if challenge_id not in rankings_dict:
            rankings_dict[challenge_id] = {
                "commitment": [],
                "correct_questions": [],
            }
            score_ranking_dict[challenge_id] = []

        # Append commitment ranking
        if active_days is not None:
            rankings_dict[challenge_id]["commitment"].append(
                {
                    "id": user_id,
                    "username": username,
                    "score": active_days,
                }
            )
        # Append correct questions ranking
        if correct_count is not None:
            rankings_dict[challenge_id]["correct_questions"].append(
                {
                    "id": user_id,
                    "username": username,
                    "score": correct_count,
                }
            )
        # Append score ranking
        if average_score is not None:
            score_ranking_dict[challenge_id].append(
                {
                    "id": user_id,
                    "username": username,
                    "score": average_score,
                }
            )

    logger.debug("Processed rankings data")

    prepared_challenges = []
    for challenge_id, challenge in challenges_dict.items():
        logger.debug(f"Preparing challenge: {challenge_id}")

        # Assign commitment ranking if applicable
        if challenge.scoring_system == ScoringSystem.FREQUENCY:
            commitment_ranking = rankings_dict.get(challenge_id, {}).get(
                "commitment", []
            )
            # Sort in descending order of score, then ascending by id
            commitment_ranking_sorted = sorted(
                commitment_ranking, key=lambda x: (-x["score"], x["id"])
            )
            setattr(challenge, "commitment_ranking", commitment_ranking_sorted)
        elif challenge.scoring_system == ScoringSystem.QUANTITY:
            correct_questions_ranking = rankings_dict.get(challenge_id, {}).get(
                "correct_questions", []
            )
            # Sort in descending order of score, then ascending by id
            correct_questions_ranking_sorted = sorted(
                correct_questions_ranking, key=lambda x: (-x["score"], x["id"])
            )
            setattr(
                challenge, "correct_questions_ranking", correct_questions_ranking_sorted
            )

        user_infos_for_challenge = [
            {
                "id": user_info["id"],
                "username": user_info["username"],
                "score": user_info["score"],
            }
            for user_info in score_ranking_dict.get(challenge_id, [])
        ]
        # Sort in descending order of score, then ascending by id
        score_ranking_sorted = sorted(
            user_infos_for_challenge, key=lambda x: (-x["score"], x["id"])
        )
        setattr(challenge, "score_ranking", score_ranking_sorted)

        prepared_challenges.append(challenge)

    logger.info(f"Prepared {len(prepared_challenges)} challenges")
    return prepared_challenges


def prepare_challenge(challenge_id: int) -> Challenge:
    return prepare_challenges([challenge_id])[0]


async def aprepare_challenge(challenge_id: int) -> Challenge:
    return await sync_to_async(prepare_challenge)(challenge_id)
