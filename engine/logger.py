"""
engine/logger.py
Public Conversation Analysis Engine — Centralized Logging Framework

Usage:
    from engine.logger import get_logger
    log = get_logger(__name__)
    log.info("Starting pipeline run")
    log.warning("Rate limit approaching")
    log.error("Connector failed: %s", exc)

Log levels: DEBUG < INFO < WARNING < ERROR < CRITICAL

Log output:
    - Console: colored, human-readable, INFO level and above
    - File:    engine/logs/pipeline_<timestamp>.log (DEBUG and above, plain text)

Each pipeline run creates one timestamped log file. The root logger is configured
once on first import; subsequent calls to get_logger() return child loggers that
inherit handlers from the root.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from datetime import datetime
from pathlib import Path

# ── constants ──────────────────────────────────────────────────────────────
LOG_DIR = Path(__file__).parent / "logs"
LOG_FORMAT_FILE = (
    "%(asctime)s | %(levelname)-8s | %(name)-40s | %(message)s"
)
LOG_FORMAT_CONSOLE = (
    "%(log_color)s%(asctime)s | %(levelname)-8s%(reset)s | %(name)s | %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Singleton flag: root logger is configured only once per process
_CONFIGURED = False
_RUN_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")


def _configure_root_logger(level: int = logging.DEBUG) -> None:
    """Configure the root 'engine' logger once per process."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("engine")
    root.setLevel(level)
    root.propagate = False  # do not bubble to the Python root logger

    # ── File handler ──────────────────────────────────────────────────────
    log_file = LOG_DIR / f"pipeline_{_RUN_TIMESTAMP}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT_FILE, datefmt=DATE_FORMAT))
    root.addHandler(file_handler)

    # ── Console handler (colored if colorlog is available) ────────────────
    try:
        import colorlog  # type: ignore[import]

        console_handler = colorlog.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(
            colorlog.ColoredFormatter(
                LOG_FORMAT_CONSOLE,
                datefmt=DATE_FORMAT,
                log_colors={
                    "DEBUG": "cyan",
                    "INFO": "green",
                    "WARNING": "yellow",
                    "ERROR": "red",
                    "CRITICAL": "bold_red",
                },
            )
        )
    except ImportError:
        # colorlog not installed — fall back to plain console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(
            logging.Formatter(LOG_FORMAT_FILE, datefmt=DATE_FORMAT)
        )

    root.addHandler(console_handler)
    _CONFIGURED = True

    root.debug("Logger initialized. Log file: %s", log_file)


def get_logger(name: str, level: int = logging.DEBUG) -> logging.Logger:
    """
    Return a named child logger under the 'engine' namespace.

    Args:
        name: Typically __name__ of the calling module.
              If the name doesn't start with 'engine', it is prefixed automatically.
        level: Minimum log level for this specific logger (default: DEBUG,
               i.e., inherit from root).

    Returns:
        logging.Logger configured and ready to use.
    """
    _configure_root_logger()

    # Ensure all loggers live under the 'engine' hierarchy
    if not name.startswith("engine"):
        name = f"engine.{name}"

    logger = logging.getLogger(name)
    logger.setLevel(level)
    return logger


def get_run_log_path() -> Path:
    """Return the absolute path to the current run's log file."""
    return LOG_DIR / f"pipeline_{_RUN_TIMESTAMP}.log"
