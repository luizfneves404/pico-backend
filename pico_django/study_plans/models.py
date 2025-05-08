from django.contrib.auth import get_user_model
from django.db import models

# Create your models here.

User = get_user_model()


class StudyPlan(models.Model):
    id = models.AutoField(primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True)
    calendar = models.JSONField(null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
