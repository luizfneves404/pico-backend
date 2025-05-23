from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MinValueValidator
from django.db import models

User = get_user_model()


class CurrencyType(models.TextChoices):
    PRICE = "price", "Price"
    REWARD = "reward", "Reward"


class CurrencyAction(models.TextChoices):
    # User related actions
    USER_REFERRED_ANOTHER = "user_referred_another", "User Referred Another"
    ANOTHER_USER_REFERRED_ME = "another_user_referred_me", "Another User Referred Me"

    # Ranking related actions
    DYNAMIC_RANKING_REWARD = "dynamic_ranking_reward", "Dynamic Ranking Reward"
    SCHOOL_DYNAMIC_RANKING_REWARD = (
        "school_dynamic_ranking_reward",
        "School Dynamic Ranking Reward",
    )

    # Quiz related actions
    CUSTOM_QUIZ_CREATION = "custom_quiz_creation", "Custom Quiz Creation"
    CUSTOM_QUIZ_JOIN = "custom_quiz_join", "Custom Quiz Join"
    QUIZ_CREATION = "quiz_creation", "Quiz Creation"
    QUIZ_JOIN = "quiz_join", "Quiz Join"

    # Duel related actions
    CUSTOM_DUEL_CREATION = "custom_duel_creation", "Custom Duel Creation"
    CUSTOM_DUEL_JOIN = "custom_duel_join", "Custom Duel Join"
    DUEL_CREATION = "duel_creation", "Duel Creation"
    DUEL_JOIN = "duel_join", "Duel Join"

    # Essay related actions
    ESSAY_CREATION = "essay_creation", "Essay Creation"

    # Challenge related actions
    CUSTOM_CHALLENGE_CREATION = "custom_challenge_creation", "Custom Challenge Creation"
    CUSTOM_CHALLENGE_JOIN = "custom_challenge_join", "Custom Challenge Join"
    CUSTOM_CHALLENGE_COMMISSION = (
        "custom_challenge_commission",
        "Custom Challenge Commission",
    )
    CHALLENGE_CREATION = "challenge_creation", "Challenge Creation"
    CHALLENGE_JOIN = "challenge_join", "Challenge Join"
    CHALLENGE_COMMISSION = "challenge_commission", "Challenge Commission"


class Currency(models.Model):
    id = models.BigAutoField(primary_key=True)
    value = models.PositiveIntegerField(
        validators=[MinValueValidator(0)]  # Changed from 1 to 0
    )
    currency_type = models.CharField(max_length=10, choices=CurrencyType.choices)
    action = models.CharField(
        max_length=50, choices=CurrencyAction.choices
    )  # Changed from category
    is_default = models.BooleanField(default=False)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Generic relation to allow linking to different types of objects
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True, blank=True
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    related_object = GenericForeignKey("content_type", "object_id")

    class Meta:
        verbose_name_plural = "currencies"
        constraints = [
            # Ensure only one default currency per action/type combination
            models.UniqueConstraint(
                fields=["action", "currency_type", "is_default"],
                condition=models.Q(is_default=True),
                name="unique_default_currency_per_action_type",
            ),
            # Ensure action values are valid
            models.CheckConstraint(
                condition=models.Q(action__in=CurrencyAction.values),
                name="valid_currency_action",
            ),
        ]

    def __str__(self):
        return f"{self.value} ({self.get_currency_type_display()} - {self.get_action_display()})"

    @classmethod
    def get_default(cls, action: CurrencyAction, currency_type: CurrencyType):
        """Get the default currency for a given action"""
        return cls.objects.get(
            action=action, currency_type=currency_type, is_default=True
        )


class Transaction(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="currency_transactions"
    )
    currency = models.ForeignKey(
        Currency,
        on_delete=models.CASCADE,
        related_name="transactions",
        null=True,
        blank=True,
    )
    amount = models.IntegerField(
        null=True,
        blank=True,  # For when using predefined currency
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    description = models.CharField(max_length=255, blank=True)

    # Generic relation for optional linking to sessions/essays
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True, blank=True
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    related_object = GenericForeignKey("content_type", "object_id")

    def __str__(self):
        amount = (
            self.amount
            if self.amount is not None
            else (self.currency.value if self.currency else "unknown")
        )
        return f"{self.user.username} - {amount} coins"

    def get_amount(self) -> int:
        """Returns transaction amount, either from direct amount or currency."""
        if self.amount is not None:
            return self.amount
        elif self.currency:
            return self.currency.value
        else:
            raise ValueError("Transaction must have either an amount or a currency.")
