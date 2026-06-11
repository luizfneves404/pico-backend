import datetime
import logging
import random
import uuid
from collections import defaultdict
from datetime import datetime, timedelta

import api.services.fcm_service as fcm_service
import api.services.user_service as user_service
import currency.currency_service as currency_service
import shared.openai_utils as openai_utils
from api.models import User
from api.services import school_service
from api.services.user_service import STARTING_DUEL_SCORE
from celery import shared_task
from chat.models import UserWebsocketInfo
from currency.models import Currency, CurrencyAction, CurrencyType
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import connection, models
from django.db.models import Count, Q
from django.utils import timezone
from import_export import resources
from import_export.formats import base_formats

import pico_backend.amp as pico_backend_amp
import quiz.bots as bots
import quiz.question_service as question_service
import quiz.quiz_service as quiz_service
import quiz.stats_service as stats_service
from pico_backend.celery import celery_async_workflow
from quiz import duel_service
from quiz.models import (
    Duel,
    Question,
    QuestionSelectionMethod,
    SessionQuestionUser,
    UserInfo,
)

logger = logging.getLogger(__name__)

REWARD_NOTIFICATION_SCHEDULE_DELAY = 2

# Títulos para usuários em sequência
DAILY_QUIZ_REMINDER_TUPLES_ON_STREAK = [
    (
        "Missão dada é missão cumprida!",
        "Mantenha sua sequência de {streak_days} {day_word} como quem cumpre uma missão!",
    ),
    (
        "🚨 Alerta da Polícia da Sequência 🚨",
        "Não corra o risco de perder {your_word} {streak_days} {day_word} {sequence_word}",
    ),
    (
        "Acorda, chuchu!",
        "Completar sua meta de {meta} questões por dia é a chave para o sucesso.",
    ),
    (
        "Parabéns! Você está numa fase incrível!",
        "Venha cumprir sua meta de {meta} questões hoje!",
    ),
]

# Títulos para usuários não em sequência
DAILY_QUIZ_REMINDER_TUPLES_NOT_ON_STREAK = [
    (
        "Missão dada é missão cumprida!",
        "Tá esperando o que? Sua meta não vai se bater sozinha!",
    ),
    (
        "Quer rir? Tem que fazer rir!",
        "Recomeçar é o primeiro passo. Venha cumprir sua meta de {meta} questões!",
    ),
    (
        "Pequenos passos levam longe",
        "Cada estudo conta! Você pode recomeçar agora e fazer a diferença!",
    ),
]

ENEM_DATE = None  # Data do primeiro dia do ENEM. None porque não achei na internet


def add_embedding_to_question(question_id: int):
    question = Question.objects.get(id=question_id)
    logger.debug(f"Adding embedding to question '{question.full_text_with_extra}'")
    question.embedding = openai_utils.compute_embedding(question.full_text_with_extra)
    question.save()
    logger.debug(f"Added embedding to question '{question.full_text_with_extra}'")


@shared_task
def task_add_embedding_to_question(question_id: int):
    add_embedding_to_question(question_id)


@shared_task
def task_create_questions(questions: list[str], answers: list[str], source: str = ""):
    question_service.create_questions(questions, answers, source)


@celery_async_workflow
def create_questions_async_workflow(
    questions: list[str], answers: list[str], source: str = ""
):
    task_create_questions.delay(questions, answers, source).forget()


def create_questions_sync_workflow(
    questions: list[str], answers: list[str], source: str = ""
):
    task_create_questions.delay(questions, answers, source).forget()


@shared_task
def schedule_daily_notifications():
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    users = list(User.non_sentinel_objects.all().distinct())

    logger.info(
        "Found %d users to check for scheduling daily notifications.", len(users)
    )

    for user in users:
        if not is_user_active(user, today):
            continue
        schedule_notification_for_user(user, yesterday, today)


def is_user_active(user, today) -> bool:
    """Checks if the user has been inactive for 7 or more days based on their connection date."""
    last_connection_date = get_last_connection_date(user)
    if last_connection_date:
        days_inactive = (today - last_connection_date).days
        logger.debug(
            "User %s last connected %d days ago.", user.username, days_inactive
        )
        return days_inactive < 7
    logger.debug("User %s has no recorded connection activity.", user.username)
    return False


