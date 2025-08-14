import json

from firebase_admin import credentials, initialize_app

from app.config import settings


def init_firebase():
    initialize_app(
        credential=credentials.Certificate(
            json.loads(settings.firebase_service_key.model_dump_json())
        )
    )
