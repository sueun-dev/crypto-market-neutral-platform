from __future__ import annotations

import pytest


def test_coalesce() -> None:
    from overseas_exchange_hedge.overseas.trade_executor import _coalesce

    assert _coalesce(None, "1.5") == 1.5
    assert _coalesce(None, None, default=2.0) == 2.0


def test_extract_filled_and_cost_uses_fallback_price() -> None:
    from overseas_exchange_hedge.overseas.trade_executor import _extract_filled_and_cost

    filled, cost = _extract_filled_and_cost({"filled": 2.0}, fallback_price=100.0)
    assert filled == pytest.approx(2.0)
    assert cost == pytest.approx(200.0)


def test_extract_filled_and_cost_uses_trades_when_missing() -> None:
    from overseas_exchange_hedge.overseas.trade_executor import _extract_filled_and_cost

    order = {"filled": 0.0, "cost": 0.0, "trades": [{"amount": 1.0, "cost": 101.0}]}
    filled, cost = _extract_filled_and_cost(order, fallback_price=100.0)
    assert filled == pytest.approx(1.0)
    assert cost == pytest.approx(101.0)


def test_enforce_min_spot_respects_min_cost_and_min_qty() -> None:
    from overseas_exchange_hedge.overseas.trade_executor import _enforce_min_spot

    market = {"precision": {"amount": 6}, "limits": {"amount": {"min": 0.01}, "cost": {"min": 10.0}}}
    qty = _enforce_min_spot(market, ref_price=100.0, qty=0.001)
    assert qty >= 0.1  # min_cost / price
