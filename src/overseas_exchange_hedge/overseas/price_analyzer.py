"""Price fetching and arbitrage analysis utilities."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional, Sequence, Tuple

from ..config import ENTRY_AMOUNT, EXCHANGE_FEES, MIN_FUNDING_RATE, ORDERBOOK_DEPTH_LIMIT, REQUIRE_FUNDING_RATE
from .exchange_manager import ExchangeManager

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MarketFillEstimate:
    """Expected market-order fill from current orderbook depth."""

    average_price: float
    base_quantity: float
    quote_quantity: float
    worst_price: float
    levels_used: int


@dataclass(frozen=True)
class HedgeOpportunity:
    """Executable contango opportunity after depth and fee simulation."""

    spot_exchange: str
    perp_exchange: str
    spot_price: float
    perp_price: float
    gross_spread: float
    net_spread: float
    quantity: float
    spot_quote: float
    perp_quote: float
    spot_fee: float
    perp_fee: float
    spot_top_ask: float
    perp_top_bid: float
    spot_levels_used: int
    perp_levels_used: int
    funding_rate: Optional[float] = None


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

    @staticmethod
    def _normalize_levels(levels: Any) -> list[tuple[float, float]]:
        """Returns clean (price, amount) levels from a ccxt orderbook side."""
        normalized: list[tuple[float, float]] = []
        if not isinstance(levels, list):
            return normalized
        for level in levels:
            if not isinstance(level, Sequence) or len(level) < 2:
                continue
            try:
                price = float(level[0])
                amount = float(level[1])
            except (TypeError, ValueError):
                continue
            if price > 0 and amount > 0:
                normalized.append((price, amount))
        return normalized

    @staticmethod
    def _levels_from_price_data(
        price_data: Dict[str, Any],
        levels_key: str,
        price_key: str,
        volume_key: str,
        entry_quote: float,
    ) -> list[tuple[float, float]]:
        """Returns stored depth, falling back to a single synthetic top level for old tests."""
        levels = PriceAnalyzer._normalize_levels(price_data.get(levels_key))
        if levels:
            return levels

        price = float(price_data.get(price_key) or 0.0)
        if price <= 0:
            return []

        if volume_key in price_data:
            volume = float(price_data.get(volume_key) or 0.0)
        else:
            # Legacy tests only provide top prices. Assume enough volume there so
            # the old public tuple API remains useful for simple unit fixtures.
            volume = (entry_quote / price) * 10.0
        return [(price, volume)] if volume > 0 else []

    @staticmethod
    def estimate_market_buy_from_quote(
        asks: list[tuple[float, float]],
        quote_budget: float,
    ) -> Optional[MarketFillEstimate]:
        """Simulates a market buy that spends an exact quote-currency budget."""
        if quote_budget <= 0:
            return None

        remaining_quote = quote_budget
        base_quantity = 0.0
        quote_spent = 0.0
        worst_price = 0.0
        levels_used = 0

        for price, available_base in asks:
            if remaining_quote <= 1e-10:
                break
            level_quote = price * available_base
            if level_quote <= 0:
                continue
            levels_used += 1
            if level_quote <= remaining_quote:
                base_quantity += available_base
                quote_spent += level_quote
                remaining_quote -= level_quote
                worst_price = price
                continue

            partial_base = remaining_quote / price
            base_quantity += partial_base
            quote_spent += remaining_quote
            remaining_quote = 0.0
            worst_price = price
            break

        if quote_spent <= 0 or base_quantity <= 0:
            return None
        if remaining_quote > max(quote_budget * 1e-8, 1e-8):
            return None

        return MarketFillEstimate(
            average_price=quote_spent / base_quantity,
            base_quantity=base_quantity,
            quote_quantity=quote_spent,
            worst_price=worst_price,
            levels_used=levels_used,
        )

    @staticmethod
    def estimate_market_sell_quantity(
        bids: list[tuple[float, float]],
        base_quantity: float,
    ) -> Optional[MarketFillEstimate]:
        """Simulates a market sell for an exact base-asset quantity."""
        if base_quantity <= 0:
            return None

        remaining_base = base_quantity
        base_sold = 0.0
        quote_received = 0.0
        worst_price = 0.0
        levels_used = 0

        for price, available_base in bids:
            if remaining_base <= 1e-12:
                break
            levels_used += 1
            sell_base = min(available_base, remaining_base)
            base_sold += sell_base
            quote_received += sell_base * price
            remaining_base -= sell_base
            worst_price = price

        if quote_received <= 0 or base_sold <= 0:
            return None
        if remaining_base > max(base_quantity * 1e-8, 1e-10):
            return None

        return MarketFillEstimate(
            average_price=quote_received / base_sold,
            base_quantity=base_sold,
            quote_quantity=quote_received,
            worst_price=worst_price,
            levels_used=levels_used,
        )

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

    def fetch_all_prices(self) -> Dict[str, Dict[str, Any]]:
        """Fetches spot/perp prices (and funding) from all exchanges in parallel."""
        prices: Dict[str, Dict[str, Any]] = {}

        def fetch_exchange_prices(exchange_name: str) -> Tuple[str, Optional[Dict[str, Any]]]:
            """Fetches prices for a single exchange."""
            try:
                result: Dict[str, Any] = {}
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
                                    ORDERBOOK_DEPTH_LIMIT,
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
                                    ORDERBOOK_DEPTH_LIMIT,
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
                            result["spot_bids"] = orderbook["bids"]
                            result["spot_asks"] = orderbook["asks"]
                            result["spot_bid"] = orderbook["bids"][0][0]
                            result["spot_ask"] = orderbook["asks"][0][0]
                            result["spot_bid_volume"] = orderbook["bids"][0][1]
                            result["spot_ask_volume"] = orderbook["asks"][0][1]
                        elif market_type == "perp":
                            result["perp_bids"] = orderbook["bids"]
                            result["perp_asks"] = orderbook["asks"]
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

    def build_executable_hedge_opportunity(
        self,
        prices: Dict[str, Dict[str, Any]],
        spot_exchange: str,
        perp_exchange: str,
        entry_amount: float = ENTRY_AMOUNT,
        min_funding_rate: Optional[float] = MIN_FUNDING_RATE,
        require_funding_rate: bool = REQUIRE_FUNDING_RATE,
    ) -> Optional[HedgeOpportunity]:
        """Builds a depth-aware opportunity for one spot/perp venue pair."""
        spot_data = prices.get(spot_exchange)
        perp_data = prices.get(perp_exchange)
        if not spot_data or not perp_data:
            return None

        funding_rate = perp_data.get("funding_rate")
        if require_funding_rate and funding_rate is None:
            return None
        if min_funding_rate is not None and funding_rate is not None and funding_rate < min_funding_rate:
            return None

        asks = self._levels_from_price_data(spot_data, "spot_asks", "spot_ask", "spot_ask_volume", entry_amount)
        bids = self._levels_from_price_data(perp_data, "perp_bids", "perp_bid", "perp_bid_volume", entry_amount)
        if not asks or not bids:
            return None

        spot_fill = self.estimate_market_buy_from_quote(asks, entry_amount)
        if not spot_fill:
            return None
        perp_fill = self.estimate_market_sell_quantity(bids, spot_fill.base_quantity)
        if not perp_fill:
            return None

        spot_fee = self._get_taker_fee(spot_exchange, "spot")
        perp_fee = self._get_taker_fee(perp_exchange, "futures")
        effective_spot_cost = spot_fill.quote_quantity * (1 + spot_fee)
        effective_perp_proceeds = perp_fill.quote_quantity * (1 - perp_fee)
        if effective_spot_cost <= 0:
            return None

        gross_spread = (perp_fill.average_price - spot_fill.average_price) / spot_fill.average_price
        net_spread = (effective_perp_proceeds - effective_spot_cost) / effective_spot_cost

        return HedgeOpportunity(
            spot_exchange=spot_exchange,
            perp_exchange=perp_exchange,
            spot_price=spot_fill.average_price,
            perp_price=perp_fill.average_price,
            gross_spread=gross_spread,
            net_spread=net_spread,
            quantity=spot_fill.base_quantity,
            spot_quote=spot_fill.quote_quantity,
            perp_quote=perp_fill.quote_quantity,
            spot_fee=spot_fee,
            perp_fee=perp_fee,
            spot_top_ask=asks[0][0],
            perp_top_bid=bids[0][0],
            spot_levels_used=spot_fill.levels_used,
            perp_levels_used=perp_fill.levels_used,
            funding_rate=float(funding_rate) if funding_rate is not None else None,
        )

    def find_best_executable_hedge_opportunity_from_data(
        self,
        prices: Dict[str, Dict[str, Any]],
        spot_filter: Optional[str] = None,
        perp_filter: Optional[str] = None,
        entry_amount: float = ENTRY_AMOUNT,
        min_funding_rate: Optional[float] = MIN_FUNDING_RATE,
        require_funding_rate: bool = REQUIRE_FUNDING_RATE,
    ) -> Optional[HedgeOpportunity]:
        """Finds the strongest executable contango opportunity using orderbook depth."""
        best_combo: Optional[HedgeOpportunity] = None

        for spot_exchange, spot_data in prices.items():
            if "spot_ask" not in spot_data and "spot_asks" not in spot_data:
                continue
            if spot_filter and spot_exchange != spot_filter:
                continue

            for perp_exchange, perp_data in prices.items():
                if "perp_bid" not in perp_data and "perp_bids" not in perp_data:
                    continue
                if perp_filter and perp_exchange != perp_filter:
                    continue

                opportunity = self.build_executable_hedge_opportunity(
                    prices,
                    spot_exchange=spot_exchange,
                    perp_exchange=perp_exchange,
                    entry_amount=entry_amount,
                    min_funding_rate=min_funding_rate,
                    require_funding_rate=require_funding_rate,
                )
                if opportunity is None:
                    continue
                if best_combo is None or opportunity.net_spread > best_combo.net_spread:
                    best_combo = opportunity

        return best_combo

    def find_best_hedge_opportunity_from_data(
        self,
        prices: Dict[str, Dict[str, Any]],
        spot_filter: Optional[str] = None,
        perp_filter: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[str], Optional[float], Optional[float], Optional[float]]:
        """Finds the optimal hedge opportunity using pre-fetched prices."""
        if not prices:
            return None, None, None, None, None
        best_combo = self.find_best_executable_hedge_opportunity_from_data(
            prices,
            spot_filter=spot_filter,
            perp_filter=perp_filter,
            entry_amount=ENTRY_AMOUNT,
            require_funding_rate=False,
        )
        if best_combo:
            return (
                best_combo.spot_exchange,
                best_combo.perp_exchange,
                best_combo.spot_price,
                best_combo.perp_price,
                best_combo.net_spread,
            )

        return None, None, None, None, None

    def calculate_exit_metrics(
        self,
        prices: Dict[str, Dict[str, Any]],
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
