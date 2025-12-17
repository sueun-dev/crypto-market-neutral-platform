from __future__ import annotations


def test_extract_okx_base() -> None:
    from overseas_exchange_hedge.overseas.exchange_manager import ExchangeManager

    assert ExchangeManager._extract_okx_base("BTC") == "BTC"
    assert ExchangeManager._extract_okx_base("btc") == "BTC"
    assert ExchangeManager._extract_okx_base("USDC-ERC20") == "USDC"
    assert ExchangeManager._extract_okx_base("ETH-ARB") == "ETH"
