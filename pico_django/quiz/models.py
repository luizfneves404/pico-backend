import logging
import os
import string
import sys
import tempfile
from contextlib import contextmanager
from typing import Literal

from api.models import get_deleted_user
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Count, F
from django.db.models.fields.files import FieldFile
from pgvector.django import HnswIndex, VectorField
from shared.code_generation import CodeManager, CodeModel
from shared.openai_utils import NUMBER_OF_EMBEDDING_DIMENSIONS

logger = logging.getLogger(__name__)

User = get_user_model()

ENEM_AREAS = {
    "Ciências Humanas": [
        "Filosofia",
        "Geografia",
        "História",
        "Sociologia",
    ],
    "Ciências da Natureza": [
        "Biologia",
        "Física",
        "Química",
    ],
    "Linguagens": [
        "Inglês",
        "Português",
        "Espanhol",
    ],
    "Matemática": ["Matemática"],
}

SUBJECT_TO_AREA = {
    subject: area for area, subjects in ENEM_AREAS.items() for subject in subjects
}

CUSTOM_SOURCE = "Custom"

UNIQUE_CONSTRAINT_SESSION_QUESTION_USER_ANSWER = "unique_session_question_user_answer"
UNIQUE_CONSTRAINT_SESSION_USER_PARTICIPATION = "unique_session_user_participant"
CHECK_SESSION_QUESTION_ANSWER_VALID_STATES = "session_question_user_valid_states"


class UserInfo(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="quiz_info"
    )
    math_score = models.FloatField(null=True, blank=True, default=None)
    language_score = models.FloatField(null=True, blank=True, default=None)
    humanities_score = models.FloatField(null=True, blank=True, default=None)
    science_score = models.FloatField(null=True, blank=True, default=None)
    average_score = models.GeneratedField(
        output_field=models.FloatField(),
        expression=(
            F("math_score")
            + F("language_score")
            + F("humanities_score")
            + F("science_score")
        )
        / 4,
        db_persist=True,
    )
    dynamic_score = models.FloatField(blank=True, default=0)
    duel_score = models.FloatField(null=True, blank=True, default=None)


class QuestionType(models.TextChoices):
    MULTIPLE_CHOICE = "multiple_choice", "Multiple choice"
    OPEN_ENDED = "open_ended", "Open-ended"
    ALL = "all", "All"
    NOT_APPLICABLE = "", "Not applicable"


class QuizType(models.TextChoices):
    QUERY_BASED = "query", "Query-based"
    PERSONALIZED = "personalized", "Personalized"
    CUSTOM = "custom", "Custom"
    NOT_APPLICABLE = "", "Not applicable"


class SelectionSource(models.TextChoices):
    RANDOM = "random", "Random"
    TOPIC = "topic", "Topic"
    FILES = "files", "Files"


class QuestionSelectionMethod(models.TextChoices):
    RANDOM_OFFICIAL = "random_official", "Random official"
    QUERY_OFFICIAL = "query_official", "Query official"
    USER_GENERATED = "user_generated", "User-generated"
    FULL = "full", "Full"


class DuelTurnPhase(models.TextChoices):
    ATTACK = "attack", "Attack"
    DEFENSE = "defense", "Defense"


class DuelStatus(models.TextChoices):
    NOT_APPLICABLE = "", "Not applicable"
    IN_PROGRESS = "in_progress", "In progress"
    COMPLETED = "completed", "Completed"
    ABANDONED = "abandoned", "Abandoned"


class QuestionDensity(models.TextChoices):
    NOT_APPLICABLE = "", "Not applicable"
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"


