"""Shared logging configuration for CLI-style output.

We use logging instead of print so that messages can be routed/filtered while
preserving the existing interactive UX (stdout, message-only by default).
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional, Union


def setup_logging(level: Optional[Union[int, str]] = None) -> None:
    """Configures root logging once (idempotent).

    - Default level: INFO (or `OEH_LOG_LEVEL`).
    - Output stream: stdout (so capsys/out captures it like print()).
    - Format: message-only (no timestamps/prefixes).
    """
    root = logging.getLogger()

    if level is None:
        level = os.getenv("OEH_LOG_LEVEL", "INFO").upper()

    if isinstance(level, str):
        resolved_level = logging.getLevelName(level)
        if isinstance(resolved_level, int):
            level = resolved_level
        else:
            level = logging.INFO

    resolved = int(level)
    root.setLevel(resolved)

    for handler in root.handlers:
        if getattr(handler, "name", None) == "oeh-stdout" or getattr(handler, "_oeh_stdout", False):
            return

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setLevel(resolved)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.set_name("oeh-stdout")
    handler._oeh_stdout = True  # type: ignore[attr-defined]
    root.addHandler(handler)
