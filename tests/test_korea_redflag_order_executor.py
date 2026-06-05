"""Tests for redflag OrderExecutor hedge sizing/execution fixes.

These pin the corrected behaviour for: Gate.io integer-contract rounding,
spot/futures leg matching, passing the validated KRW amount through (no racy
ticker refetch), and fail-closed balance checks.
"""

from __future__ import annotations

import unittest

from overseas_exchange_hedge.korea.redflag.core.order_executor import OrderExecutor


class _Korean:
    exchange_id = "upbit"

    def __init__(self) -> None:
        self.orders: list[tuple] = []

    def get_ticker(self, symbol: str):
        if symbol == "USDT/KRW":
            return {"last": 1400.0}
        return {"last": 100_000.0, "ask": 100_000.0, "bid": 99_900.0}

    def get_balance(self, currency: str):
        return {"free": 10_000_000.0, "used": 0.0, "total": 10_000_000.0}

    def create_market_order(self, symbol, side, amount, params=None):
        self.orders.append((symbol, side, amount, params))
        return {"id": "k1", "filled": amount, "status": "closed"}


class _GateFutures:
    exchange_id = "gateio"

    def __init__(self, contract_size: float = 0.01) -> None:
        self.contract_size = contract_size
        self.orders: list[tuple] = []

    def get_ticker(self, symbol: str):
        return {"last": 70.0, "bid": 70.0, "ask": 70.1}

    def get_balance(self, currency: str):
        return {"free": 10_000.0, "used": 0.0, "total": 10_000.0}

    def get_markets(self):
        return {"PEPE/USDT:USDT": {"contract_size": self.contract_size}}

    def set_leverage(self, symbol, leverage):
        return True

    def create_market_order(self, symbol, side, amount, params=None):
        self.orders.append((symbol, side, amount, params))
        return {"id": "f1", "filled": amount, "status": "closed"}

    def get_positions(self):
        return []


class TestFuturesQuantity(unittest.TestCase):
    def test_gateio_contracts_are_rounded_to_integer(self) -> None:
        ex = OrderExecutor(_Korean(), _GateFutures(contract_size=0.01))
        # 0.047 / 0.01 = 4.7 -> rounds to 5 contracts (truncating gave 4 = under-hedge)
        self.assertEqual(ex._calculate_futures_quantity("PEPE", 0.047), 5.0)

    def test_spot_quantity_matches_contract_grid(self) -> None:
        ex = OrderExecutor(_Korean(), _GateFutures(contract_size=0.01))
        # 5 contracts * 0.01 = 0.05 coins -> spot leg must hold exactly this
        self.assertAlmostEqual(ex._match_spot_to_futures("PEPE", 0.047, 5.0), 0.05)

    def test_non_gateio_quantity_unchanged(self) -> None:
        class _Bybit:
            exchange_id = "bybit"

        ex = OrderExecutor(_Korean(), _Bybit())
        self.assertEqual(ex._match_spot_to_futures("BTC", 0.123, 0.123), 0.123)


class TestBalancesFailClosed(unittest.TestCase):
    def test_balance_error_blocks_order(self) -> None:
        class _Boom(_Korean):
            def get_balance(self, currency):
                raise RuntimeError("api down")

        ex = OrderExecutor(_Boom(), _GateFutures())
        # Must fail closed (False), never proceed to place orders with unknown funds.
        self.assertFalse(ex._check_balances(1_000.0, 100.0))


class TestExecuteHedgePassesValidatedKrw(unittest.TestCase):
    def test_korean_buy_uses_passed_krw_amount(self) -> None:
        korean = _Korean()
        futures = _GateFutures(contract_size=0.01)
        ex = OrderExecutor(korean, futures)

        ok = ex.execute_hedge_position("PEPE", amount_usd=100.0)
        self.assertTrue(ok)

        # Korean leg: a market buy with a positive KRW *amount* (not a recomputed None).
        self.assertEqual(len(korean.orders), 1)
        _sym, side, amount, _params = korean.orders[0]
        self.assertEqual(side, "buy")
        self.assertGreater(amount, 0)

        # Futures leg: a short with integer contracts, flagged from the executor.
        self.assertEqual(len(futures.orders), 1)
        _fsym, fside, fcontracts, fparams = futures.orders[0]
        self.assertEqual(fside, "sell")
        self.assertEqual(fcontracts, round(fcontracts))
        self.assertTrue(fparams and fparams.get("from_order_executor"))


if __name__ == "__main__":
    unittest.main()
