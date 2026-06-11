from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from shared.code_generation import CodeManager, CodeModel

User = get_user_model()

UNIQUE_CONSTRAINT_TOURNAMENT_PARTICIPATION = "unique_tournament_participation"


class ChallengeQuerySet(models.QuerySet):
    def is_happening(self):
        return self.filter(start_date__lte=timezone.localdate()).filter(
            end_date__gte=timezone.localdate()
        )


class ChallengeManager(CodeManager):
    def get_queryset(self):
        return ChallengeQuerySet(self.model, using=self._db)


class ChallengeRole(models.TextChoices):
    PARTICIPANT = "PARTICIPANT", "Participant"
    CREATOR = "CREATOR", "Creator"


class ScoringSystem(models.TextChoices):
    FREQUENCY = "frequency", "Frequency"
    QUANTITY = "quantity", "Quantity"


class Challenge(CodeModel):
    id = models.AutoField(primary_key=True)
    code = models.CharField(
        max_length=5, unique=True
    )  # no need to create an index for the code because django creates it automatically for unique fields
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    start_date = models.DateField()
    end_date = models.DateField()
    scoring_system = models.CharField(max_length=12, choices=ScoringSystem.choices)
    questions_per_day = models.IntegerField(null=True, blank=True, default=10)

    participants = models.ManyToManyField(
        User,
        related_name="challenges_participated",
        through="ChallengeParticipation",
    )

    objects = ChallengeManager()

    def clean(self):
        # Ensure questions_per_day is provided if scoring system is "frequency"
        if self.scoring_system == "frequency" and not self.questions_per_day:
            raise ValidationError(
                "You must specify the number of questions per day for a frequency-based scoring system."
            )
        super().clean()


class ChallengeParticipation(models.Model):
    id = models.AutoField(primary_key=True)
    challenge = models.ForeignKey(
        Challenge, on_delete=models.CASCADE, related_name="participations"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="participations"
    )
    role = models.CharField(max_length=12, choices=ChallengeRole.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - Challenge {self.challenge.id}"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "challenge"], name="unique_participation"
            )
        ]
        indexes = [
            models.Index(fields=["user", "challenge"]),
        ]


class TournamentStatus(models.TextChoices):
    UPCOMING = "upcoming", "Upcoming"
    ONGOING = "ongoing", "Ongoing"
    COMPLETED = "completed", "Completed"


class Tournament(CodeModel):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    status = models.CharField(max_length=12, choices=TournamentStatus.choices)
    participants = models.ManyToManyField(
        User,
        related_name="tournaments_participated",
        through="TournamentParticipation",
    )


class TournamentParticipation(models.Model):
    id = models.AutoField(primary_key=True)
    tournament = models.ForeignKey(
        Tournament,
        on_delete=models.CASCADE,
        related_name="tournament_participation_set",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="tournament_participation_set",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "tournament"], name="unique_tournament_participation"
            )
        ]
        indexes = [
            models.Index(fields=["user", "tournament"]),
        ]


class Prize(models.Model):
    tournament = models.ForeignKey(
        Tournament, related_name="prizes", on_delete=models.CASCADE
    )
    rank = models.PositiveIntegerField()
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Monetary value of the prize (optional)",
    )

    class Meta:
        ordering = ["rank"]
        constraints = [
            models.UniqueConstraint(
                fields=["tournament", "rank"], name="unique_prize_rank"
            )
        ]
