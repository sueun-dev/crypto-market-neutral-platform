from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

_RUNTIME_DIR = tempfile.mkdtemp(prefix="oeh-runtime-")
os.environ.setdefault("OEH_RUNTIME_DIR", _RUNTIME_DIR)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = _PROJECT_ROOT / "src"
if _SRC_DIR.is_dir():
    sys.path.insert(0, str(_SRC_DIR))


@atexit.register
def _cleanup_runtime_dir() -> None:
    shutil.rmtree(_RUNTIME_DIR, ignore_errors=True)
