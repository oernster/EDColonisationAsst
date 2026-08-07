"""Logging configuration and utilities"""

import logging
import sys

from ..config import get_config


def setup_logging(level: str | None = None, format_str: str | None = None) -> None:
    """
    Setup logging configuration for the application

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_str: Log format string
    """
    config = get_config()

    log_level = level or config.logging.level
    log_format = format_str or config.logging.format

    # Convert string level to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Configure root logger
    logging.basicConfig(
        level=numeric_level,
        format=log_format,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Set level for third-party loggers to WARNING to reduce noise
    logging.getLogger("watchdog").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("fastapi").setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the specified name

    Args:
        name: Logger name (typically __name__ of the module)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)