class SessionSuper(models.Model):
    class Meta:
        abstract = True

    session_type = models.CharField(
        max_length=20,
    )

    def save(self, *args, **kwargs):
        """automatically store the proxy class name in the database"""
        self.session_type = self.__class__.__name__.lower()
        super().save(*args, **kwargs)

    def __new__(cls, *args, **kwargs):
        """create an instance corresponding to the proxy_name"""
        proxy_class = cls
        try:
            field_name = SessionSuper._meta.get_fields()[0].name
            proxy_name = kwargs.get(field_name)
            if proxy_name is None:
                proxy_name_field_index = cls._meta.fields.index(
                    cls._meta.get_field(field_name)
                )
                proxy_name = args[proxy_name_field_index]
            proxy_class = getattr(sys.modules[cls.__module__], proxy_name)
        finally:
            return super().__new__(proxy_class)


class Session(SessionSuper, CodeModel):
    id = models.BigAutoField(primary_key=True)
    questions = models.ManyToManyField(
        "quiz.Question",
        through="quiz.SessionQuestion",
        related_name="sessions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    file = models.FileField(upload_to="sessions/files/", blank=True)

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET(get_deleted_user),
        null=True,
        blank=True,
        related_name="sessions_created",
    )

    parent_session = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="child_sessions",
    )

    selection_source = models.CharField(
        blank=True,
        max_length=25,
        choices=SelectionSource.choices,
        default=SelectionSource.TOPIC,
    )

    selection_method = models.CharField(
        blank=True,
        max_length=25,
        choices=QuestionSelectionMethod.choices,
        default=QuestionSelectionMethod.QUERY_OFFICIAL,
    )
    question_density = models.CharField(
        blank=True,
        max_length=25,
        choices=QuestionDensity.choices,
        default=QuestionDensity.NOT_APPLICABLE,
    )

    # quiz fields
    title = models.CharField(max_length=255, blank=True, default="")
    topic = models.TextField(blank=True, default="")
    query = models.TextField(blank=True, default="")
    area = models.CharField(max_length=255, blank=True, default="")
    source_filter = models.CharField(max_length=255, blank=True, default="")
    difficulty = models.CharField(max_length=50, blank=True, default="")
    question_type = models.CharField(
        blank=True,
        max_length=16,
        choices=QuestionType.choices,
        default=QuestionType.NOT_APPLICABLE,
    )

    quiz_type = models.CharField(
        blank=True,
        max_length=16,
        choices=QuizType.choices,
        default=QuizType.NOT_APPLICABLE,
    )  # TODO: should we have this or remove?

    # duel fields

    participants = models.ManyToManyField(
        User,
        related_name="sessions",
        through="quiz.SessionParticipation",
    )

    tournament = models.ForeignKey(
        "challenges.Tournament",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="sessions",
    )

    is_fast = models.BooleanField(default=True)

    n_questions_per_round = models.IntegerField(null=True, blank=True, default=None)

    duel_status = models.CharField(
        blank=True,
        max_length=25,
        choices=DuelStatus.choices,
        default=DuelStatus.NOT_APPLICABLE,
    )
    # current_turn needs to be a field and cannot be computed. Think about the start of the duel: who goes first? You need this field to know it
    current_turn = models.ForeignKey(
        "quiz.Turn",
        on_delete=models.SET(get_deleted_user),
        null=True,
        blank=True,
        related_name="sessions",
    )

    winner = models.ForeignKey(
        User,
        on_delete=models.SET(get_deleted_user),
        null=True,
        blank=True,
        related_name="sessions_winner",
    )
    start_time = models.DateTimeField(default=None, null=True, blank=True)
    end_time = models.DateTimeField(default=None, null=True, blank=True)

    def __str__(self):
        return f"{self.session_type.capitalize()} object ({self.id})"

    @property
    def content_str(self):
        return f"{self.session_type.capitalize()}: {self.title}##{self.area}"

    class Meta:
        verbose_name_plural = "sessions"
        constraints = [
            # ==========================
            # Quiz Constraints
            # --------------------------
            # If session_type is 'quiz', question_type must be one of the allowed values.
            models.CheckConstraint(
                condition=(
                    models.Q(
                        session_type="quiz",
                        question_type__in=(
                            QuestionType.MULTIPLE_CHOICE,
                            QuestionType.OPEN_ENDED,
                            QuestionType.ALL,
                        ),
                    )
                    | ~models.Q(session_type="quiz")
                ),
                name="quiz_question_type_valid",
            ),
            # If session_type is 'quiz', quiz_type must be one of the allowed values.
            models.CheckConstraint(
                condition=(
                    models.Q(
                        session_type="quiz",
                        quiz_type__in=(
                            QuizType.QUERY_BASED,
                            QuizType.PERSONALIZED,
                            QuizType.CUSTOM,
                        ),
                    )
                    | ~models.Q(session_type="quiz")
                ),
                name="quiz_quiz_type_valid",
            ),
            # ==========================
            # Duel Constraints
            # --------------------------
            # If session_type is 'duel', n_questions_per_round must be set and duel_status must be valid.
            models.CheckConstraint(
                condition=(
                    models.Q(
                        session_type="duel",
                        n_questions_per_round__isnull=False,
                        duel_status__in=(
                            DuelStatus.IN_PROGRESS,
                            DuelStatus.COMPLETED,
                            DuelStatus.ABANDONED,
                        ),
                    )
                    | ~models.Q(session_type="duel")
                ),
                name="duel_required_fields_valid",
            ),
            # If session_type is NOT 'duel', ensure duel-specific fields are not set.
            models.CheckConstraint(
                condition=(
                    models.Q(
                        ~models.Q(session_type="duel"),
                        n_questions_per_round__isnull=True,
                        current_turn__isnull=True,
                        duel_status=DuelStatus.NOT_APPLICABLE,
                        winner__isnull=True,
                        tournament__isnull=True,
                    )
                    | models.Q(session_type="duel")
                ),
                name="duel_non_applicable_fields_null",
            ),
            # ==========================
            # Selection Method Constraints
            # --------------------------
            models.CheckConstraint(
                condition=(
                    models.Q(
                        selection_method__in=(
                            QuestionSelectionMethod.RANDOM_OFFICIAL,
                            QuestionSelectionMethod.QUERY_OFFICIAL,
                            QuestionSelectionMethod.USER_GENERATED,
                            QuestionSelectionMethod.FULL,
                        ),
                    )
                ),
                name="selection_method_valid",
            ),
        ]


