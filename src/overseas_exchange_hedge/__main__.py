"""Module entrypoint: `python -m overseas_exchange_hedge`."""

from __future__ import annotations

import sys

from .cli import main
from .common.logging_utils import setup_logging

if __name__ == "__main__":
    setup_logging()
    main(sys.argv[1:])
