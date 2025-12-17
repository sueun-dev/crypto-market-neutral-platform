from __future__ import annotations

import pytest


def test_calculate_kimchi_premium_happy_path() -> None:
    from overseas_exchange_hedge.korea.exit.kimchi_premium import KimchiPremiumCalculator

    calc = KimchiPremiumCalculator(exchange_manager=None, korean_manager=None)
    calc.get_overseas_price = lambda coin, exchange: 100.0  # type: ignore[method-assign]
    calc.get_usdt_krw_price = lambda: 1300.0  # type: ignore[method-assign]
    calc.get_korean_bid_price = lambda coin, exchange: 135000.0  # type: ignore[method-assign]

    premium, details = calc.calculate_kimchi_premium("BTC", "bithumb", "gateio")
    assert premium is not None
    assert details["overseas_price_krw"] == pytest.approx(130000.0)
    assert premium == pytest.approx((135000.0 - 130000.0) / 130000.0 * 100)