def get_last_quiz_activity_date(user):
    """Returns the last date the user answered a quiz question."""
    last_answer = (
        SessionQuestionUser.objects.filter(user_id=user.id)
        .order_by("-timestamp")
        .first()
    )
    last_quiz_activity_date = (
        timezone.localdate(last_answer.timestamp) if last_answer else None
    )
    logger.debug(
        "User %s last answered a quiz on: %s", user.username, last_quiz_activity_date
    )
    return last_quiz_activity_date


def get_last_connection_date(user):
    """Returns the last date the user was connected via WebSocket."""
    last_connection = UserWebsocketInfo.objects.filter(user=user).first()
    if last_connection:
        last_connection_date = timezone.localdate(
            last_connection.last_websocket_connection
        )
        logger.debug(
            "User %s last WebSocket connection date: %s",
            user.username,
            last_connection_date,
        )
        return last_connection_date
    logger.debug("User %s has no recorded WebSocket connections.", user.username)
    return None


def schedule_notification_for_user(user, yesterday, today):
    """Schedules notification based on the user's quiz activity."""
    localtime_today_midnight = timezone.make_aware(
        datetime.combine(today, datetime.min.time()),
        timezone=timezone.get_current_timezone(),
    )

    first_quiz_time_yesterday = get_first_quiz_local_time(user, yesterday)

    if first_quiz_time_yesterday:
        # User had activity yesterday
        all_quiz_answers = list(
            SessionQuestionUser.objects.filter(user_id=user.id)
            .order_by("-timestamp")
            .values("id", "timestamp")
        )
        _, streak_days = user_service.get_streak_info(
            [answer["timestamp"] for answer in all_quiz_answers]
        )
        title, body = random.choice(DAILY_QUIZ_REMINDER_TUPLES_ON_STREAK)
        day_word = "dia" if streak_days == 1 else "dias"
        your_word = "seu" if streak_days == 1 else "seus"
        sequence_word = "seguido" if streak_days == 1 else "seguidos"
        body_formatted = safe_format(
            body,
            streak_days=streak_days,
            day_word=day_word,
            your_word=your_word,
            sequence_word=sequence_word,
            meta=user.commitment,
        )
        eta = first_quiz_time_yesterday + timedelta(hours=24)
        schedule_notification(user.id, title, body_formatted, eta)
    else:
        # User had no activity yesterday
        last_quiz_activity_date = get_last_quiz_activity_date(user)
        if last_quiz_activity_date:
            days_inactive = (today - last_quiz_activity_date).days
            logger.debug(
                "User %s has been inactive for %d days in terms of quiz activity.",
                user.username,
                days_inactive,
            )
            first_quiz_time = get_first_quiz_local_time(user, last_quiz_activity_date)
            extracted_hour = first_quiz_time.hour if first_quiz_time else 19
            extracted_minute = first_quiz_time.minute if first_quiz_time else 0
            title, body = random.choice(DAILY_QUIZ_REMINDER_TUPLES_NOT_ON_STREAK)
            body_formatted = safe_format(body, meta=user.commitment)
            eta = localtime_today_midnight + timedelta(
                hours=extracted_hour, minutes=extracted_minute
            )
            schedule_notification(user.id, title, body_formatted, eta)
        else:
            logger.debug(
                "User %s has no quiz activity to schedule notifications.",
                user.username,
            )


def get_first_quiz_local_time(user, local_date):
    """Returns the timestamp of the user's first quiz on a given date."""
    first_answer = (
        SessionQuestionUser.objects.filter(user_id=user.id, timestamp__date=local_date)
        .order_by("timestamp")
        .first()
    )
    return timezone.localtime(first_answer.timestamp) if first_answer else None


def schedule_notification(user_id, title, body, eta):
    logger.debug(f"Scheduling notification for user {user_id} at {eta}")
    send_notification.apply_async(
        (user_id, title, body),
        eta=eta,
    ).forget()


def safe_format(s, **kwargs):
    return s.format_map(defaultdict(str, **kwargs))


