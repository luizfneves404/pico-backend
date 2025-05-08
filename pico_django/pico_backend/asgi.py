"""
ASGI config for pico_backend project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os

from app.config import settings

# Set DJANGO_SETTINGS_MODULE *before* importing any Django modules
if os.environ.get("DJANGO_SETTINGS_MODULE") != settings.django_settings_module:
    print(
        f"Warning: DJANGO_SETTINGS_MODULE is being overridden. "
        f"{os.environ.get('DJANGO_SETTINGS_MODULE')} -> {settings.django_settings_module}"
    )
os.environ["DJANGO_SETTINGS_MODULE"] = settings.django_settings_module

# This import must come after the env var is set
import django

django.setup()

import chat.routing  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from chat.amp_middleware import AmplitudeMiddleware  # noqa: E402
from chat.json_token_auth import JWTAuthenticationMiddleware  # noqa: E402
from django.core.asgi import get_asgi_application  # noqa: E402

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