class ProxyManager(CodeManager):
    def get_queryset(self):
        return super().get_queryset().filter(session_type=self.model.__name__.lower())


class Quiz(Session):
    objects = ProxyManager()

    class Meta:
        proxy = True


class Duel(Session):
    objects = ProxyManager()

    class Meta:
        proxy = True

    @property
    def current_turn_user(self):
        return self.current_turn.user

    @property
    def current_turn_round(self):
        return self.current_turn.round

    @property
    def current_turn_start_time(self):
        return self.current_turn.start_time

    @property
    def current_turn_phase(self):
        return self.current_turn.phase


class Challenge(Session):
    objects = ProxyManager()

    class Meta:
        proxy = True


class Round(models.Model):
    """This is created when the duel starts. It corresponds to n_questions_per_round questions. It contains two turns, one for each user."""

    duel = models.ForeignKey(Duel, on_delete=models.CASCADE)
    users = models.ManyToManyField(User, through="quiz.Turn")
    query = models.TextField(blank=True, default="")

    class Meta:
        order_with_respect_to = "duel"


class Turn(models.Model):
    """This is created when the duel starts. When someone joins the duel, the turns without user have their user set to the joining user."""

    round = models.ForeignKey(Round, on_delete=models.CASCADE)
    user = models.ForeignKey(
        User, on_delete=models.SET(get_deleted_user), null=True, blank=True
    )  # the duel may have been created without specifying a user (who will join later by other means)
    phase = models.CharField(
        max_length=25,
        choices=DuelTurnPhase.choices,
    )
    start_time = models.DateTimeField(
        null=True, blank=True
    )  # this is set after creation, when the turn starts.

    class Meta:
        order_with_respect_to = "round"
        constraints = [
            models.UniqueConstraint(
                fields=["round", "user"],
                name="unique_turn_per_round_and_user",
            )
        ]


