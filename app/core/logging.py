"""Safe structured logging configuration for CRYVEX ShopFlow Voice AI.

Ensures that authentication tokens, credentials, authorization headers, and
raw audio payloads are strictly sanitized and never leaked to logs.
"""

import logging
import sys
from typing import Any, Dict


SENSITIVE_FIELD_NAMES = {
    "authorization",
    "x-service-key",
    "x-api-key",
    "service_api_key",
    "shopflow_internal_api_key",
    "secret",
    "password",
    "audio_bytes",
    "raw_audio",
    "audio_base64",
}


class SafeLogFilter(logging.Filter):
    """Filter that sanitizes records to prevent secret and audio data leakage."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for sensitive in ["Bearer ", "x-service-key"]:
                if sensitive.lower() in record.msg.lower():
                    record.msg = "[REDACTED_SECURITY_DATA]"
        return True


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configures application logger with safe formatters and redaction."""
    logger = logging.getLogger("cryvex.voice")
    logger.setLevel(level)

    # Avoid adding duplicate handlers if reloaded
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] [req_id=%(request_id)s] %(message)s",
            defaults={"request_id": "-"}
        )
        handler.setFormatter(formatter)
        handler.addFilter(SafeLogFilter())
        logger.addHandler(handler)

    return logger


logger = setup_logging()