@shared_task
def send_notification(user_id, title, body):
    """Sends a notification if the user hasn't taken a quiz today."""
    today = timezone.localdate()
    quiz_answers = SessionQuestionUser.objects.filter(
        user_id=user_id,
        timestamp__date__gte=today,
    )

    if not quiz_answers.exists():
        logger.debug(
            "User of id %s did not take a quiz today. Sending notification.", user_id
        )
        # The user did not take a quiz today, send the notification
        fcm_service.send_notification([user_id], title, body)
    else:
        logger.debug(
            "User of id %s already took a quiz today. Skipping notification.", user_id
        )


@shared_task(ignore_result=False)
def export_answers_celery(queryset_ids: list[int]):
    queryset = SessionQuestionUser.objects.filter(id__in=queryset_ids).select_related(
        "user",
        "session_question",
        "session_question__session",
        "session_question__question",
        "choice",
    )
    dataset = AnswerResource().export(queryset)
    csv_file = base_formats.CSV().export_data(dataset)

    filename = f"answer_export_{uuid.uuid4()}.csv"
    path = default_storage.save(f"exports/{filename}", ContentFile(csv_file))

    return path


@shared_task
def task_maybe_track_commitment_hit(user_id: int, len_created_answers: int):
    user = User.objects.get(id=user_id)
    today = timezone.localdate()
    num_answers_after = SessionQuestionUser.objects.filter(
        user_id=user.id, timestamp__date=today
    ).count()
    num_answers_before = num_answers_after - len_created_answers
    if user.commitment and num_answers_before < user.commitment <= num_answers_after:
        pico_backend_amp.track_amplitude_event(
            user.id,
            "Commitment Goal Hit",
        )


@shared_task
def task_update_score(user_id: int) -> None:
    user_info, _ = UserInfo.objects.get_or_create(
        user_id=user_id, defaults={"duel_score": STARTING_DUEL_SCORE}
    )
    quiz_service.update_score(user_id, user_info)


@shared_task
def task_duel_cleanup():
    """Gets sent to redis queue by Amazon Lambda every 5 minutes, in order to delete cancelled duels and mark abandoned duels."""
    delete_cancelled_duels()
    mark_abandoned_duels()
    bot_join_and_answer_duels()


def delete_cancelled_duels():
    """Delete duels that meet the following criteria:
    - The duel is in_progress
    - There is only one confirmed participant
    - 24 hours have passed since the duel was created
    """
    cutoff = timezone.now() - timedelta(hours=24)
    sessions_qs = (
        Duel.objects.filter(
            duel_status="in_progress",
            created_at__lt=cutoff,
        )
        .annotate(
            confirmed_count=models.Count(
                "session_participation_set",
                filter=models.Q(session_participation_set__confirmed=True),
            )
        )
        .filter(confirmed_count=1)
    )
    deleted_ids = list(sessions_qs.values_list("id", flat=True))
    sessions_qs.delete()
    logger.info(f"Deleted {len(deleted_ids)} cancelled duels: {deleted_ids}")


