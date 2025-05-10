import logging


class SuppressSensitiveWebSocketLogs(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = str(record.getMessage())
        # Customize pattern to your needs
        if "token=" in msg:
            return False  # suppress
        return True  # allow everything else


def add_log_filters():
    logger = logging.getLogger("uvicorn.error")
    for handler in logger.handlers:
        handler.addFilter(SuppressSensitiveWebSocketLogs())
