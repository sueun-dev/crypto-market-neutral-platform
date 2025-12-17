#!/usr/bin/env bash

set -euo pipefail

if command -v uv >/dev/null 2>&1; then
  exec uv run hedge
fi

export PYTHONPATH="${PYTHONPATH:-}:src"

if [ -x ".venv/bin/python" ]; then
  exec .venv/bin/python -m overseas_exchange_hedge
fi

exec python3 -m overseas_exchange_hedge
