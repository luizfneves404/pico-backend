import json

from firebase_admin import credentials, initialize_app

from app.config import settings
from app.fcm.fcm_service import logger


def init_firebase():
    try:
        initialize_app(
            credential=credentials.Certificate(
                json.loads(settings.firebase_service_key.model_dump_json())
            )
        )
    except ValueError:
        logger.debug("Firebase already initialized")
    else:
        logger.debug("Firebase initialized")
