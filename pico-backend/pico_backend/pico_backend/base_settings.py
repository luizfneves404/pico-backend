import json
from datetime import timedelta
from pathlib import Path

from decouple import config
from firebase_admin import credentials, initialize_app

BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config("SECRET_KEY")
DB_NAME = config("DB_NAME")
DB_PASSWORD = config("DB_PASSWORD")
DB_USER = config("DB_USER")
DB_HOST = config("DB_HOST")
DB_PORT = config("DB_PORT")
REDIS_HOST = config("REDIS_HOST")
REDIS_PORT = config("REDIS_PORT")
FIREBASE_JSON_SERVICE_KEY = str(config("FIREBASE_JSON_SERVICE_KEY"))
OPENAI_API_KEY = str(config("OPENAI_API_KEY"))
PEN_TO_PRINT_RAPIDAPI_KEY = str(config("PEN_TO_PRINT_RAPIDAPI_KEY"))
AMPLITUDE_API_KEY = str(config("AMPLITUDE_API_KEY"))
AMPLITUDE_SECRET_KEY = str(config("AMPLITUDE_SECRET_KEY"))
TINIFY_API_KEY = str(config("TINIFY_API_KEY"))
BRANCH_KEY = str(config("BRANCH_KEY"))
GEMINI_API_KEY = str(config("GEMINI_API_KEY"))

# Configure custom exception reporter filter to hide password-related variables
DEFAULT_EXCEPTION_REPORTER_FILTER = (
    "pico_backend.exception_reporter.CustomExceptionReporterFilter"
)

ADMINS = []

APPEND_SLASH = False

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "api",
    "chat",
    "commands",
    "core",
    "notifications",
    "currency",
    "essays",
    "quiz",
    "study_plans",
    "challenges",
    "bonus_events",
    "channels",
    "channels_redis",
    "storages",
    "ninja",
    "fcm_django",
    "sortedm2m",
    "import_export",
    "corsheaders",
]

# SITE_ID = 1

MIDDLEWARE = [
    "pico_backend.middlewares.health_check_middleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "pico_backend.middlewares.analytics_middleware",
    "pico_backend.middlewares.view_time_middleware",
]

ROOT_URLCONF = "pico_backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

ASGI_APPLICATION = "pico_backend.asgi.application"


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": DB_NAME,
        "USER": DB_USER,
        "PASSWORD": DB_PASSWORD,
        "HOST": DB_HOST,  # Set to empty string for localhost.
        "PORT": DB_PORT,  # Set to empty string to use the default port.
        "OPTIONS": {
            "pool": {
                "min_size": 2,
                "max_size": 45,
                "timeout": 10,
            }
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

AUTH_USER_MODEL = "api.User"


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "America/Sao_Paulo"

USE_I18N = True

USE_TZ = True

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "mail_admins": {
            "level": "ERROR",
            "class": "pico_backend.logging.ThrottledAdminEmailHandler",
            "include_html": True,
        },
        "mail_admins_warning": {
            "level": "WARNING",
            "class": "pico_backend.logging.ThrottledAdminEmailHandler",
            "include_html": True,
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console", "mail_admins"],
            "level": "INFO",
            "propagate": False,
        },
        "django.db.backends": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "daphne": {
            "handlers": ["console", "mail_admins"],
            "level": "INFO",
            "propagate": False,
        },
        "daphne.server": {
            "handlers": ["console", "mail_admins_warning"],
            "level": "INFO",
            "propagate": False,
        },
        "celery": {
            "handlers": [
                "console",
                "mail_admins",
            ],
            "level": "INFO",
            "propagate": False,
        },
        "chat": {
            "handlers": ["console", "mail_admins"],
            "level": "DEBUG",
            "propagate": False,
        },
        "api": {
            "handlers": ["console", "mail_admins"],
            "level": "DEBUG",
            "propagate": False,
        },
        "core": {
            "handlers": ["console", "mail_admins"],
            "level": "DEBUG",
            "propagate": False,
        },
        "commands": {
            "handlers": ["console", "mail_admins"],
            "level": "DEBUG",
            "propagate": False,
        },
        "notifications": {
            "handlers": ["console", "mail_admins"],
            "level": "DEBUG",
            "propagate": False,
        },
        "essays": {
            "handlers": ["console", "mail_admins"],
            "level": "DEBUG",
            "propagate": False,
        },
        "currency": {
            "handlers": ["console", "mail_admins"],
            "level": "DEBUG",
            "propagate": False,
        },
        "quiz": {
            "handlers": ["console", "mail_admins"],
            "level": "DEBUG",
            "propagate": False,
        },
        "study_plans": {
            "handlers": ["console", "mail_admins"],
            "level": "DEBUG",
            "propagate": False,
        },
        "challenges": {
            "handlers": ["console", "mail_admins"],
            "level": "DEBUG",
            "propagate": False,
        },
        "bonus_events": {
            "handlers": ["console", "mail_admins"],
            "level": "DEBUG",
            "propagate": False,
        },
        "shared": {
            "handlers": ["console", "mail_admins"],
            "level": "DEBUG",
            "propagate": False,
        },
        "pico_backend": {
            "handlers": ["console", "mail_admins"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"redis://{REDIS_HOST}:{REDIS_PORT}",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    },
}


CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [(REDIS_HOST, REDIS_PORT)],
        },
    },
}

