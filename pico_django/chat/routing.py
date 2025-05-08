from django.urls import path
from chat import consumers

websocket_urlpatterns = [
    path("ws/notifications", consumers.NotificationConsumer.as_asgi()),
]
