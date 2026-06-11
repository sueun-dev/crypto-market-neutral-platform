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


def test_market_buy_from_quote_consumes_depth() -> None:
    import pytest

    from overseas_exchange_hedge.overseas.price_analyzer import PriceAnalyzer

    fill = PriceAnalyzer.estimate_market_buy_from_quote(
        asks=[(100.0, 0.5), (101.0, 1.0)],
        quote_budget=100.0,
    )

    assert fill is not None
    assert fill.base_quantity == pytest.approx(0.99504950495)
    assert fill.average_price == pytest.approx(100.4975124378)
    assert fill.levels_used == 2


def test_build_executable_opportunity_uses_depth_and_fees() -> None:
    from overseas_exchange_hedge.overseas.exchange_manager import ExchangeManager
    from overseas_exchange_hedge.overseas.price_analyzer import PriceAnalyzer

    analyzer = PriceAnalyzer(ExchangeManager())
    prices = {
        "gateio": {
            "spot_asks": [(100.0, 0.5), (101.0, 1.0)],
            "spot_bids": [(99.8, 1.0)],
            "spot_ask": 100.0,
        },
        "bybit": {
            "perp_bids": [(101.5, 0.4), (101.2, 1.0)],
            "perp_asks": [(101.6, 1.0)],
            "perp_bid": 101.5,
            "funding_rate": 0.0,
        },
    }

    opportunity = analyzer.build_executable_hedge_opportunity(
        prices,
        spot_exchange="gateio",
        perp_exchange="bybit",
        entry_amount=100.0,
    )

    assert opportunity is not None
    assert opportunity.spot_levels_used == 2
    assert opportunity.perp_levels_used == 2
    assert opportunity.net_spread > 0.002
    assert opportunity.spot_price > 100.0
    assert opportunity.perp_price < 101.5


def test_build_executable_opportunity_rejects_when_depth_erases_edge() -> None:
    from overseas_exchange_hedge.overseas.exchange_manager import ExchangeManager
    from overseas_exchange_hedge.overseas.price_analyzer import PriceAnalyzer

    analyzer = PriceAnalyzer(ExchangeManager())
    prices = {
        "gateio": {
            "spot_asks": [(100.0, 0.05), (104.0, 2.0)],
            "spot_ask": 100.0,
        },
        "bybit": {
            "perp_bids": [(101.0, 2.0)],
            "perp_bid": 101.0,
            "funding_rate": 0.0,
        },
    }

    opportunity = analyzer.build_executable_hedge_opportunity(
        prices,
        spot_exchange="gateio",
        perp_exchange="bybit",
        entry_amount=100.0,
    )

    assert opportunity is not None
    assert opportunity.net_spread < 0.002


def test_build_executable_opportunity_rejects_negative_funding() -> None:
    from overseas_exchange_hedge.overseas.exchange_manager import ExchangeManager
    from overseas_exchange_hedge.overseas.price_analyzer import PriceAnalyzer

    analyzer = PriceAnalyzer(ExchangeManager())
    prices = {
        "gateio": {"spot_asks": [(100.0, 2.0)], "spot_ask": 100.0},
        "bybit": {"perp_bids": [(102.0, 2.0)], "perp_bid": 102.0, "funding_rate": -0.0001},
    }

    opportunity = analyzer.build_executable_hedge_opportunity(
        prices,
        spot_exchange="gateio",
        perp_exchange="bybit",
        entry_amount=100.0,
    )

    assert opportunity is None


def test_build_executable_opportunity_rejects_missing_funding_by_default() -> None:
    from overseas_exchange_hedge.overseas.exchange_manager import ExchangeManager
    from overseas_exchange_hedge.overseas.price_analyzer import PriceAnalyzer

    analyzer = PriceAnalyzer(ExchangeManager())
    prices = {
        "gateio": {"spot_asks": [(100.0, 2.0)], "spot_ask": 100.0},
        "bybit": {"perp_bids": [(102.0, 2.0)], "perp_bid": 102.0},
    }

    opportunity = analyzer.build_executable_hedge_opportunity(
        prices,
        spot_exchange="gateio",
        perp_exchange="bybit",
        entry_amount=100.0,
    )

    assert opportunity is None


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
