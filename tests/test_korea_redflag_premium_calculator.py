from __future__ import annotations

import pytest


class _DummyKoreanExchange:
    def __init__(self, ask_krw: float, usdt_krw: float) -> None:
        self.ask_krw = ask_krw
        self.usdt_krw = usdt_krw

    def get_ticker(self, symbol: str):
        if symbol == "USDT/KRW":
            return {"last": self.usdt_krw}
        return {"last": self.ask_krw, "ask": self.ask_krw}


class _DummyFuturesExchange:
    def __init__(self, bid_usdt: float) -> None:
        self.bid_usdt = bid_usdt

    def get_ticker(self, symbol: str):
        return {"last": self.bid_usdt, "bid": self.bid_usdt}


def test_redflag_premium_calculation() -> None:
    from overseas_exchange_hedge.korea.redflag.core.premium_calculator import PremiumCalculator

    korean = _DummyKoreanExchange(ask_krw=130000.0, usdt_krw=1300.0)
    futures = _DummyFuturesExchange(bid_usdt=100.0)
    calc = PremiumCalculator(korean, futures)

    premium = calc.calculate("BTC")
    assert premium is not None
    assert premium == pytest.approx(((130000.0 / 1300.0) / 100.0 - 1) * 100)
