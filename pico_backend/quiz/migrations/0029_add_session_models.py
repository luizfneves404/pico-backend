import api.models.user
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("quiz", "0028_alter_quiz_question_type"),  # Update this to your last migration
    ]

    operations = [
        migrations.CreateModel(
            name="Session",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                (
                    "session_type",
                    models.CharField(max_length=20),
                ),
                ("created_at", models.DateTimeField()),
                ("query", models.TextField(blank=True, default="")),
                ("area", models.CharField(blank=True, default="", max_length=255)),
                (
                    "source_filter",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                ("difficulty", models.CharField(blank=True, default="", max_length=50)),
                (
                    "question_type",
                    models.CharField(
                        choices=[
                            ("multiple_choice", "Multiple choice"),
                            ("open_ended", "Open-ended"),
                            ("all", "All"),
                        ],
                        default="multiple_choice",
                        max_length=16,
                    ),
                ),
                (
                    "quiz_type",
                    models.CharField(
                        choices=[
                            ("query", "Query-based"),
                            ("personalized", "Personalized"),
                        ],
                        default="query",
                        max_length=16,
                    ),
                ),
                (
                    "file",
                    models.FileField(
                        blank=True, null=True, upload_to="sessions/files/"
                    ),
                ),
                ("code", models.CharField(max_length=5, unique=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.SET(api.models.user.get_deleted_user),
                        related_name="sessions_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "parent_session",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="child_sessions",
                        to="quiz.session",
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "sessions",
            },
        ),
        migrations.CreateModel(
            name="SessionQuestion",
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
                ("order", models.PositiveIntegerField(db_index=True)),
                (
                    "question",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="quiz.question",
                        related_name="session_question_set",
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="quiz.session",
                        related_name="session_question_set",
                    ),
                ),
            ],
            options={
                "ordering": ["order"],
                "unique_together": {("session", "question")},
            },
        ),
        migrations.CreateModel(
            name="SessionQuestionAnswer",
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
                ("submitted_text", models.TextField(blank=True, default="")),
                ("timestamp", models.DateTimeField()),
                ("feedback", models.TextField(blank=True, default="")),
                ("grade", models.FloatField(blank=True, default=None, null=True)),
                (
                    "choice",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="quiz.choice",
                    ),
                ),
                (
                    "session_question",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="session_question_answer_set",
                        to="quiz.sessionquestion",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="session_question_answer_set",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="session",
            name="questions",
            field=models.ManyToManyField(
                related_name="sessions",
                through="quiz.SessionQuestion",
                to="quiz.Question",
            ),
        ),
        migrations.AddField(
            model_name="sessionquestion",
            name="users_answered",
            field=models.ManyToManyField(
                related_name="answered_session_questions",
                through="quiz.SessionQuestionAnswer",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddConstraint(
            model_name="sessionquestionanswer",
            constraint=models.UniqueConstraint(
                fields=("session_question", "user"),
                name="unique_session_question_user_answer",
            ),
        ),
        migrations.AddConstraint(
            model_name="sessionquestionanswer",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        models.Q(("choice__isnull", True), _negated=True),
                        ("submitted_text__exact", ""),
                    ),
                    models.Q(
                        ("choice__isnull", True),
                        models.Q(("submitted_text__exact", ""), _negated=True),
                    ),
                    _connector="OR",
                ),
                name="session_question_answer_choice_xor_submitted_text",
            ),
        ),
    ]
