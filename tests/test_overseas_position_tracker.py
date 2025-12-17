from __future__ import annotations

from pathlib import Path

import pytest


def test_position_tracker_add_reduce_and_persist(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OEH_RUNTIME_DIR", str(tmp_path / "runtime"))

    from overseas_exchange_hedge.overseas.position_tracker import PositionTracker

    tracker = PositionTracker()
    assert tracker.positions["entries"] == []

    tracker.add_entry(
        coin="BTC",
        spot_price=100.0,
        quantity=2.0,
        spot_exchange="gateio",
        perp_exchange="bybit",
        perp_price=101.0,
        spread=0.01,
    )

    assert tracker.positions["current_coin"] == "BTC"
    assert tracker.positions["total_quantity"] == pytest.approx(2.0)
    assert tracker.positions["total_cost_usdt"] == pytest.approx(200.0)
    assert tracker.positions["average_price"] == pytest.approx(100.0)

    pairs = tracker.get_open_pairs()
    assert ("gateio", "bybit") in pairs
    assert pairs[("gateio", "bybit")]["quantity"] == pytest.approx(2.0)

    reduced = tracker.reduce_pair_position("gateio", "bybit", quantity=1.0)
    assert reduced == pytest.approx(1.0)
    assert tracker.positions["total_quantity"] == pytest.approx(1.0)

    state_path = Path(tmp_path / "runtime" / "state" / "positions.json")
    assert state_path.exists()

    # Reload from disk
    tracker2 = PositionTracker()
    assert tracker2.positions["total_quantity"] == pytest.approx(1.0)


def test_get_bithumb_targets(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OEH_RUNTIME_DIR", str(tmp_path / "runtime"))

    from overseas_exchange_hedge.overseas.position_tracker import PositionTracker

    tracker = PositionTracker()
    tracker.add_entry(
        coin="ETH",
        spot_price=2000.0,
        quantity=0.5,
        spot_exchange="bybit",
        perp_exchange="okx",
        perp_price=2010.0,
        spread=0.005,
    )

    targets = tracker.get_bithumb_targets(usdt_krw_rate=1300.0)
    assert targets is not None
    assert targets["total_quantity"] == pytest.approx(0.5)
    assert targets["average_price_usdt"] == pytest.approx(2000.0)
