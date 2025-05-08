from pico_backend.base_settings import *

from app.config import S3Config, settings

ADMIN_URL = settings.admin_url
AWS_S3_REGION_NAME = settings.aws_s3_region_name
AWS_SES_REGION_NAME = settings.aws_ses_region_name
AWS_SES_FROM_EMAIL = settings.aws_ses_from_email
SERVER_EMAIL = AWS_SES_FROM_EMAIL
DEFAULT_FROM_EMAIL = AWS_SES_FROM_EMAIL


# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

CELERY_TASK_ALWAYS_EAGER = False  # Need to specify, even though its the default, because this is checked in the code

USE_X_FORWARDED_HOST = True

ALLOWED_HOSTS = settings.allowed_hosts

CORS_ALLOWED_ORIGINS = [
    "https://pico-web.vercel.app",
]

CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = [
    "https://www.pico.fyi",
    "https://pico.fyi",
    "https://api.pico.fyi",
]

if (
    isinstance(settings.storage, S3Config)
    and isinstance(settings.staticfiles_storage, S3Config)
    and isinstance(settings.us_east_1_storage, S3Config)
):
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "bucket_name": settings.storage.bucket_name,
                "querystring_auth": True,
                "querystring_expire": 604800,
            },
        },
        "staticfiles": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "bucket_name": settings.staticfiles_storage.bucket_name,
                "querystring_auth": False,
            },
        },
        "us_east_1": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "bucket_name": settings.us_east_1_storage.bucket_name,
                "querystring_auth": True,
                "querystring_expire": 604800,
            },
        },
    }
else:
    raise ValueError(f"Unsupported storage backend: {settings.storage}")

EMAIL_BACKEND = "django_ses.SESBackend"
NINJA_NUM_PROXIES = 1
