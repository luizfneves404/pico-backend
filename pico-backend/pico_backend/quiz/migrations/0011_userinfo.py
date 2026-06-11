import logging
from datetime import datetime, timedelta

from asgiref.sync import async_to_sync
from django.conf import settings
from django.db import migrations, models, transaction
from django.utils import timezone
from django.utils.timezone import localtime

logger = logging.getLogger(__name__)


def get_normalized_streak(streak: int):
    return min(streak, 20) / 20


def calc_streak_info(ordered_timestamps: list[datetime]):
    streak = 0
    today = timezone.localdate()
    done_today = False
    last_processed_date = None

    for timestamp in ordered_timestamps:
        current_date = localtime(timestamp).date()
        if last_processed_date == current_date:
            continue
        last_processed_date = current_date

        if streak == 0:
            if current_date == today:
                done_today = True
                streak += 1
            elif current_date == today - timedelta(days=1):
                streak += 1
            else:
                break
        else:
            if current_date == today - timedelta(
                days=streak + 1 if not done_today else streak
            ):
                streak += 1
            else:
                break

    return done_today, streak


def calculate_combined_score(
    normalized_total_answers, normalized_streak, proportion_correct
):
    return round(
        (
            normalized_total_answers * (1 / 3)
            + normalized_streak * (1 / 6)
            + proportion_correct * (1 / 2)
        )
        * 60,
        2,
    )


def get_streak_info(user_answers: list) -> tuple[bool, int]:
    timestamps = [answer.timestamp for answer in user_answers]
    return calc_streak_info(timestamps)


async def get_users_stats_no_subject_performance(apps, users) -> list[dict]:
    UserQuizAnswer = apps.get_model("quiz", "UserQuizAnswer")
    logger.debug("Starting to compute user statistics without subject performance.")
    # Pre-fetching all necessary data in one go
    user_quiz_answers = (
        UserQuizAnswer.objects.select_related("user_quiz__user", "choice")
        .order_by("-timestamp")
        .filter(user_quiz__user__in=users)
    )

    # Aggregating scores for the users in user_queryset
    user_scores = {
        user.id: {
            "user": user,
            "total_answers": 0,
            "correct_answers": 0,
            "answers_for_score": [],
            "answers": [],
        }
        for user in users
    }

    async for answer in user_quiz_answers:
        user = answer.user_quiz.user
        user_id = user.id
        if user_id not in user_scores:
            user_scores[user_id] = {
                "user": user,
                "total_answers": 0,
                "correct_answers": 0,
                "answers_for_score": [],
                "answers": [],
            }

        user_scores[user_id]["answers"].append(answer)
        user_scores[user_id]["total_answers"] += 1
        if answer.choice.is_correct:
            user_scores[user_id]["correct_answers"] += 1

        if len(user_scores[user_id]["answers_for_score"]) < 100:
            user_scores[user_id]["answers_for_score"].append(answer)

    # Calculating additional fields and the final score
    users_list = []
    for user_id, scores in user_scores.items():
        correct_answers_for_score = sum(
            1 for ans in scores["answers_for_score"] if ans.choice.is_correct
        )
        total_answers_for_score = len(scores["answers_for_score"])

        proportion_correct = (
            correct_answers_for_score / total_answers_for_score
            if total_answers_for_score
            else 0
        )

        normalized_total_answers = (
            total_answers_for_score / 100 if total_answers_for_score else 0
        )
        done_today, streak = get_streak_info(scores["answers"])
        normalized_streak = get_normalized_streak(streak)

        combined_score = calculate_combined_score(
            normalized_total_answers,
            normalized_streak,
            proportion_correct,
        )

        users_list.append(
            {
                "id": user_id,
                "username": scores["user"].username,
                "streak": streak,
                "done_today": done_today,
                "school": scores["user"].school,
                "score": combined_score,
                "total_answers": scores["total_answers"],
                "correct_answers": scores["correct_answers"],
            }
        )
    return users_list


async def update_score(apps, user):
    UserInfo = apps.get_model("quiz", "UserInfo")
    logger.debug(f"Updating score for user {user.username}.")

    score = (await get_users_stats_no_subject_performance(apps, [user]))[0]["score"]

    user_info, created = await UserInfo.objects.aget_or_create(
        user=user, defaults={"score": score}
    )

    if not created:
        user_info.score = score
        await user_info.asave()

    logger.debug(f"User {user.username} score updated to {user_info.score}")


def update_user_scores(apps, schema_editor):
    User = apps.get_model("api", "User")

    # Fetch all users
    users = User.objects.all()

    with transaction.atomic():
        for user in users:
            async_to_sync(update_score)(apps, user)


def noop(apps, schema_editor):
    # No-op function for reverse migration
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("quiz", "0010_question_difficulty"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserInfo",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("score", models.FloatField(default=0)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=models.CASCADE,
                        related_name="quiz_info",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.RunPython(update_user_scores, reverse_code=noop),
    ]
