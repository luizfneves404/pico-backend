import logging
from typing import Any

from app.config import Environment, settings


class SuppressSensitiveWebSocketLogs(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = str(record.getMessage())
        # Customize pattern to your needs
        if "token=" in msg:
            return False  # suppress
        return True  # allow everything else


def get_logging_config() -> dict[str, Any]:
    base_format = "%(asctime)s [%(levelname)s] %(name)s | %(message)s"
    log_dir = settings.app_root.parent
    config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {"format": base_format},
        },
        "filters": {
            "suppress_sensitive_ws": {
                "()": "app.logging_config.SuppressSensitiveWebSocketLogs"
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "level": "INFO",
                "stream": "ext://sys.stdout",
            },
            "admin_email": {
                "class": "app.mail.AdminEmailHandler",
                "level": "ERROR",
                "formatter": "default",
            },
        },
        "root": {"level": "WARNING", "handlers": ["console", "admin_email"]},
        "loggers": {
            "app": {"level": "DEBUG", "propagate": True},
            "alembic": {"level": "DEBUG", "propagate": True},
            "sqlalchemy.engine": {
                "level": "DEBUG"
                if settings.environment != Environment.PROD
                else "WARNING",
                "propagate": True,
            },
            "botocore": {"level": "INFO", "propagate": True},
            "google": {"level": "INFO", "propagate": True},
            "urllib3": {"level": "INFO", "propagate": True},
            "httpcore": {"level": "INFO", "propagate": True},
            "openai": {"level": "INFO", "propagate": True},
            "python_multipart": {"level": "INFO", "propagate": True},
            "factory": {"level": "INFO", "propagate": True},
            "uvicorn": {"level": "INFO", "propagate": True},
            "uvicorn.access": {"level": "WARNING", "propagate": False},
            "uvicorn.error": {
                "level": "INFO",
                "propagate": True,
                "filters": ["suppress_sensitive_ws"],
            },
            "arq": {"level": "DEBUG", "propagate": True},
            "faker": {"level": "INFO", "propagate": True},
        },
    }

    if settings.environment == Environment.TEST:
        config["handlers"]["file"] = {
            "class": "logging.FileHandler",
            "formatter": "default",
            "level": "DEBUG",
            "filename": log_dir / "test.log",
            "mode": "w",
        }
        config["root"]["handlers"].append("file")
    elif settings.environment == Environment.DEV:
        config["handlers"]["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "default",
            "level": "DEBUG",
            "filename": log_dir / "dev.log",
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "mode": "a",
        }
        config["root"]["handlers"].append("file")

    return config