class SessionParticipation(models.Model):
    session = models.ForeignKey(
        Session, on_delete=models.CASCADE, related_name="session_participation_set"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="session_participation_set"
    )
    confirmed = models.BooleanField(default=False)

    duel_score_change = models.FloatField(null=True, blank=True, default=None)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["session", "user"],
                name=UNIQUE_CONSTRAINT_SESSION_USER_PARTICIPATION,
            )
        ]


class QuestionQuerySet(models.QuerySet):
    def exclude_inactive(self):
        return self.exclude(is_active=False)

    def filter_by_type(
        self, question_type: QuestionType
    ):  # had to use distinct = True to avoid the choices multiplying the number of questions???
        queryset = self.annotate(num_choices=Count("choices"))
        if question_type == QuestionType.MULTIPLE_CHOICE:
            return queryset.filter(num_choices__gt=0)
        elif question_type == QuestionType.OPEN_ENDED:
            return queryset.filter(num_choices=0)
        else:
            return self


class Question(models.Model):
    id = models.BigAutoField(primary_key=True)
    is_active = models.BooleanField(default=True)
    allow_resubmit = models.BooleanField(default=False)
    subject = models.CharField(max_length=255, blank=True, default="")
    extra_embedding_text = models.TextField(blank=True, default="")
    text = models.TextField(blank=True, default="")
    image = models.ImageField(upload_to="questions", blank=True)
    video_url = models.URLField(blank=True, default="")
    answer_text = models.TextField(blank=True, default="")
    answer_image = models.ImageField(upload_to="answers", blank=True)
    embedding = VectorField(
        dimensions=NUMBER_OF_EMBEDDING_DIMENSIONS, null=True, blank=True
    )
    source = models.CharField(
        max_length=100, blank=True, default=""
    )  # if it doesnt come from an official vestibular, = CUSTOM_SOURCE
    caderno = models.CharField(max_length=255, blank=True, default="")
    caderno_number = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    difficulty = models.CharField(max_length=10, blank=True, default="")
    parameter_A = models.FloatField(null=True, blank=True, default=None)
    parameter_B = models.FloatField(null=True, blank=True, default=None)
    parameter_C = models.FloatField(null=True, blank=True, default=None)
    category = models.CharField(max_length=100, blank=True, default="")
    subcategory = models.CharField(max_length=100, blank=True, default="")
    is_fast = models.BooleanField(default=False)

    objects = QuestionQuerySet.as_manager()

    @property
    def area(self) -> str | None:
        return SUBJECT_TO_AREA.get(self.subject, None)

    @property
    def text_with_source_and_subject(self):
        parts = []

        if self.source:
            parts.append(self.source)

        if self.subject:
            parts.append(self.subject)

        # Always create the prefix with parentheses if either 'source' or 'subject' is available
        prefix = ""
        if parts:
            prefix = f"({' - '.join(parts)}) "

        # Check if 'text' is available and non-empty
        text = self.text if self.text else "No text available"

        # Combine the prefix with the 'text'
        return f"{prefix}{text}"

    @property
    def text_with_source_and_subject_with_extra(self):
        parts = []

        if self.source:
            parts.append(self.source)

        if self.subject:
            parts.append(self.subject)

        # Always create the prefix with parentheses if either 'source' or 'subject' is available
        prefix = ""
        if parts:
            prefix = f"({' - '.join(parts)})"

        if self.extra_embedding_text:
            prefix = f"{prefix} {self.extra_embedding_text}"

        # Check if 'text' is available and non-empty
        text = self.text if self.text else "No text available"

        # Combine the prefix with the 'text'
        return f"{prefix}\n\n{text}"

    @property
    def choices_text(self):
        choices_text = []
        for j, choice in enumerate(self.choices.all()):
            if choice.text:
                choices_text.append(f"{string.ascii_uppercase[j]}) {choice.text}")
            else:
                return ""
        return "\n".join(choices_text)

    @property
    def full_text(self):
        return f"{self.text_with_source_and_subject}\n\n{self.choices_text}"

    @property
    def full_text_with_extra(self):
        return f"{self.text_with_source_and_subject_with_extra}\n\n{self.choices_text}"

    @property
    def full_text_with_categories(self):
        # Start with the base text that includes source and subject
        parts = []

        if self.source:
            parts.append(self.source)

        if self.subject:
            parts.append(self.subject)

        # Add category and subcategory if they exist
        if self.category:
            parts.append(self.category)

        if self.subcategory:
            parts.append(self.subcategory)

        # Create the prefix with parentheses if any metadata is available
        prefix = ""
        if parts:
            prefix = f"({' - '.join(parts)})"

        if self.extra_embedding_text:
            prefix = f"{prefix} {self.extra_embedding_text}"

        # Check if 'text' is available and non-empty
        text = self.text if self.text else "No text available"

        # Combine the prefix with the text and choices
        return f"{prefix}\n\n{text}\n\n{self.choices_text}"

    def __str__(self):
        return self.text if self.text else f"id: {self.id}"

    class Meta:
        indexes = [
            HnswIndex(
                name="new_question_embedding_index",
                fields=["embedding"],
                m=16,
                ef_construction=200,
                opclasses=["vector_cosine_ops"],
            ),
        ]
        ordering = ["id"]


