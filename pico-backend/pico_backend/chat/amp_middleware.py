import logging

from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model

import pico_backend.amp as pico_backend_amp

User = get_user_model()

logger = logging.getLogger(__name__)

WEBSOCKET_CONNECT_EVENT_TYPE = "Websocket Connect"


class AmplitudeMiddleware(BaseMiddleware):
    def __init__(self, inner):
        super().__init__(inner)
        self.amplitude_client = pico_backend_amp.get_amplitude_client()

    async def __call__(self, scope, receive, send):
        self.user = scope["user"]
        if self.user.is_authenticated:
            pico_backend_amp.track_amplitude_event(
                self.user.id, WEBSOCKET_CONNECT_EVENT_TYPE
            )
        return await super().__call__(scope, receive, send)
