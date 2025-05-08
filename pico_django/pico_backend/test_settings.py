import os
from pathlib import Path

from pico_backend.base_settings import *

from app.config import settings

BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = settings.allowed_hosts

INTERNAL_IPS = [
    # List of IP addresses, as strings, that:
    # - Can access the Django Debug Toolbar
    "127.0.0.1",
    "localhost",
]

STATIC_URL = "/static/"

STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

MEDIA_URL = "/media/"

MEDIA_ROOT = os.path.join(BASE_DIR, "media")

EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"

EMAIL_FILE_PATH = os.path.join(BASE_DIR, "sent_emails")

SERVER_EMAIL = "automatic-test-pico@usepico.com.br"
DEFAULT_FROM_EMAIL = SERVER_EMAIL

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TASK_STORE_EAGER_RESULT = True
CELERY_TASK_SEND_SENT_EVENT = True

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
    "us_east_1": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
}