def mark_abandoned_duels():
    """Mark duels as abandoned that meet the following criteria:
    - The duel is in_progress
    - The current turn has unanswered questions after 24 hours of its start_time

    When a duel is identified as abandoned:
    - The duel status is changed to 'abandoned'
    - The winner is set to the opponent of the inactive player (the player whose turn it currently is)
    - The current turn reference is cleared by setting it to NULL
    """
    with connection.cursor() as cursor:
        sql = """
        WITH inactive_duels AS (
            SELECT 
                s.id AS session_id,
                t.user_id AS inactive_user_id
            FROM quiz_session s
            JOIN quiz_turn t ON s.current_turn_id = t.id
            JOIN quiz_round r ON t.round_id = r.id
            WHERE s.session_type = 'duel'
              AND s.duel_status = 'in_progress'
              AND (%s - t.start_time) > interval '24 hours'
              AND (
                  -- Check if unanswered questions exist in current round
                  SELECT COUNT(squ.id)
                  FROM quiz_sessionquestion sq
                  LEFT JOIN quiz_sessionquestionuser squ 
                    ON squ.session_question_id = sq.id 
                    AND squ.user_id = t.user_id
                  WHERE sq.session_id = s.id
                    AND sq.order BETWEEN (r._order * s.n_questions_per_round)
                        AND ((r._order + 1) * s.n_questions_per_round - 1)
              ) < s.n_questions_per_round
        )
        
        UPDATE quiz_session s
        SET duel_status = 'abandoned',
            current_turn_id = NULL,
            winner_id = (
                SELECT user_id
                FROM quiz_sessionparticipation
                WHERE session_id = s.id
                AND user_id != d.inactive_user_id
                AND confirmed = true
            ) -- this should never be NULL since the cancelled duels are deleted above
        FROM inactive_duels d
        WHERE s.id = d.session_id
        RETURNING s.id AS session_id, duel_status, winner_id;
        """

        cursor.execute(sql, [timezone.now()])
        updated_rows = cursor.fetchall()

    if updated_rows:
        for row in updated_rows:
            session_id, duel_status, winner_id = row
            logger.info(
                f"Updated session {session_id}: status set to '{duel_status}', winner_id set to '{winner_id}'."
            )
    else:
        logger.info("No inactive duels found or updated.")


def bot_join_and_answer_duels():
    """Joins duels that meet the following criteria:
    - The duel is in_progress
    - The duel is part of a tournament
    - There is only one confirmed participant
    - The current_turn is not the first turn
    If so, a bot from a different school of the user joins the duel.
    Then, all bots answer the questions of the duels that they are in.
    """
    # Step 1: Find tournament duels with only one participant that aren't on the first turn
    eligible_duels = (
        Duel.objects.filter(
            duel_status="in_progress",
            tournament_id__isnull=False,
        )
        .annotate(
            confirmed_count=Count(
                "session_participation_set",
                filter=Q(session_participation_set__confirmed=True),
            )
        )
        .filter(confirmed_count=1)
        .exclude(
            current_turn__round___order=0,
            current_turn___order=0,
        )
    )

    # Step 2: Add bots to eligible duels
    for duel in eligible_duels:
        # Get the human player
        human_user = (
            duel.session_participation_set.filter(confirmed=True)
            .select_related("user")
            .first()
            .user
        )

        # Find a bot from a different school
        bot = (
            User.objects.filter(is_bot=True)
            .exclude(school=human_user.school)
            .order_by("?")
            .first()
        )

        duel_service.join_duel_by_tournament(bot.id, duel.tournament_id)

    # Step 3: Find all duels where a bot needs to make a move
    bot_duels = Duel.objects.filter(
        duel_status="in_progress",
        current_turn__user__is_bot=True,
    ).select_related("current_turn__user")

    # Step 4: Have bots make their moves
    for duel in bot_duels:
        # Get the bot that needs to make a move
        bot = duel.current_turn.user

        # Get the human player to use their weak subcategories
        human_user = (
            duel.session_participation_set.filter(confirmed=True, user__is_bot=False)
            .select_related("user")
            .first()
            .user
        )

        if (
            duel.selection_method == QuestionSelectionMethod.QUERY_OFFICIAL
            and duel.current_turn._order == 0
        ):
            # Add questions based on human player's weak areas
            weak_subcategories = list(
                stats_service.identify_weak_subcategories(human_user.id)
            )
            if weak_subcategories:
                query = random.choice(weak_subcategories)
            else:
                query = ""
            duel_service.add_questions_to_duel_by_query(
                bot.id,
                duel.id,
                query=query,
                area="",
                source_filter="",
                difficulty="",
                is_fast=duel.is_fast,
            )

        # Bot makes its move
        bots.do_random_turn(bot, duel, correct_chance=bot.bot_difficulty)


def schedule_push_notification(
    user_ids: list[int], title: str, body: str, eta: datetime
):
    task_send_push_notification.apply_async(
        (user_ids, title, body),
        eta=eta,
    ).forget()


@shared_task
def task_send_push_notification(user_ids: list[int], title: str, body: str):
    fcm_service.send_notification(user_ids, title, body)


