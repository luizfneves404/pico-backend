from api.models import User
from django.db import models


class Badge(models.Model):
    id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=255)
    description = models.TextField()
    level = models.SmallIntegerField()
    image = models.ImageField(upload_to="badges/")
    prize = models.IntegerField()
    users_earned = models.ManyToManyField(
        User, related_name="badges_earned", through="UserBadge"
    )

    def __str__(self) -> str:
        return self.title


class UserBadge(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    is_redeemed = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "badge"], name="unique_user_badge")
        ]
