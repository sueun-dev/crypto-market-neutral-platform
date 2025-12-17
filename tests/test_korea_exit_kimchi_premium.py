from __future__ import annotations


def test_get_best_opportunity_filters_and_sorts() -> None:
    from overseas_exchange_hedge.korea.exit.kimchi_premium import KimchiPremiumCalculator

    calc = KimchiPremiumCalculator(exchange_manager=None, korean_manager=None)
    results = [
        {"should_sell": False, "premium": 10.0},
        {"should_sell": True, "premium": 3.0},
        {"should_sell": True, "premium": 5.0},
    ]

    best = calc.get_best_opportunity(results)
    assert best is not None
    assert best["premium"] == 5.0
