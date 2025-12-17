"""Price fetching and arbitrage analysis utilities."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, Optional, Tuple, TypedDict

from ..config import EXCHANGE_FEES
from .exchange_manager import ExchangeManager

logger = logging.getLogger(__name__)


class PriceAnalyzer:
    """Collects prices and computes hedge opportunities across venues."""

    def __init__(self, exchange_manager: ExchangeManager) -> None:
        self.exchange_manager = exchange_manager
        self.exchanges = exchange_manager.exchanges
        self.symbols = exchange_manager.symbols

    @staticmethod
    def _get_taker_fee(exchange_name: str, market: str) -> float:
        """Safely returns the taker fee configured for an exchange."""
        return EXCHANGE_FEES.get(exchange_name, {}).get(market, {}).get("taker", 0.0)

    def fetch_funding_rate(self, exchange_name: str, symbol: str) -> Optional[float]:
        """Fetches the current funding rate for a perpetual contract.

        Args:
            exchange_name: Exchange key (e.g., bybit).
            symbol: Perpetual contract symbol.

        Returns:
            Funding rate as a decimal, or None on failure.
        """
        try:
            exchange = self.exchanges[exchange_name]["perp"]
            funding = exchange.fetch_funding_rate(symbol)
            return funding["fundingRate"] if funding else None
        except Exception as exc:  # broad catch is intentional for API variability
            logger.warning("⚠️ %s funding rate fetch failed: %s", exchange_name.upper(), exc)
            return None

    def fetch_all_prices(self) -> Dict[str, Dict[str, float]]:
        """Fetches spot/perp prices (and funding) from all exchanges in parallel."""
        prices: Dict[str, Dict[str, float]] = {}

        def fetch_exchange_prices(exchange_name: str) -> Tuple[str, Optional[Dict[str, float]]]:
            """Fetches prices for a single exchange."""
            try:
                result: Dict[str, float] = {}
                has_spot = "spot" in self.symbols[exchange_name]
                has_perp = "perp" in self.symbols[exchange_name]

                with ThreadPoolExecutor(max_workers=2) as executor:
                    futures = []
                    if has_spot:
                        futures.append(
                            (
                                "spot",
                                executor.submit(
                                    self.exchanges[exchange_name]["spot"].fetch_order_book,
                                    self.symbols[exchange_name]["spot"],
                                ),
                            )
                        )
                    if has_perp:
                        futures.append(
                            (
                                "perp",
                                executor.submit(
                                    self.exchanges[exchange_name]["perp"].fetch_order_book,
                                    self.symbols[exchange_name]["perp"],
                                ),
                            )
                        )

                    for market_type, future in futures:
                        try:
                            orderbook = future.result(timeout=5)
                        except Exception:
                            continue

                        if not orderbook or not orderbook.get("asks") or not orderbook.get("bids"):
                            continue

                        if market_type == "spot":
                            result["spot_bid"] = orderbook["bids"][0][0]
                            result["spot_ask"] = orderbook["asks"][0][0]
                            result["spot_bid_volume"] = orderbook["bids"][0][1]
                            result["spot_ask_volume"] = orderbook["asks"][0][1]
                        elif market_type == "perp":
                            result["perp_bid"] = orderbook["bids"][0][0]
                            result["perp_ask"] = orderbook["asks"][0][0]
                            result["perp_bid_volume"] = orderbook["bids"][0][1]
                            result["perp_ask_volume"] = orderbook["asks"][0][1]
                            perp_symbol = self.symbols[exchange_name].get("perp")
                            if perp_symbol:
                                funding_rate = self.fetch_funding_rate(exchange_name, perp_symbol)
                                if funding_rate is not None:
                                    result["funding_rate"] = funding_rate

                if result:
                    result["timestamp"] = datetime.now().timestamp()
                    return exchange_name, result

                return exchange_name, None
            except Exception as exc:
                logger.warning("⚠️ %s price fetch failed: %s", exchange_name.upper(), exc)
                return exchange_name, None

        with ThreadPoolExecutor(max_workers=len(self.symbols)) as executor:
            futures = [executor.submit(fetch_exchange_prices, ex) for ex in self.symbols.keys()]

            for future in as_completed(futures):
                exchange_name, price_data = future.result()
                if price_data:
                    prices[exchange_name] = price_data

        return prices

    def find_best_hedge_opportunity(
        self, spot_filter: Optional[str] = None, perp_filter: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str], Optional[float], Optional[float], Optional[float]]:
        """Fetches prices and returns the strongest hedge spread."""
        prices = self.fetch_all_prices()
        return self.find_best_hedge_opportunity_from_data(prices, spot_filter, perp_filter)

    def find_best_hedge_opportunity_from_data(
        self,
        prices: Dict[str, Dict[str, float]],
        spot_filter: Optional[str] = None,
        perp_filter: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[str], Optional[float], Optional[float], Optional[float]]:
        """Finds the optimal hedge opportunity using pre-fetched prices."""
        if not prices:
            return None, None, None, None, None

        class _BestCombo(TypedDict):
            spot_exchange: str
            perp_exchange: str
            spot_price: float
            perp_price: float
            net_spread: float

        best_combo: Optional[_BestCombo] = None

        for spot_exchange, spot_data in prices.items():
            if "spot_ask" not in spot_data:
                continue
            if spot_filter and spot_exchange != spot_filter:
                continue

            spot_price = spot_data["spot_ask"]
            if spot_price <= 0:
                continue

            spot_fee = self._get_taker_fee(spot_exchange, "spot")
            effective_spot = spot_price * (1 + spot_fee)

            for perp_exchange, perp_data in prices.items():
                if "perp_bid" not in perp_data:
                    continue
                if perp_filter and perp_exchange != perp_filter:
                    continue

                perp_price = perp_data["perp_bid"]
                perp_fee = self._get_taker_fee(perp_exchange, "futures")
                effective_perp = perp_price * (1 - perp_fee)

                if effective_spot <= 0:
                    continue

                net_spread = (effective_perp - effective_spot) / effective_spot
                if best_combo is None or net_spread > best_combo["net_spread"]:
                    best_combo = {
                        "spot_exchange": spot_exchange,
                        "perp_exchange": perp_exchange,
                        "spot_price": spot_price,
                        "perp_price": perp_price,
                        "net_spread": net_spread,
                    }

        if best_combo:
            return (
                best_combo["spot_exchange"],
                best_combo["perp_exchange"],
                best_combo["spot_price"],
                best_combo["perp_price"],
                best_combo["net_spread"],
            )

        return None, None, None, None, None

    def calculate_exit_metrics(
        self,
        prices: Dict[str, Dict[str, float]],
        spot_exchange: str,
        perp_exchange: str,
    ) -> Optional[Dict[str, float]]:
        """Computes effective exit prices including taker fees."""
        spot_data = prices.get(spot_exchange)
        perp_data = prices.get(perp_exchange)
        if not spot_data or not perp_data:
            return None
        if "spot_bid" not in spot_data or "perp_ask" not in perp_data:
            return None

        spot_fee = self._get_taker_fee(spot_exchange, "spot")
        perp_fee = self._get_taker_fee(perp_exchange, "futures")

        spot_exit = spot_data["spot_bid"] * (1 - spot_fee)
        perp_exit = perp_data["perp_ask"] * (1 + perp_fee)
        if spot_exit <= 0 or perp_exit <= 0:
            return None

        return {
            "spot_exit": spot_exit,
            "perp_exit": perp_exit,
            "spot_fee": spot_fee,
            "perp_fee": perp_fee,
        }
