"""Sensitive Data Logging Filter and Log Sanitizer.

Prevents credentials, JWT tokens, PII, and authorization headers
from leaking into application logs, console outputs, or log aggregators.
"""

import logging
import re
from typing import Any

from src.api.middlewares.request_id import request_id_ctx_var

# Regex patterns matching sensitive fields in key-value pairs or JSON strings
SENSITIVE_PATTERNS = [
    # Authorization / Bearer tokens
    (re.compile(r"(?i)(bearer\s+)[a-zA-Z0-9_\-\.]+"), r"\1[REDACTED_TOKEN]"),
    # JWT tokens in raw strings
    (re.compile(r"\beyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\b"), "[REDACTED_JWT]"),
    # Password / secret in JSON or query-like strings
    (
        re.compile(
            r'(?i)("?(?:password|token|secret|api_key|access_token)"?\s*[:=]\s*"?)[^",\s&\}]+("?)'
        ),
        r"\1[REDACTED]\2",
    ),
    # DNI / NIE / Passport simple heuristics (Spanish worker context)
    (re.compile(r"\b\d{8}[A-Za-z]\b"), "[REDACTED_DNI]"),
]

SECRET_KEYWORDS = ("pass", "token", "secret", "key", "auth")


class SensitiveDataFilter(logging.Filter):
    """Logging filter that scrubs sensitive credentials and attaches request_id."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Sanitize record message and inject request_id context."""
        # Inject request_id into record attributes
        req_id = request_id_ctx_var.get()
        record.request_id = req_id or "-"

        # Sanitize msg if it is a string
        if isinstance(record.msg, str):
            sanitized = record.msg
            for pattern, replacement in SENSITIVE_PATTERNS:
                sanitized = pattern.sub(replacement, sanitized)
            record.msg = sanitized

        # Sanitize arguments if provided
        if record.args:
            if isinstance(record.args, dict):
                clean_dict: dict[str, Any] = {}
                for k, v in record.args.items():
                    if any(secret_word in k.lower() for secret_word in SECRET_KEYWORDS):
                        clean_dict[k] = "[REDACTED]"
                    elif isinstance(v, str):
                        clean_val = v
                        for pattern, replacement in SENSITIVE_PATTERNS:
                            clean_val = pattern.sub(replacement, clean_val)
                        clean_dict[k] = clean_val
                    else:
                        clean_dict[k] = v
                record.args = clean_dict
            elif isinstance(record.args, tuple):
                clean_list: list[Any] = []
                for item in record.args:
                    if isinstance(item, str):
                        clean_val = item
                        for pattern, replacement in SENSITIVE_PATTERNS:
                            clean_val = pattern.sub(replacement, clean_val)
                        clean_list.append(clean_val)
                    else:
                        clean_list.append(item)
                record.args = tuple(clean_list)

        return True


def setup_secure_logging(level: str = "INFO") -> None:
    """Configure root logger with the sensitive data filter and structured format."""
    log_filter = SensitiveDataFilter()
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [req_id=%(request_id)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Avoid duplicate handlers if called multiple times
    if not root_logger.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.addFilter(log_filter)
        root_logger.addHandler(console_handler)
    else:
        for handler in root_logger.handlers:
            handler.setFormatter(formatter)
            handler.addFilter(log_filter)