class Choice(models.Model):
    id = models.BigAutoField(primary_key=True)
    question = models.ForeignKey(
        Question, related_name="choices", on_delete=models.CASCADE
    )
    image = models.ImageField(upload_to="choices", blank=True)
    text = models.TextField(blank=True, default="")
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return self.text

    class Meta:
        order_with_respect_to = "question"
        constraints = [
            models.CheckConstraint(
                condition=(
                    (~models.Q(image="") & models.Q(text=""))
                    | (models.Q(image="") & ~models.Q(text=""))
                ),
                name="choice_has_image_xor_text",
            )
        ]


class SessionQuestionQuerySet(models.QuerySet):
    def bulk_create(  # since i have this on the queryset and not on the model manager, overriding the bulk_create also changes abulk_create, since the latter calls the former
        self,
        objs,
        batch_size=None,
        ignore_conflicts=False,
        update_conflicts=False,
        update_fields=None,
        unique_fields=None,
    ):
        if not objs:
            return super().bulk_create(
                objs,
                batch_size=batch_size,
                ignore_conflicts=ignore_conflicts,
                update_conflicts=update_conflicts,
                update_fields=update_fields,
                unique_fields=unique_fields,
            )

        # Single query to get count
        count = self.filter(session=objs[0].session).count()

        # Set sequential orders starting after current count
        for i, obj in enumerate(objs, start=count):
            obj.order = i

        return super().bulk_create(
            objs, batch_size=batch_size, ignore_conflicts=ignore_conflicts
        )


class SessionQuestionManager(models.Manager):
    def get_queryset(self):
        return SessionQuestionQuerySet(self.model, using=self._db)


class SessionQuestion(models.Model):
    session = models.ForeignKey(
        Session, on_delete=models.CASCADE, related_name="session_question_set"
    )
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="session_question_set"
    )
    order = models.PositiveIntegerField(db_index=True)  # No null, no default
    users_answered = models.ManyToManyField(
        User,
        through="quiz.SessionQuestionUser",
        related_name="answered_session_questions",
    )

    objects = SessionQuestionManager()

    class Meta:
        ordering = ["order", "id"]
        unique_together = ["session", "question"]

    def save(self, *args, **kwargs):
        if not self.order and self._state.adding:
            # Only set order on creation and if not already set
            self.order = SessionQuestion.objects.filter(session=self.session).count()
        elif not self.order:
            raise ValueError("order cannot be None")
        super().save(*args, **kwargs)


class SessionQuestionUserQuerySet(models.QuerySet):
    def filter_by_type(self, answer_type: Literal["multiple_choice", "open_ended"]):
        if answer_type == "multiple_choice":
            return self.filter(choice__isnull=False)
        elif answer_type == "open_ended":
            return self.filter(choice__isnull=True)
        else:
            return self


