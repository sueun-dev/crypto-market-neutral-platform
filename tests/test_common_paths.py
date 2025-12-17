from __future__ import annotations

from pathlib import Path


def test_runtime_dirs_created(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OEH_RUNTIME_DIR", str(tmp_path / "runtime"))

    from overseas_exchange_hedge.common import paths

    paths.ensure_runtime_dirs()

    assert (tmp_path / "runtime" / "cache").is_dir()
    assert (tmp_path / "runtime" / "state").is_dir()
    assert (tmp_path / "runtime" / "logs").is_dir()


def test_state_file_migrates_legacy(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OEH_RUNTIME_DIR", str(tmp_path / "runtime"))

    legacy = tmp_path / "positions.json"
    legacy.write_text('{"ok": true}', encoding="utf-8")

    from overseas_exchange_hedge.common.paths import state_file

    target = state_file("positions.json", legacy_filename=str(legacy))
    assert target.read_text(encoding="utf-8") == '{"ok": true}'
    assert target.parent == tmp_path / "runtime" / "state"


def test_cache_file_returns_path(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OEH_RUNTIME_DIR", str(tmp_path / "runtime"))

    from overseas_exchange_hedge.common.paths import cache_file

    path = cache_file("bybit_status.json")
    assert isinstance(path, Path)
    assert path.parent == tmp_path / "runtime" / "cache"
