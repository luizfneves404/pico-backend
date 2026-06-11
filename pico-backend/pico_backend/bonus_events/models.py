from django.db import models


class BonusEvent(models.Model):
    name = models.CharField(max_length=255)
    multiplier = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)
    start_time = models.DateTimeField(null=True)
    end_time = models.DateTimeField(null=True)
    challenges = models.ManyToManyField("challenges.Challenge", blank=True)
    sessions = models.ManyToManyField("quiz.Session", blank=True)