class SessionQuestionUser(models.Model):
    """
    A place to store the information about the user's relationship to a question in a session.
    it can be in one of the 3 following states:
    - seen: the user has seen the question. This is always a temporary state, and should move on to one of the other two states.
        - Representation: choice is None and submitted_text is empty and timed_out is False
    - timed out: the user ran out of time when answering the question.
        - Representation: choice is None and submitted_text is empty and timed_out is True.
    - answered: the user has answered the question.
        - Representation: timed_out is False and one of the following is set: choice or submitted_text.
    in the future we will add a "skipped" state, in which the user has decided to never answer the question.
    For many purposes, it could be useful to count timed_out as an answer, so be careful!
    """

    session_question = models.ForeignKey(
        SessionQuestion,
        on_delete=models.CASCADE,
        related_name="session_question_user_set",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="session_question_user_set",
    )
    choice = models.ForeignKey(
        Choice,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    submitted_text = models.TextField(blank=True, default="")
    timestamp = models.DateTimeField(auto_now_add=True)
    feedback = models.TextField(blank=True, default="")
    grade = models.FloatField(null=True, blank=True, default=None)

    timed_out = models.BooleanField(default=False)

    objects = SessionQuestionUserQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["session_question", "user"],
                name=UNIQUE_CONSTRAINT_SESSION_QUESTION_USER_ANSWER,
            ),
            models.CheckConstraint(
                condition=(
                    (
                        models.Q(choice__isnull=False)  # there is a choice
                        & models.Q(
                            submitted_text__exact=""
                        )  # there is no text submitted
                        & models.Q(timed_out=False)  # the user didnt time out
                    )
                    | (
                        models.Q(choice__isnull=True)  # there is no choice
                        & ~models.Q(submitted_text__exact="")  # there is text submitted
                        & models.Q(timed_out=False)  # the user didnt time out
                    )
                    | (
                        models.Q(choice__isnull=True)  # there is no choice
                        & models.Q(
                            submitted_text__exact=""
                        )  # there is no text submitted
                    )
                ),
                name=CHECK_SESSION_QUESTION_ANSWER_VALID_STATES,
            ),
        ]

    @property
    def is_correct(self):
        return self.choice.is_correct if self.choice else False

    @property
    def session(self):
        return self.session_question.session

    @property
    def question(self):
        return self.session_question.question

    @property
    def question_text(self):
        return self.question.text

    @property
    def question_subject(self):
        return self.question.subject

    @property
    def question_category(self):
        return self.question.category

    @property
    def question_subcategory(self):
        return self.question.subcategory


class Transcription(models.Model):
    """
    Represents a block of transcribed text associated with a session.
    Each session can (and ideally should) have multiple transcription blocks.
    """

    session = models.ForeignKey(
        Session, on_delete=models.CASCADE, related_name="transcriptions"
    )
    title = models.CharField(max_length=255, blank=True, default="")
    block_number = models.PositiveIntegerField()
    block_text = models.TextField()

    class Meta:
        ordering = ["session", "block_number"]
        unique_together = ["session", "block_number"]

    def __str__(self):
        return f"{self.title} - Block {self.block_number}"


@contextmanager
def open_field_file_as_temp(field_file: FieldFile):
    try:
        _, file_extension = os.path.splitext(field_file.name)

        temp_file = tempfile.NamedTemporaryFile(
            mode="r+b", delete=False, suffix=file_extension
        )

        logger.debug(f"Writing {field_file.size} bytes to temp file...")

        for chunk in field_file.chunks():
            temp_file.write(chunk)

        logger.debug(f"Finished writing {field_file.size} bytes to temp file")

        temp_file.close()

        file_path = temp_file.name

        yield file_path

    finally:
        try:
            os.remove(file_path)
            logger.debug("Cleaned up temporary file for field_file")
        except UnboundLocalError:
            logger.debug(
                "UnboundLocalError: file_path is not defined, so no cleanup needed"
            )
