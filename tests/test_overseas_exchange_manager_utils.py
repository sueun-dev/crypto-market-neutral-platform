from __future__ import annotations


def test_resolve_symbol_prefers_loaded_symbols() -> None:
    from overseas_exchange_hedge.overseas.exchange_manager import ExchangeManager

    mgr = ExchangeManager()
    mgr.symbols = {"gateio": {"spot": "BTC/USDT", "perp": "BTC/USDT:USDT"}}

    assert mgr.resolve_symbol("gateio", "spot", "BTC") == "BTC/USDT"
    assert mgr.resolve_symbol("gateio", "perp", "BTC") == "BTC/USDT:USDT"


def test_resolve_symbol_falls_back_to_templates() -> None:
    from overseas_exchange_hedge.overseas.exchange_manager import ExchangeManager

    mgr = ExchangeManager()
    assert mgr.resolve_symbol("gateio", "spot", "ETH") == "ETH/USDT"
    assert mgr.resolve_symbol("gateio", "perp", "ETH") == "ETH/USDT:USDT"


def test_attach_credentials_injects_api_keys() -> None:
    from overseas_exchange_hedge.overseas.exchange_manager import ExchangeManager

    mgr = ExchangeManager()
    params = {"enableRateLimit": True}
    cfg = {"apiKey": "k", "secret": "s", "password": "p"}

    mgr._attach_credentials(params, cfg, password_key="password")
    assert params["apiKey"] == "k"
    assert params["secret"] == "s"
    assert params["password"] == "p"
