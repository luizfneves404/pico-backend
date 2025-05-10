from pathlib import Path

from app.config import settings

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = settings.secret_key

# Configure custom exception reporter filter to hide password-related variables
DEFAULT_EXCEPTION_REPORTER_FILTER = (
    "pico_backend.exception_reporter.CustomExceptionReporterFilter"
)

ADMINS = list(zip(settings.admin_names, settings.admin_emails))

APPEND_SLASH = False

INSTALLED_APPS = [
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
        "NAME": settings.django_database_url.split("/")[-1],
        "USER": settings.django_database_url.split("://")[1].split(":")[0],
        "PASSWORD": settings.django_database_url.split(":")[2].split("@")[0],
        "HOST": settings.django_database_url.split("@")[1].split(":")[0],
        "PORT": settings.django_database_url.split(":")[-1].split("/")[0],
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

TIME_ZONE = settings.local_timezone

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
        "LOCATION": settings.redis_url,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    },
}


CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [
                (
                    settings.redis_url.split("://")[1].split(":")[0],
                    settings.redis_url.split(":")[-1].split("/")[0],
                )
            ],
        },
    },
}

CELERY_BROKER_URL = settings.redis_url
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 26 * 60 * 60}
CELERY_RESULT_BACKEND = settings.redis_url  # needed for chords (not groups nor chains) and tasks with results: https://docs.celeryq.dev/en/latest/userguide/canvas.html#chord-important-notes
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

FCM_DJANGO_SETTINGS = {
    # true if you want to have only one active device per registered user at a time
    # default: False
    "ONE_DEVICE_PER_USER": True,
    # devices to which notifications cannot be sent,
    # are deleted upon receiving error response from FCM
    # default: False
    "DELETE_INACTIVE_DEVICES": True,
}

OFFICIAL_CHATROOM_ICON_URL = (
    "https://pico-backend-needed-images.s3.sa-east-1.amazonaws.com/PicoLogo.png"
)

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
    "pico-api-key",
]
