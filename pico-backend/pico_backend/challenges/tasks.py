import logging

import api.services.fcm_service as fcm_service
from celery import shared_task
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.db import connection
from django.utils import timezone
from quiz.models import SessionQuestionUser

from challenges.models import Challenge, ScoringSystem

logger = logging.getLogger(__name__)

User = get_user_model()

NUM_CORRECT_ANSWERS_FOR_NOTIFICATION = 5


@shared_task
def task_check_send_challenge_notifications(
    answers_ids: list[int],
):
    today = timezone.localdate()
    instances = list(
        SessionQuestionUser.objects.filter_by_type("multiple_choice")
        .filter(id__in=answers_ids)
        .values("user_id", "choice__is_correct", "id")
    )
    num_answers_after = (
        SessionQuestionUser.objects.filter_by_type("multiple_choice")
        .filter(
            user_id=instances[0]["user_id"],
            timestamp__date=today,
        )
        .count()
    )
    num_answers_submitted = len(instances)
    num_answers_before = num_answers_after - num_answers_submitted
    num_correct_answers_after = (
        SessionQuestionUser.objects.filter_by_type("multiple_choice")
        .filter(
            user_id=instances[0]["user_id"],
            choice__is_correct=True,
            timestamp__date=today,
        )
        .count()
    )
    num_correct_answers_submitted = sum(
        1 for instance in instances if instance["choice__is_correct"]
    )
    num_correct_answers_before = (
        num_correct_answers_after - num_correct_answers_submitted
    )
    user_id = instances[0]["user_id"]
    user = User.objects.get(id=user_id)
    for challenge in (
        Challenge.objects.filter(participants__id=user_id)
        .is_happening()
        .prefetch_related("participants")
    ):
        if challenge.scoring_system == ScoringSystem.FREQUENCY.value:
            if (
                num_answers_before < challenge.questions_per_day <= num_answers_after
                and not someone_else_has_hit_commitment(challenge, user_id)
            ):
                logger.debug(
                    f"User {user.username} was the first to hit their daily quota in challenge {challenge.id}, sending notifications"
                )
                send_notifications_to_users_about_friend(
                    user.username, challenge, set(challenge.participants.all()) - {user}
                )
            else:
                logger.debug(
                    f"Not sending notifications to users about friend commitment for user {user.username} because either they didn't hit the daily quota of challenge {challenge.id} or someone else has hit it on the challenge"
                )
        elif challenge.scoring_system == ScoringSystem.QUANTITY.value:
            if (
                num_correct_answers_before
                < NUM_CORRECT_ANSWERS_FOR_NOTIFICATION
                <= num_correct_answers_after
                and not someone_else_has_hit_num_correct_answers(
                    challenge.id, user_id, NUM_CORRECT_ANSWERS_FOR_NOTIFICATION
                )
            ):
                logger.debug(
                    f"User {user.username} was the first to hit num correct answers in challenge {challenge.id}, sending notifications"
                )
                send_notifications_to_users_about_friend(
                    user.username, challenge, set(challenge.participants.all()) - {user}
                )
            else:
                logger.debug(
                    f"Not sending notifications to users about friend num correct answers for user {user.username} because either they didn't hit the num correct answers quota of challenge {challenge.id} on this request or someone else has hit it on the challenge"
                )


def someone_else_has_hit_num_correct_answers(
    challenge_id: int, user_id: int, num_correct_answers: int
) -> bool:
    # Get the current date in the local timezone
    local_today = timezone.localdate()

    with connection.cursor() as cursor:
        cursor.execute(
            """
            WITH participant_users AS (
                SELECT u.id
                FROM api_user u
                INNER JOIN challenges_challengeparticipation ccp ON u.id = ccp.user_id
                WHERE ccp.challenge_id = %s
                  AND u.id != %s
            ),
            correct_answers AS (
                SELECT u.id AS user_id, COUNT(*) AS correct_count
                FROM participant_users u
                INNER JOIN quiz_sessionquestionuser squ ON squ.user_id = u.id
                INNER JOIN quiz_choice c ON squ.choice_id = c.id
                WHERE DATE(squ.timestamp AT TIME ZONE %s) = %s
                  AND c.is_correct = TRUE
                GROUP BY u.id
            )
            SELECT EXISTS (
                SELECT 1
                FROM correct_answers
                WHERE correct_count >= %s
            ) AS has_user_hit_goal;
        """,
            [
                challenge_id,
                user_id,
                str(timezone.get_current_timezone()),
                local_today.isoformat(),
                num_correct_answers,
            ],
        )

        result = cursor.fetchone()
    return result[0] if result else False


def someone_else_has_hit_commitment(challenge: Challenge, user_id: int) -> bool:
    # Get the current date in the local timezone
    local_today = timezone.localdate()

    with connection.cursor() as cursor:
        cursor.execute(
            """
            WITH participant_users AS (
                SELECT u.id
                FROM api_user u
                INNER JOIN challenges_challengeparticipation ccp ON u.id = ccp.user_id
                WHERE ccp.challenge_id = %s
                  AND u.id != %s
            ),
            user_answers AS (
                SELECT u.id AS user_id, COUNT(DISTINCT squ.id) AS answer_count
                FROM participant_users u
                INNER JOIN quiz_sessionquestionuser squ ON squ.user_id = u.id
                WHERE DATE(squ.timestamp AT TIME ZONE %s) = %s
                GROUP BY u.id
            )
            SELECT EXISTS (
                SELECT 1
                FROM user_answers
                WHERE answer_count >= %s
            ) AS has_user_hit_goal;
        """,
            [
                challenge.id,
                user_id,
                str(timezone.get_current_timezone()),
                local_today.isoformat(),
                challenge.questions_per_day,
            ],
        )

        result = cursor.fetchone()
    return result[0] if result else False


def send_notifications_to_users_about_friend(
    friend_username: str, challenge: Challenge, users: set[AbstractBaseUser]
):
    if challenge.scoring_system == ScoringSystem.FREQUENCY.value:
        title = f"{friend_username} bateu a meta do desafio!"
        body = f"Não fique pra trás! Faça {challenge.questions_per_day} questões hoje para ganhar pontos no desafio {challenge.name} também!"
    elif challenge.scoring_system == ScoringSystem.QUANTITY.value:
        title = f"{friend_username} já fez {NUM_CORRECT_ANSWERS_FOR_NOTIFICATION} questões corretas hoje!"
        body = (
            "Não fique pra trás! Acerte mais questões pra subir no ranking do desafio!"
        )
    else:
        raise ValueError(f"Unknown scoring system {challenge.scoring_system}")
    for user in users:
        fcm_service.send_notification(
            user.id,
            title,
            body,
        )
