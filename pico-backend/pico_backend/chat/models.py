from django.conf import settings
from django.db import models
from django.utils import timezone


class UserWebsocketInfo(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="websocket_info",
    )
    last_websocket_connection = models.DateTimeField(default=timezone.now)
    last_websocket_disconnection = models.DateTimeField(null=True)
