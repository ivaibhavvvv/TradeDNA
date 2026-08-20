import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

SENSITIVE_KEYS = {
    "password",
    "jwt",
    "token",
    "access_token",
    "refresh_token",
    "pairing_token",
    "secret",
    "device_secret",
    "hmac_secret",
    "authorization",
    "cookie",
    "x-tradedna-signature",
    "db_password",
}


def redact_sensitive_data(obj: Any) -> Any:
    """Recursively redacts sensitive keys from log dictionaries."""
    if isinstance(obj, dict):
        redacted = {}
        for k, v in obj.items():
            if any(s in str(k).lower() for s in SENSITIVE_KEYS):
                redacted[k] = "[REDACTED]"
            elif isinstance(v, (dict, list)):
                redacted[k] = redact_sensitive_data(v)
            else:
                redacted[k] = v
        return redacted
    elif isinstance(obj, list):
        return [redact_sensitive_data(item) for item in obj]
    return obj


class JSONFormatter(logging.Formatter):
    """Structured JSON formatter for production-ready observability and auditability."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Context correlation fields
        for field in ("request_id", "tenant_id", "user_id", "route", "method", "status_code", "latency_ms", "error_category"):
            if hasattr(record, field):
                log_obj[field] = getattr(record, field)

        # Include exception traceback if present
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        # Ensure all data is sanitized
        sanitized_log = redact_sensitive_data(log_obj)
        return json.dumps(sanitized_log)


def setup_logging(log_level: str = "INFO") -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root_logger.addHandler(handler)


logger = logging.getLogger("tradedna")

