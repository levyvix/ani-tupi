"""Logging configuration for ani-tupi using loguru.

Provides centralized logging setup with file rotation (max 50MB per file).
Use get_logger() to get a logger instance for any module.
"""

import sys

from loguru import logger as _base_logger

from models.config import get_data_path

# Store configuration state to prevent re-initialization
_initialized = False


def configure_logging(debug: bool = False) -> None:
    """Configure loguru for the entire application.

    Args:
        debug: If True, set console logging to DEBUG level instead of WARNING
    """
    global _initialized

    if _initialized:
        return

    log_dir = get_data_path()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "ani-tupi.log"

    # Remove default handler
    _base_logger.remove()

    # Console handler (WARNING by default, DEBUG if debug=True)
    console_level = "DEBUG" if debug else "WARNING"
    _base_logger.add(
        sys.stderr,
        format="<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level=console_level,
    )

    # File handler with rotation (50MB per file, keep last 10 files)
    _base_logger.add(
        log_file,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="50 MB",  # Rotate when file reaches 50MB
        retention=10,  # Keep last 10 rotated files
        compression="zip",  # Compress rotated files
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
