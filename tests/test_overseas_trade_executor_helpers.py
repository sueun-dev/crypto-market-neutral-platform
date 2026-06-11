from __future__ import annotations

from typing import Any, cast

import pytest


class _FakeExchange:
    def __init__(self, orderbook=None, funding_rate=0.0):
        self.orderbook = orderbook or {"asks": [(100.0, 10.0)], "bids": [(100.0, 10.0)]}
        self.funding_rate = funding_rate
        self.created_orders = []

    def fetch_order_book(self, symbol, limit=None):
        return self.orderbook

    def fetch_funding_rate(self, symbol):
        return {"fundingRate": self.funding_rate}

    def create_order(self, *args, **kwargs):
        self.created_orders.append((args, kwargs))
        return {"id": "fake-order", "filled": kwargs.get("amount", 0.0), "cost": 0.0, "status": "closed"}

    def fetch_order(self, order_id, symbol):
        return {"id": order_id, "filled": 1.0, "cost": 100.0, "status": "closed"}


class _FakeExchangeManager:
    def __init__(self, spot_orderbook, perp_orderbook, perp_market=None):
        self.exchanges = {
            "gateio": {"spot": _FakeExchange(spot_orderbook), "perp": _FakeExchange()},
            "bybit": {"spot": _FakeExchange(), "perp": _FakeExchange(perp_orderbook)},
        }
        self.symbols = {
            "gateio": {"spot": "TEST/USDT", "spot_market": {"precision": {"amount": 6}}},
            "bybit": {"perp": "TEST/USDT:USDT", "perp_market": perp_market or {"precision": {"amount": 6}}},
        }

    def get_exchange(self, exchange_name):
        return self.exchanges.get(exchange_name)

    def get_symbols(self, exchange_name):
        return self.symbols.get(exchange_name)


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


def test_execute_hedge_skips_orders_when_pretrade_spread_below_threshold() -> None:
    from overseas_exchange_hedge.overseas.trade_executor import TradeExecutor

    manager = _FakeExchangeManager(
        spot_orderbook={"asks": [(100.0, 10.0)], "bids": [(99.9, 10.0)]},
        perp_orderbook={"asks": [(100.2, 10.0)], "bids": [(100.1, 10.0)]},
    )
    executor = TradeExecutor(cast(Any, manager))

    result = executor.execute_hedge(
        spot_exchange="gateio",
        perp_exchange="bybit",
        spot_price=100.0,
        perp_price=100.1,
        coin="TEST",
        entry_amount=100.0,
    )

    assert result is None
    assert manager.exchanges["gateio"]["spot"].created_orders == []
    assert manager.exchanges["bybit"]["perp"].created_orders == []


def test_execute_hedge_skips_when_perp_min_size_would_oversize() -> None:
    from overseas_exchange_hedge.overseas.trade_executor import TradeExecutor

    manager = _FakeExchangeManager(
        spot_orderbook={"asks": [(100.0, 10.0)], "bids": [(99.9, 10.0)]},
        perp_orderbook={"asks": [(102.1, 10.0)], "bids": [(102.0, 10.0)]},
        perp_market={"precision": {"amount": 6}, "limits": {"amount": {"min": 2.0}}},
    )
    executor = TradeExecutor(cast(Any, manager))

    result = executor.execute_hedge(
        spot_exchange="gateio",
        perp_exchange="bybit",
        spot_price=100.0,
        perp_price=102.0,
        coin="TEST",
        entry_amount=100.0,
    )

    assert result is None
    assert manager.exchanges["gateio"]["spot"].created_orders == []
    assert manager.exchanges["bybit"]["perp"].created_orders == []
