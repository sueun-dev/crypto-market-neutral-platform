from __future__ import annotations


def test_find_best_hedge_opportunity_from_data_selects_best() -> None:
    from overseas_exchange_hedge.overseas.exchange_manager import ExchangeManager
    from overseas_exchange_hedge.overseas.price_analyzer import PriceAnalyzer

    analyzer = PriceAnalyzer(ExchangeManager())

    prices = {
        "gateio": {"spot_ask": 100.0, "perp_bid": 101.0},
        "bybit": {"spot_ask": 100.5, "perp_bid": 101.2},
    }

    spot_ex, perp_ex, spot_price, perp_price, net_spread = analyzer.find_best_hedge_opportunity_from_data(prices)

    assert spot_ex in {"gateio", "bybit"}
    assert perp_ex in {"gateio", "bybit"}
    assert spot_price is not None and spot_price > 0
    assert perp_price is not None and perp_price > 0
    assert net_spread is not None


def test_find_best_hedge_opportunity_from_data_respects_filters() -> None:
    from overseas_exchange_hedge.overseas.exchange_manager import ExchangeManager
    from overseas_exchange_hedge.overseas.price_analyzer import PriceAnalyzer

    analyzer = PriceAnalyzer(ExchangeManager())

    prices = {
        "gateio": {"spot_ask": 100.0, "perp_bid": 101.0},
        "bybit": {"spot_ask": 99.0, "perp_bid": 102.0},
    }

    spot_ex, perp_ex, *_ = analyzer.find_best_hedge_opportunity_from_data(
        prices, spot_filter="gateio", perp_filter="bybit"
    )
    assert spot_ex == "gateio"
    assert perp_ex == "bybit"


def test_calculate_exit_metrics() -> None:
    from overseas_exchange_hedge.overseas.exchange_manager import ExchangeManager
    from overseas_exchange_hedge.overseas.price_analyzer import PriceAnalyzer

    analyzer = PriceAnalyzer(ExchangeManager())

    prices = {
        "gateio": {"spot_bid": 99.0},
        "bybit": {"perp_ask": 100.0},
    }

    metrics = analyzer.calculate_exit_metrics(prices, spot_exchange="gateio", perp_exchange="bybit")
    assert metrics is not None
    assert metrics["spot_exit"] > 0
    assert metrics["perp_exit"] > 0
