"""Logging configuration for ani-tupi using loguru.

Provides centralized logging setup with file rotation (max 50MB per file).
Supports JSON debug logging with automatic sensitive data masking.
Use get_logger() to get a logger instance for any module.
"""

import json
import re
import sys

from loguru import logger as _base_logger

from models.config import get_data_path

# Store configuration state to prevent re-initialization
_initialized = False
_debug_mode = False


# Sensitive data patterns for masking
_SENSITIVE_PATTERNS = [
    # API tokens and keys
    (r'["\']?(?:sk|pk)-[a-zA-Z0-9]{20,}["\']?', "[MASKED_API_KEY]"),
    (r'(?:api[_-]?)?key["\']?\s*[:=]\s*["\']?[a-zA-Z0-9\-_]{16,}["\']?', "key=[MASKED_API_KEY]"),
    (r'token["\']?\s*[:=]\s*["\']?[a-zA-Z0-9._\-]{20,}["\']?', "token=[MASKED_TOKEN]"),
    # Bearer tokens
    (r"Bearer\s+[a-zA-Z0-9\-._~\+/]+=*", "Bearer [MASKED_TOKEN]"),
    # Passwords and pwd fields
    (r'password["\']?\s*[:=]\s*["\']?[^"\'\s,}]+["\']?', "password=[MASKED_PASSWORD]"),
    (r'pwd["\']?\s*[:=]\s*["\']?[^"\'\s,}]+["\']?', "pwd=[MASKED_PASSWORD]"),
    (r'passwd["\']?\s*[:=]\s*["\']?[^"\'\s,}]+["\']?', "passwd=[MASKED_PASSWORD]"),
    # Authorization headers
    (r'Authorization["\']?\s*:\s*["\']?[^"\'\s,}]+["\']?', "Authorization: [MASKED_TOKEN]"),
    (r'X-API-Key["\']?\s*:\s*["\']?[^"\'\s,}]+["\']?', "X-API-Key: [MASKED_KEY]"),
    (r'X-Auth-Token["\']?\s*:\s*["\']?[^"\'\s,}]+["\']?', "X-Auth-Token: [MASKED_TOKEN]"),
    # Cookie values
    (
        r'(sessionid|session_id|token|auth_token)["\']?\s*[:=]\s*["\']?[^"\'\s,}]+["\']?',
        r"\1=[MASKED_COOKIE]",
    ),
    # Email addresses in sensitive contexts (in API responses/requests)
    (r'(?:user_email|email)["\']?\s*:\s*["\']([^"\']+)["\']', r'email: "[MASKED_EMAIL]"'),
    # Phone numbers
    (r'(?:phone|mobile)["\']?\s*:\s*["\']?(\+?[0-9\s\-()]{10,})["\']?', r"phone: [MASKED_PHONE]"),
]


def mask_sensitive_data(message: str) -> str:
    """Redact sensitive data from a message string.

    Masks API tokens, passwords, auth headers, cookies, and other credentials.

    Args:
        message: The message string to mask

    Returns:
        Message with sensitive data redacted
    """
    if not isinstance(message, str):
        return message

    masked = message
    for pattern, replacement in _SENSITIVE_PATTERNS:
        masked = re.sub(pattern, replacement, masked, flags=re.IGNORECASE)

    return masked


class SensitiveDataFilter:
    """Loguru filter that masks sensitive data in log records."""

    def __call__(self, record):
        """Apply masking to the log record message."""
        record["message"] = mask_sensitive_data(record["message"])
        return True


def _json_formatter(record):
    """Format a log record as a JSON line.

    Loguru treats a callable format's return value as a *format template* and
    runs ``str.format_map`` on it. Returning raw JSON would make loguru parse
    the ``{...}`` braces as format fields (KeyError). So we stash the serialized
    JSON in ``record["extra"]`` and return a template that only references it.

    Args:
        record: Loguru record dictionary

    Returns:
        A format template string referencing the serialized JSON
    """
    log_data = {
        "timestamp": record["time"].isoformat(),
        "level": record["level"].name,
        "logger": record["name"],
        "function": record["function"],
        "line": record["line"],
        "message": record["message"],
        "process_id": record["process"].id,
        "thread_id": record["thread"].id,
    }

    # Add exception info if present
    if record["exception"]:
        exc_type, exc_value, exc_traceback = record["exception"]
        log_data["exception"] = {
            "type": exc_type.__name__ if exc_type else None,
            "value": str(exc_value) if exc_value else None,
            "traceback": str(exc_traceback) if exc_traceback else None,
        }

    record["extra"]["serialized"] = json.dumps(log_data)
    return "{extra[serialized]}\n"


def configure_logging(debug: bool = False) -> None:
    """Configure loguru for the entire application.

    Args:
        debug: If True, enable DEBUG-level logging to both console and debug.log (JSON format)
    """
    global _initialized, _debug_mode

    # Allow reconfiguration if debug mode changes
    if _initialized and _debug_mode == debug:
        return

    _debug_mode = debug
    log_dir = get_data_path()
    log_dir.mkdir(parents=True, exist_ok=True)

    # Remove default handler (clear previous configuration)
    _base_logger.remove()

    # Console handlers
    if debug:
        # Debug mode: show all levels with detailed format
        _base_logger.add(
            sys.stderr,
            format="<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
            level="DEBUG",
            filter=SensitiveDataFilter(),
        )
    else:
        # User-friendly: show INFO+ with simple format
        _base_logger.add(
            sys.stderr,
            format="<level>{level: <8}</level> {message}",
            level="INFO",
            filter=SensitiveDataFilter(),
        )

    # Regular file handler with rotation (50MB per file, keep last 10 files)
    log_file = log_dir / "ani-tupi.log"
    _base_logger.add(
        log_file,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="50 MB",  # Rotate when file reaches 50MB
        retention=10,  # Keep last 10 rotated files
        compression="zip",  # Compress rotated files
        filter=SensitiveDataFilter(),
    )

    # JSON debug log handler (only when debug mode is enabled)
    if debug:
        debug_log_file = log_dir / "debug.log"

        _base_logger.add(
            debug_log_file,
            format=_json_formatter,
            level="DEBUG",
            rotation="50 MB",
            retention=10,
            compression="zip",
            filter=SensitiveDataFilter(),
        )

    _initialized = True


def get_logger(name: str):
    """Get a configured logger instance for a module.

    Automatically configures logging if not already done.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured loguru logger instance
    """
    # Ensure logging is configured
    if not _initialized:
        configure_logging()

    # Bind the module name to the logger
    return _base_logger.bind(name=name)