CELERY_BROKER_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}"
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 26 * 60 * 60}
CELERY_RESULT_BACKEND = f"redis://{REDIS_HOST}:{REDIS_PORT}"  # needed for chords (not groups nor chains) and tasks with results: https://docs.celeryq.dev/en/latest/userguide/canvas.html#chord-important-notes
CELERY_TASK_IGNORE_RESULT = True
CELERY_WORKER_MAX_MEMORY_PER_CHILD = 500 * 1000  # 500MB, since its in kilobytes
CELERY_WORKER_MAX_TASKS_PER_CHILD = 20
CELERY_TASK_TIME_LIMIT = 600
CELERY_TASK_SOFT_TIME_LIMIT = 590


CHATFILE_VALID_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/avif",
    "image/bmp",
    "image/webp",
    "image/svg+xml",
    "image/x-icon",
    "image/heic",
    "image/heif",
    "video/quicktime",
    "video/x-msvideo",
    "video/mp4",
    "video/mpeg",
    "video/ogg",
    "video/webm",
    "video/3gpp",
    "video/3gpp2",
    "text/plain",
    "text/css",
    "text/csv",
    "text/calendar",
    "text/html",
    "audio/aac",
    "audio/mpeg",
    "audio/ogg",
    "audio/wav",
    "audio/midi",
    "audio/x-midi",
    "audio/x-m4a",
    "audio/x-mp3",
    "audio/x-wav",
    "audio/x-mpegurl",
    "audio/x-scpls",
    "audio/x-ms-wma",
    "audio/x-ms-wax",
    "audio/vnd.rn-realaudio",
    "audio/vnd.wave",
    "audio/webm",
    "audio/3gpp",
}

JWT_ACCESS_EXPIRATION_DELTA = timedelta(minutes=5)
JWT_REFRESH_EXPIRATION_DELTA = timedelta(days=180)

FIREBASE_APP = initialize_app(
    credential=credentials.Certificate(json.loads(FIREBASE_JSON_SERVICE_KEY))
)

FCM_DJANGO_SETTINGS = {
    # an instance of firebase_admin.App to be used as default for all fcm-django requests
    # default: None (the default Firebase app)
    "DEFAULT_FIREBASE_APP": FIREBASE_APP,
    # true if you want to have only one active device per registered user at a time
    # default: False
    "ONE_DEVICE_PER_USER": True,
    # devices to which notifications cannot be sent,
    # are deleted upon receiving error response from FCM
    # default: False
    "DELETE_INACTIVE_DEVICES": True,
}

OFFICIAL_CHATROOM_ICON_URL = ""

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = [
    "DELETE",
    "GET",
    "OPTIONS",
    "PATCH",
    "POST",
    "PUT",
]
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]
