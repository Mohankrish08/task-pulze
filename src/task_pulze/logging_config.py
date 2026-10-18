"""Logging setup.

Logs always go to stderr: with the stdio transport, stdout carries the MCP
protocol stream and any stray output there corrupts it.
"""

import logging
import sys

from task_pulze.config import LogLevel

_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging(level: LogLevel) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_FORMAT))

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)

    # httpx logs every request URL at INFO; keep it quiet unless debugging.
    logging.getLogger("httpx").setLevel(logging.DEBUG if level == "DEBUG" else logging.WARNING)
