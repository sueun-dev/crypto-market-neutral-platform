from __future__ import annotations


def test_format_percentage() -> None:
    from overseas_exchange_hedge.common.utils import format_percentage

    assert format_percentage(0.01234, decimals=2) == "1.23%"


def test_round_to_precision_default() -> None:
    from overseas_exchange_hedge.common.utils import round_to_precision

    assert round_to_precision(1.234567891) == 1.23456789


def test_round_to_precision_market_precision_int() -> None:
    from overseas_exchange_hedge.common.utils import round_to_precision

    market = {"precision": {"amount": 3}}
    assert round_to_precision(1.23456, market) == 1.235


def test_round_to_precision_market_precision_step() -> None:
    from overseas_exchange_hedge.common.utils import round_to_precision

    market = {"precision": {"amount": 0.001}}
    assert round_to_precision(1.23456, market) == 1.235


def test_round_to_precision_respects_min_amount() -> None:
    from overseas_exchange_hedge.common.utils import round_to_precision

    market = {"precision": {"amount": 4}, "limits": {"amount": {"min": 0.01}}}
    assert round_to_precision(0.0001, market) == 0.01


def test_validate_api_keys() -> None:
    from overseas_exchange_hedge.common.utils import validate_api_keys

    cfg = {
        "gateio": {"apiKey": "k", "secret": "s"},
        "bybit": {"apiKey": "", "secret": ""},
        "okx": {"apiKey": "k", "secret": "s", "password": ""},
    }
    status = validate_api_keys(cfg)
    assert status["gateio"] is True
    assert status["bybit"] is False
    assert status["okx"] is False
