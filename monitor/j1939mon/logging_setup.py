"""Standard logging configuration.

Console plus optional file output with a consistent format. Applied to
the root logger so that all modules report through the same handlers.
"""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

LOG_FORMAT = "%(asctime)s [%(levelname)-7s] %(name)s :: %(message)s"
DATE_FORMAT = "%H:%M:%S"


def configure_logging(level: str = "INFO", log_file: str | None = None) -> None:
    """Configure the root logger."""
    root = logging.getLogger()
    root.setLevel(level)

    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            path,
            maxBytes=2_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    logging.getLogger("can").setLevel(logging.WARNING)
