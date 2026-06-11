from pico_backend.test_settings import *

""" INSTALLED_APPS.append("debug_toolbar")
INSTALLED_APPS.append("django_extensions")
MIDDLEWARE.append("debug_toolbar.middleware.DebugToolbarMiddleware") """

# enable sql logging
LOGGING["loggers"]["django.db.backends"] = {
    "handlers": ["console"],
    "level": "DEBUG",
    "propagate": False,
}
