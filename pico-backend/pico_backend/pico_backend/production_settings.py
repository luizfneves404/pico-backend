from decouple import config

from pico_backend.base_settings import *

ADMIN_URL = config("ADMIN_URL", default="admin")
AWS_DEFAULT_STORAGE_BUCKET_NAME = config("AWS_DEFAULT_STORAGE_BUCKET_NAME")
AWS_STATICFILES_STORAGE_BUCKET_NAME = config("AWS_STATICFILES_STORAGE_BUCKET_NAME")
AWS_US_EAST_1_STORAGE_BUCKET_NAME = config("AWS_US_EAST_1_STORAGE_BUCKET_NAME")
AWS_S3_REGION_NAME = config("AWS_S3_REGION_NAME")
AWS_SES_REGION_NAME = config("AWS_SES_REGION_NAME")
AWS_SES_FROM_EMAIL = config("AWS_SES_FROM_EMAIL")
SERVER_EMAIL = AWS_SES_FROM_EMAIL
DEFAULT_FROM_EMAIL = AWS_SES_FROM_EMAIL


# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

DOCS_URL = "REDACTED"

OPENAPI_URL = "REDACTED"

OPENAPI_API_KEY = "REDACTED"

CELERY_TASK_ALWAYS_EAGER = False  # Need to specify, even though its the default, because this is checked in the code

USE_X_FORWARDED_HOST = True

ALLOWED_HOSTS = ["www.pico.fyi", "pico.fyi", "api.pico.fyi"]

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


STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": AWS_DEFAULT_STORAGE_BUCKET_NAME,
            "querystring_auth": True,
            "querystring_expire": 604800,
        },
    },
    "staticfiles": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": AWS_STATICFILES_STORAGE_BUCKET_NAME,
            "querystring_auth": False,
        },
    },
    "us_east_1": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": AWS_US_EAST_1_STORAGE_BUCKET_NAME,
            "querystring_auth": True,
            "querystring_expire": 604800,
        },
    },
}

EMAIL_BACKEND = "django_ses.SESBackend"
NINJA_NUM_PROXIES = 1
AMPLITUDE_TRACK_EVENTS = True
