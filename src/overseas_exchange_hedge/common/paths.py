"""Project runtime paths (state/cache/logs)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

RUNTIME_DIR_ENV = "OEH_RUNTIME_DIR"


def runtime_dir() -> Path:
    """Returns the base runtime directory (default: ./runtime)."""
    return Path(os.getenv(RUNTIME_DIR_ENV, "runtime")).expanduser()


def cache_dir() -> Path:
    return runtime_dir() / "cache"


def state_dir() -> Path:
    return runtime_dir() / "state"


def logs_dir() -> Path:
    return runtime_dir() / "logs"


def ensure_runtime_dirs() -> None:
    cache_dir().mkdir(parents=True, exist_ok=True)
    state_dir().mkdir(parents=True, exist_ok=True)
    logs_dir().mkdir(parents=True, exist_ok=True)


def cache_file(filename: str, legacy_filename: Optional[str] = None) -> Path:
    ensure_runtime_dirs()
    path = cache_dir() / filename
    _migrate_legacy_file(path, legacy_filename)
    return path


def state_file(filename: str, legacy_filename: Optional[str] = None) -> Path:
    ensure_runtime_dirs()
    path = state_dir() / filename
    _migrate_legacy_file(path, legacy_filename)
    return path


def log_file(filename: str) -> Path:
    ensure_runtime_dirs()
    return logs_dir() / filename


def _migrate_legacy_file(target_path: Path, legacy_filename: Optional[str]) -> None:
    if not legacy_filename:
        return
    legacy_path = Path(legacy_filename)
    if target_path.exists() or not legacy_path.exists():
        return
    try:
        shutil.copy2(legacy_path, target_path)
    except Exception:
        return