@shared_task
def task_reward_dynamic_ranking():
    try:
        currency = Currency.get_default(
            CurrencyAction.DYNAMIC_RANKING_REWARD, CurrencyType.REWARD
        )
    except Currency.DoesNotExist:
        logger.warning("No currency found for dynamic ranking reward")
        currency = None

    if currency:
        # Reward top 3 users according to dynamic score, scheduling a push notification
        top_3_users = list(
            UserInfo.objects.order_by("-dynamic_score", "-user_id").select_related(
                "user"
            )[:3]
        )
        for user_info in top_3_users:
            currency_service.handle_currency_transaction(
                user_info.user,
                CurrencyAction.DYNAMIC_RANKING_REWARD,
                CurrencyType.REWARD,
            )

        user_ids = [user_info.user.id for user_info in top_3_users]
        schedule_push_notification(
            user_ids,
            "Você ficou no top 3 da semana!",
            f"Você está no top 3 do ranking de pontuação dinâmica! Dê uma olhada nas suas novas {currency.value} moedas!",
            timezone.localtime() + timedelta(hours=REWARD_NOTIFICATION_SCHEDULE_DELAY),
        )
        logger.info(
            "Rewarded top 3 users according to dynamic score: %s",
            [user_info.user.username for user_info in top_3_users],
        )

    try:
        currency = Currency.get_default(
            CurrencyAction.SCHOOL_DYNAMIC_RANKING_REWARD, CurrencyType.REWARD
        )
    except Currency.DoesNotExist:
        logger.warning("No currency found for school dynamic ranking reward")
        currency = None

    if currency:
        # Reward the users of the school with highest dynamic score, scheduling a push notification
        school_ranking = school_service.get_school_ranking()
        if school_ranking and len(school_ranking) > 0:
            school_id = school_ranking[0]["id"]
            school_name = school_ranking[0]["name"]

            users = list(User.objects.filter(school_id=school_id, is_bot=False))
            for user in users:
                currency_service.handle_currency_transaction(
                    user,
                    CurrencyAction.SCHOOL_DYNAMIC_RANKING_REWARD,
                    CurrencyType.REWARD,
                )

            if users:
                user_ids = [user.id for user in users]
                schedule_push_notification(
                    user_ids,
                    "Sua escola foi a melhor da semana!",
                    f"Sua escola ficou em 1º lugar no ranking de pontuação dinâmica! Você ganhou {currency.value} moedas!",
                    timezone.localtime()
                    + timedelta(hours=REWARD_NOTIFICATION_SCHEDULE_DELAY),
                )
                logger.info(
                    "Rewarded users of school with highest dynamic score: %s. Users: %s",
                    school_name,
                    [user.username for user in users],
                )


@shared_task
def task_reset_dynamic_scores():
    logger.info("Resetting dynamic scores for all users.")
    UserInfo.objects.all().update(dynamic_score=0)
    logger.info("Dynamic scores reset for all users.")


class AnswerResource(resources.ModelResource):
    """DO NOT USE DIRECTLY ON ADMIN RESOURCE CLASS. IT WILL BREAK THE SERVER.
    Use SessionQuestionUserAdmin.export_answers_async instead.
    """

    user = resources.Field(readonly=True)
    question = resources.Field(readonly=True)
    session = resources.Field(readonly=True)
    choice = resources.Field(readonly=True)
    is_correct = resources.Field(readonly=True)
    session_type = resources.Field(readonly=True)

    class Meta:
        use_bulk = True
        model = SessionQuestionUser
        fields = (
            "id",
            "user",
            "session",
            "session_type",
            "question",
            "choice",
            "is_correct",
            "submitted_text",
            "feedback",
            "grade",
            "timestamp",
        )

    def dehydrate_user(self, answer):
        return answer.user.username if answer.user else None

    def dehydrate_session(self, answer):
        return answer.session_question.session.id

    def dehydrate_question(self, answer):
        return answer.session_question.question.id

    def dehydrate_is_correct(self, answer):
        return answer.choice.is_correct if answer.choice else None

    def dehydrate_choice(self, answer):
        return answer.choice.id if answer.choice else None

    def dehydrate_session_type(self, answer):
        return answer.session_question.session.session_type
