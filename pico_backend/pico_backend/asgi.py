"""
ASGI config for pico_backend project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pico_backend.settings")

import django

django.setup()

import chat.routing
from channels.routing import ProtocolTypeRouter, URLRouter
from chat.amp_middleware import AmplitudeMiddleware
from chat.json_token_auth import JWTAuthenticationMiddleware
from django.core.asgi import get_asgi_application

# i probably need to validate allowed_hosts
application = ProtocolTypeRouter(
    {
        "http": get_asgi_application(),
        "websocket": (
            JWTAuthenticationMiddleware(
                AmplitudeMiddleware(URLRouter(chat.routing.websocket_urlpatterns))
            )
        ),
    }
)
