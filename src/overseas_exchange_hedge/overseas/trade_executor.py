"""Order execution helpers for delta-neutral hedging.

Key behaviors:
    • Pre-trade executable spread recheck using current orderbook depth.
    • Quantity-matched market legs with immediate imbalance cleanup.
    • Robust fill polling with myTrades fallback for Bybit.
    • Consistent 1x leverage enforcement across OKX/Bybit/GateIO.
    • Precision-aware sizing and defensive parsing of ccxt responses.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from ..common import utils
from ..config import FUTURES_LEVERAGE, MIN_EXECUTABLE_NET_SPREAD, ORDERBOOK_DEPTH_LIMIT
from .exchange_manager import ExchangeManager
from .price_analyzer import HedgeOpportunity, PriceAnalyzer

logger = logging.getLogger(__name__)

# --- Behavior knobs ---
FILL_POLL_SECONDS = 1.0  # standard polling window
FILL_POLL_INTERVAL = 0.25
FAST_POLL_SECONDS = 1.0  # short window when fast mode is on
PROCEED_ON_PERP_ACK = True  # True: spot fires immediately after perp ACK (or short poll)
MIN_NOTIONAL_SAFETY = 1e-6
SPOT_BUY_QUOTE_BUFFER = 0.0


@dataclass(frozen=True)
class HedgeExecutionResult:
    """Normalized result for one completed delta-neutral entry."""

    quantity: float
    spot_price: float
    perp_price: float
    gross_spread: float
    net_spread: float
    spot_exchange: str
    perp_exchange: str


# =========================
# Helpers
# =========================


def _best_ask(exchange, symbol) -> float:
    ob = exchange.fetch_order_book(symbol)
    return float(ob["asks"][0][0]) if ob and ob.get("asks") else 0.0


def _best_bid(exchange, symbol) -> float:
    ob = exchange.fetch_order_book(symbol)
    return float(ob["bids"][0][0]) if ob and ob.get("bids") else 0.0


def _round_by_market(quantity: float, market_meta: Optional[Dict]) -> float:
    """Rounds a base quantity to the market precision/steps if provided."""
    if not market_meta:
        return round(quantity, 6)
    return utils.round_to_precision(quantity, market_meta)


def _coalesce(*vals, default=0.0) -> float:
    """Returns the first value convertible to float, otherwise the default."""
    for v in vals:
        if v is None:
            continue
        try:
            return float(v)
        except Exception:
            continue
    return float(default)


def _extract_filled_and_cost(order: Dict, fallback_price: float) -> Tuple[float, float]:
    """Extracts filled base amount and quote cost from a ccxt order payload.

    Args:
        order: Raw order dictionary from ccxt.
        fallback_price: Reference price used when cost is missing.

    Returns:
        Tuple of (filled_base, quote_cost). Falls back to nested trades and
        fallback_price when direct fields are unavailable.
    """
    if not order:
        return 0.0, 0.0

    status = (order.get("status") or "").lower()
    filled = _coalesce(order.get("filled"), default=0.0)
    if filled <= 0 and status in ("closed", "filled"):
        filled = _coalesce(order.get("amount"), default=0.0)
    cost = _coalesce(order.get("cost"), default=0.0)

    trades = order.get("trades") or []
    if trades and (filled <= 0 or cost <= 0):
        t_base = 0.0
        t_quote = 0.0
        for t in trades:
            t_base += _coalesce(t.get("amount"), t.get("filled"), default=0.0)
            t_quote += _coalesce(t.get("cost"), default=0.0)
        filled = max(filled, t_base)
        cost = max(cost, t_quote if t_quote > 0 else filled * fallback_price)

    if cost <= 0 and filled > 0:
        cost = filled * fallback_price

    return float(filled or 0.0), float(cost or 0.0)


def _has_reliable_fill(order: Dict, fallback_price: float) -> bool:
    """Returns True only when the order payload contains credible fill evidence."""
    if not order:
        return False
    status = (order.get("status") or "").lower()
    filled, cost = _extract_filled_and_cost(order, fallback_price)
    if filled <= 0:
        return False
    if order.get("filled") is not None or order.get("trades"):
        return True
    if status in ("closed", "filled"):
        return True
    return cost > 0 and order.get("cost") is not None


def _poll_fetch_order(exchange, order_id: str, symbol: str, fast: bool = False) -> Dict:
    """Polls `fetch_order` until an acknowledgement or fill is observed.

    Args:
        exchange: ccxt exchange instance.
        order_id: Identifier returned by create_order.
        symbol: Trading pair symbol.
        fast: When True, return once the order is visible/open.

    Returns:
        Last observed order payload (may be empty dict on timeout).
    """
    deadline = time.time() + (FAST_POLL_SECONDS if fast else FILL_POLL_SECONDS)
    last = None
    while time.time() < deadline:
        try:
            last = exchange.fetch_order(order_id, symbol)
            if not last:
                time.sleep(FILL_POLL_INTERVAL)
                continue
            status = (last.get("status") or "").lower()
            filled = _coalesce(last.get("filled"))
            if status in ("closed", "filled") or filled > 0:
                return last
            if fast and status in ("open", "new", ""):
                # approved/visible: good enough to proceed
                return last
        except Exception:
            pass
        time.sleep(FILL_POLL_INTERVAL)
    return last or {}


def _extract_filled_cost_from_trades(
    exchange, symbol: str, order_id: str, fallback_price: float
) -> Tuple[float, float]:
    """Extracts fills from `fetch_my_trades` when fetch_order is delayed.

    Args:
        exchange: ccxt exchange instance.
        symbol: Trading pair symbol.
        order_id: Order identifier to filter trades.
        fallback_price: Price used when trade cost is missing.

    Returns:
        Tuple of (filled_base, quote_cost) pulled from recent trades.
    """
    try:
        trades = exchange.fetch_my_trades(symbol, since=None, limit=30)
        base = 0.0
        quote = 0.0
        for t in trades or []:
            if t.get("order") == order_id:
                base += _coalesce(t.get("amount"))
                quote += _coalesce(t.get("cost"), default=0.0)
        if base > 0:
            return base, (quote if quote > 0 else base * fallback_price)
    except Exception:
        pass
    return 0.0, 0.0


def _enforce_min_spot(market_meta: Optional[dict], ref_price: float, qty: float) -> float:
    """Ensures spot order sizes satisfy minQty and minNotional requirements.

    Args:
        market_meta: Market metadata dictionary from ccxt.
        ref_price: Current reference price.
        qty: Proposed base quantity.

    Returns:
        Quantity adjusted upward to satisfy exchange constraints.
    """
    if not market_meta or ref_price <= 0:
        return qty
    limits = market_meta.get("limits") or {}
    min_qty = float((limits.get("amount") or {}).get("min") or 0)
    min_cost = float((limits.get("cost") or {}).get("min") or 0)

    if min_cost > 0:
        qty = max(qty, min_cost / ref_price)
    if min_qty > 0:
        qty = max(qty, min_qty)

    qty = _round_by_market(qty, market_meta)
    if min_cost > 0 and qty * ref_price < min_cost:
        qty = _round_by_market(qty * 1.0000005, market_meta)
    return qty


# =========================
# Trade Executor
# =========================


class TradeExecutor:
    """Executes spot/perp orders with exchange-specific safeguards."""

    def __init__(self, exchange_manager: ExchangeManager):
        self.exchange_manager = exchange_manager

    # ---------- Leverage & mode helpers (OKX/Bybit/GateIO-safe) ----------
    def _ensure_one_x_leverage(self, exchange_name: str, symbol: str) -> None:
        """Enforces 1x leverage and one-way mode for delta-neutral hedging.

        Args:
            exchange_name: Exchange identifier (gateio/bybit/okx).
            symbol: Perpetual symbol to configure.

        Raises:
            RuntimeError: If leverage/mode configuration fails.
        """
        ex = self.exchange_manager.get_exchange(exchange_name)
        if not ex:
            raise RuntimeError(f"{exchange_name} not initialized")

        perp = ex["perp"]
        name = exchange_name.lower()
        target_leverage = int(FUTURES_LEVERAGE or 1)
        if target_leverage < 1:
            target_leverage = 1

        try:
            if name == "okx":
                try:
                    perp.set_position_mode(False)  # net (one-way)
                except Exception:
                    pass
                perp.set_leverage(target_leverage, symbol, params={"mgnMode": "isolated"})

            elif name == "bybit":
                try:
                    perp.set_position_mode(False)  # one-way
                except Exception:
                    pass
                try:
                    if hasattr(perp, "set_margin_mode"):
                        perp.set_margin_mode("ISOLATED", symbol, params={"category": "linear"})
                except Exception:
                    pass
                try:
                    perp.set_leverage(target_leverage, symbol, params={"category": "linear"})
                except Exception:
                    pass

            elif name == "gateio":
                try:
                    perp.set_leverage(target_leverage, symbol)
                except Exception:
                    pass

        except Exception as e:
            raise RuntimeError(f"Failed to set 1x leverage/mode on {exchange_name}: {e}")

    # ---------- Spot Buy ----------
    def execute_spot_buy(self, exchange_name: str, amount_usdt: float, coin: str) -> float:
        """Executes a spot market buy using a quote-amount budget.

        Args:
            exchange_name: Spot exchange identifier.
            amount_usdt: Quote budget in USDT.
            coin: Base asset symbol.

        Returns:
            Filled base asset quantity.

        Raises:
            RuntimeError: If the exchange is not initialized or the order fails.
            ValueError: If the amount_usdt is non-positive.
        """
        ex = self.exchange_manager.get_exchange(exchange_name)
        symbols = self.exchange_manager.get_symbols(exchange_name)
        if not ex or not symbols:
            raise RuntimeError(f"Exchange {exchange_name} not initialized")

        spot = ex["spot"]
        spot_symbol = symbols["spot"]
        spot_market = symbols.get("spot_market")

        if amount_usdt <= 0:
            raise ValueError("amount_usdt must be > 0")

        name = exchange_name.lower()
        ref_price = _best_ask(spot, spot_symbol)
        if ref_price <= 0:
            raise RuntimeError(f"Cannot get spot ask price from {exchange_name}")

        try:
            if name == "gateio":
                options = getattr(spot, "options", None)
                if isinstance(options, dict):
                    options["createMarketBuyOrderRequiresPrice"] = False
                else:
                    spot.options = {"createMarketBuyOrderRequiresPrice": False}
                order = spot.create_market_buy_order(spot_symbol, amount=amount_usdt, params={"cost": amount_usdt})
            else:
                slippage = 0.004
                pay_price = ref_price * (1.0 + slippage)
                qty = max(amount_usdt / max(pay_price, 1e-12), MIN_NOTIONAL_SAFETY)
                qty = _enforce_min_spot(spot_market, ref_price, qty)
                order = spot.create_order(symbol=spot_symbol, type="market", side="buy", amount=qty)

            order_id = (order or {}).get("id") or (order or {}).get("orderId") or ""
            if order_id and not _has_reliable_fill(order or {}, ref_price):
                order = _poll_fetch_order(spot, order_id, spot_symbol)

            filled, cost = _extract_filled_and_cost(order, ref_price)

            # Fallbacks: myTrades or small bump retry
            if filled <= 0 and order_id:
                alt_filled, alt_cost = _extract_filled_cost_from_trades(spot, spot_symbol, order_id, ref_price)
                if alt_filled > 0:
                    filled, cost = alt_filled, alt_cost
                else:
                    if name in ("bybit", "okx"):
                        bump_qty = _enforce_min_spot(spot_market, ref_price, qty * 1.02)
                        if bump_qty > qty:
                            order2 = spot.create_order(symbol=spot_symbol, type="market", side="buy", amount=bump_qty)
                            oid2 = (order2 or {}).get("id") or ""
                            if oid2 and not _has_reliable_fill(order2 or {}, ref_price):
                                order2 = _poll_fetch_order(spot, oid2, spot_symbol)
                            filled, cost = _extract_filled_and_cost(order2, ref_price)

            logger.info("✅ %s Spot Buy: %.8f %s for $%.2f", exchange_name.upper(), filled, coin, cost)
            if filled <= 0:
                raise RuntimeError(f"{exchange_name} spot buy resulted in 0 fill")
            return float(filled)

        except Exception as e:
            logger.error("❌ %s spot buy failed: %s", exchange_name.upper(), e)
            raise

    def execute_spot_buy_quantity(
        self,
        exchange_name: str,
        quantity: float,
        coin: str,
        quote_budget: Optional[float] = None,
    ) -> float:
        """Executes a spot market buy for a target base quantity.

        Gate.io's ccxt market-buy path is quote-cost oriented in this project,
        so it uses a bounded quote budget and then reconciles the filled base.
        Other venues receive the base quantity directly.
        """
        ex = self.exchange_manager.get_exchange(exchange_name)
        symbols = self.exchange_manager.get_symbols(exchange_name)
        if not ex or not symbols:
            raise RuntimeError(f"Exchange {exchange_name} not initialized")

        spot = ex["spot"]
        spot_symbol = symbols["spot"]
        spot_market = symbols.get("spot_market")

        if quantity <= 0:
            raise ValueError("quantity must be > 0")

        ref_price = _best_ask(spot, spot_symbol)
        if ref_price <= 0:
            raise RuntimeError(f"Cannot get spot ask price from {exchange_name}")

        name = exchange_name.lower()
        requested_qty = _round_by_market(quantity, spot_market)
        qty = _enforce_min_spot(spot_market, ref_price, requested_qty)
        if qty > quantity * 1.001:
            raise RuntimeError(f"{exchange_name} spot minimum would overbuy: requested {quantity}, adjusted {qty}")

        try:
            if name == "gateio":
                options = getattr(spot, "options", None)
                if isinstance(options, dict):
                    options["createMarketBuyOrderRequiresPrice"] = False
                else:
                    spot.options = {"createMarketBuyOrderRequiresPrice": False}
                max_cost = quote_budget if quote_budget is not None else qty * ref_price * (1 + SPOT_BUY_QUOTE_BUFFER)
                order = spot.create_market_buy_order(spot_symbol, amount=max_cost, params={"cost": max_cost})
            else:
                order = spot.create_order(symbol=spot_symbol, type="market", side="buy", amount=qty)

            order_id = (order or {}).get("id") or (order or {}).get("orderId") or ""
            if order_id and not _has_reliable_fill(order or {}, ref_price):
                order = _poll_fetch_order(spot, order_id, spot_symbol)

            filled, cost = _extract_filled_and_cost(order, ref_price)

            if filled <= 0 and order_id:
                alt_filled, alt_cost = _extract_filled_cost_from_trades(spot, spot_symbol, order_id, ref_price)
                if alt_filled > 0:
                    filled, cost = alt_filled, alt_cost

            logger.info("✅ %s Spot Buy: %.8f %s for $%.2f", exchange_name.upper(), filled, coin, cost)
            if filled <= 0:
                raise RuntimeError(f"{exchange_name} spot buy resulted in 0 fill")
            return float(filled)

        except Exception as e:
            logger.error("❌ %s spot buy failed: %s", exchange_name.upper(), e)
            raise

    def execute_spot_sell(self, exchange_name: str, quantity: float, coin: str) -> float:
        """Executes a spot market sell using a base quantity.

        Args:
            exchange_name: Spot exchange identifier.
            quantity: Base amount to sell.
            coin: Base asset symbol.

        Returns:
            Filled base asset quantity.

        Raises:
            RuntimeError: If the exchange is not initialized or the order fails.
            ValueError: If the quantity is non-positive.
        """
        ex = self.exchange_manager.get_exchange(exchange_name)
        symbols = self.exchange_manager.get_symbols(exchange_name)
        if not ex or not symbols:
            raise RuntimeError(f"Exchange {exchange_name} not initialized")

        spot = ex["spot"]
        spot_symbol = symbols["spot"]

        if quantity <= 0:
            raise ValueError("quantity must be > 0")

        ref_price = _best_bid(spot, spot_symbol)
        if ref_price <= 0:
            raise RuntimeError(f"Cannot get spot bid price from {exchange_name}")

        try:
            order = spot.create_order(symbol=spot_symbol, type="market", side="sell", amount=quantity)

            order_id = (order or {}).get("id") or (order or {}).get("orderId") or ""
            if order_id and not _has_reliable_fill(order or {}, ref_price):
                order = _poll_fetch_order(spot, order_id, spot_symbol)

            filled, cost = _extract_filled_and_cost(order, ref_price)

            if filled <= 0 and order_id:
                alt_filled, alt_cost = _extract_filled_cost_from_trades(spot, spot_symbol, order_id, ref_price)
                if alt_filled > 0:
                    filled, cost = alt_filled, alt_cost

            logger.info("✅ %s Spot Sell: %.8f %s for $%.2f", exchange_name.upper(), filled, coin, cost)
            if filled <= 0:
                raise RuntimeError(f"{exchange_name} spot sell resulted in 0 fill")
            return float(filled)
        except Exception as e:
            logger.error("❌ %s spot sell failed: %s", exchange_name.upper(), e)
            raise

    # ---------- Perp Short ----------
    def execute_perp_short(
        self, exchange_name: str, quantity: float, coin: str, fast: bool = PROCEED_ON_PERP_ACK
    ) -> Tuple[float, Optional[str]]:
        """Places a perpetual market short and returns effective filled size.

        Args:
            exchange_name: Perpetual exchange identifier.
            quantity: Target base quantity to short.
            coin: Base asset symbol.
            fast: If True, proceed once the order is acknowledged.

        Returns:
            Tuple of (effective_filled_quantity, order_id).

        Raises:
            RuntimeError: If exchange is not initialized or leverage configuration fails.
            ValueError: If quantity is non-positive.
        """
        ex = self.exchange_manager.get_exchange(exchange_name)
        symbols = self.exchange_manager.get_symbols(exchange_name)
        if not ex or not symbols:
            raise RuntimeError(f"Exchange {exchange_name} not initialized")

        perp = ex["perp"]
        perp_symbol = symbols["perp"]
        perp_market = symbols.get("perp_market")
        name = exchange_name.lower()

        if quantity <= 0:
            raise ValueError("quantity must be > 0")

        # 1) Ensure leverage/mode ahead of time
        self._ensure_one_x_leverage(exchange_name, perp_symbol)

        # 2) Round quantity to market precision (and lift to min if needed)
        qty = _round_by_market(quantity, perp_market)
        if perp_market:
            min_qty = perp_market.get("limits", {}).get("amount", {}).get("min", 0)
            if min_qty and qty < float(min_qty):
                qty = float(min_qty)

        ref_price = _best_bid(perp, perp_symbol)

        def _try_place(position_idx: Optional[int]) -> Tuple[float, float, Dict, str]:
            params: Dict[str, Any] = {"reduceOnly": False}
            if name == "okx":
                params.update({"tdMode": "isolated"})
            elif name == "bybit":
                params.update({"category": "linear"})
                if position_idx is not None:
                    # 0=one-way, 2=hedge-short
                    params.update({"positionIdx": position_idx})

            order = perp.create_order(symbol=perp_symbol, type="market", side="sell", amount=qty, params=params)

            order_id = (order or {}).get("id") or (order or {}).get("orderId") or ""
            if order_id and not _has_reliable_fill(order or {}, ref_price):
                order = _poll_fetch_order(perp, order_id, perp_symbol, fast=fast)

            filled, _ = _extract_filled_and_cost(order, ref_price)
            price = _coalesce((order or {}).get("price"), ref_price)

            if filled <= 0 and order_id and not fast:
                alt_filled, _alt_cost = _extract_filled_cost_from_trades(perp, perp_symbol, order_id, ref_price)
                if alt_filled > 0:
                    filled = alt_filled

            return filled, price, (order or {}), order_id

        try:
            order_id = None
            if name == "bybit":
                filled, price, order, order_id = _try_place(position_idx=0)
                if filled <= 0 and not fast:
                    filled, price, order, order_id = _try_place(position_idx=2)
                if filled <= 0 and not fast:
                    filled, price, order, order_id = _try_place(position_idx=None)
            else:
                filled, price, order, order_id = _try_place(position_idx=None)

            # Fast mode: if still 0, proceed with requested qty (we reconcile later)
            effective = filled if filled > 0 else (qty if fast else 0.0)

            logger.info("✅ %s Perp Short(ack): %.8f %s @ $%.4f", exchange_name.upper(), effective, coin, price)
            if effective <= 0:
                raise RuntimeError(f"{exchange_name} perp short resulted in 0 fill")
            return float(effective), order_id

        except Exception as e:
            logger.error("❌ %s perp short failed: %s", exchange_name.upper(), e)
            raise

    # ---------- Full Hedge ----------
    def _recheck_executable_opportunity(
        self,
        spot_exchange: str,
        perp_exchange: str,
        coin: str,
        entry_amount: float,
    ) -> Optional[HedgeOpportunity]:
        """Re-fetches depth/funding for the selected pair in parallel before orders."""
        spot_pair = self.exchange_manager.get_exchange(spot_exchange)
        perp_pair = self.exchange_manager.get_exchange(perp_exchange)
        spot_symbols = self.exchange_manager.get_symbols(spot_exchange)
        perp_symbols = self.exchange_manager.get_symbols(perp_exchange)
        if not spot_pair or not perp_pair or not spot_symbols or not perp_symbols:
            return None

        spot_symbol = spot_symbols.get("spot")
        perp_symbol = perp_symbols.get("perp")
        if not spot_symbol or not perp_symbol:
            return None

        analyzer = PriceAnalyzer(self.exchange_manager)
        with ThreadPoolExecutor(max_workers=3) as executor:
            spot_orderbook_future = executor.submit(
                spot_pair["spot"].fetch_order_book,
                spot_symbol,
                ORDERBOOK_DEPTH_LIMIT,
            )
            perp_orderbook_future = executor.submit(
                perp_pair["perp"].fetch_order_book,
                perp_symbol,
                ORDERBOOK_DEPTH_LIMIT,
            )
            funding_future = executor.submit(analyzer.fetch_funding_rate, perp_exchange, perp_symbol)

            try:
                spot_orderbook = spot_orderbook_future.result()
                perp_orderbook = perp_orderbook_future.result()
            except Exception as exc:
                logger.warning(
                    "⚠️ Pre-trade depth recheck failed for %s/%s %s: %s",
                    spot_exchange,
                    perp_exchange,
                    coin,
                    exc,
                )
                return None

            try:
                funding_rate = funding_future.result()
            except Exception as exc:
                logger.warning(
                    "⚠️ Pre-trade funding recheck failed for %s %s: %s",
                    perp_exchange,
                    coin,
                    exc,
                )
                funding_rate = None

        if not spot_orderbook.get("asks") or not spot_orderbook.get("bids"):
            return None
        if not perp_orderbook.get("asks") or not perp_orderbook.get("bids"):
            return None

        prices: Dict[str, Dict[str, Any]] = {}
        prices.setdefault(spot_exchange, {}).update(
            {
                "spot_asks": spot_orderbook["asks"],
                "spot_bids": spot_orderbook["bids"],
                "spot_ask": spot_orderbook["asks"][0][0],
                "spot_bid": spot_orderbook["bids"][0][0],
            }
        )
        prices.setdefault(perp_exchange, {}).update(
            {
                "perp_bids": perp_orderbook["bids"],
                "perp_asks": perp_orderbook["asks"],
                "perp_bid": perp_orderbook["bids"][0][0],
                "perp_ask": perp_orderbook["asks"][0][0],
            }
        )

        if funding_rate is not None:
            prices[perp_exchange]["funding_rate"] = funding_rate

        return analyzer.build_executable_hedge_opportunity(
            prices,
            spot_exchange=spot_exchange,
            perp_exchange=perp_exchange,
            entry_amount=entry_amount,
        )

    def execute_hedge(
        self,
        spot_exchange: str,
        perp_exchange: str,
        spot_price: float,
        perp_price: float,
        coin: str,
        entry_amount: float = 50.0,
        target_quantity: Optional[float] = None,
        min_net_spread: float = MIN_EXECUTABLE_NET_SPREAD,
    ) -> Optional[HedgeExecutionResult]:
        """Executes a delta-neutral hedge across spot and perpetual venues.

        Args:
            spot_exchange: Exchange to buy spot.
            perp_exchange: Exchange to short perpetual.
            spot_price: Current spot price used for sizing.
            perp_price: Current perp price (for logging).
            coin: Base asset symbol.
            entry_amount: Quote budget in USDT.

        Returns:
            HedgeExecutionResult if both legs are reconciled, otherwise None.
        """
        opportunity = self._recheck_executable_opportunity(spot_exchange, perp_exchange, coin, entry_amount)
        if opportunity is None:
            logger.warning("❌ Pre-trade depth recheck failed; skipping hedge.")
            return None
        if opportunity.net_spread < min_net_spread:
            logger.warning(
                "❌ Pre-trade net spread %.3f%% < required %.3f%%; skipping hedge.",
                opportunity.net_spread * 100,
                min_net_spread * 100,
            )
            return None

        spot_price = opportunity.spot_price
        perp_price = opportunity.perp_price
        target_quantity = (
            opportunity.quantity if target_quantity is None else min(target_quantity, opportunity.quantity)
        )
        logger.info("Spot: %s @ $%.4f", spot_exchange.upper(), spot_price)
        logger.info("Perp: %s @ $%.4f", perp_exchange.upper(), perp_price)
        spread_abs = perp_price - spot_price
        spread_pct = spread_abs / spot_price * 100.0 if spot_price > 0 else 0.0
        logger.info("Spread: $%.4f (%.3f%%)", spread_abs, spread_pct)

        try:
            # 1) Size target from executable depth, not just the top ask.
            target_qty = target_quantity or (entry_amount / max(spot_price, 1e-12))

            perp_symbols = self.exchange_manager.get_symbols(perp_exchange)
            perp_market = perp_symbols.get("perp_market") if perp_symbols else None
            perp_qty = _round_by_market(target_qty, perp_market)
            if perp_market:
                min_qty = perp_market.get("limits", {}).get("amount", {}).get("min", 0)
                if min_qty and perp_qty < float(min_qty):
                    perp_qty = float(min_qty)
            if perp_qty > target_qty * 1.000001:
                logger.warning(
                    "❌ Perp size precision/minimum would oversize %.8f → %.8f %s; skipping hedge.",
                    target_qty,
                    perp_qty,
                    coin,
                )
                return None

            perp_eff_qty = 0.0
            spot_filled = 0.0

            # 2) Perp first, but wait for fill details before buying spot.
            perp_eff_qty, _perp_order_id = self.execute_perp_short(perp_exchange, perp_qty, coin, fast=False)

            # 3) Buy the same base quantity on spot with a bounded quote budget.
            quote_budget = perp_eff_qty * spot_price * (1 + SPOT_BUY_QUOTE_BUFFER)
            spot_filled = self.execute_spot_buy_quantity(spot_exchange, perp_eff_qty, coin, quote_budget=quote_budget)

            # 4) Reconcile the two legs immediately.
            tol = max(perp_eff_qty * 1e-6, 1e-8)
            if spot_filled < perp_eff_qty - tol:
                excess_short = perp_eff_qty - spot_filled
                logger.warning("   ⚠️ Spot underfilled by %.8f %s; covering excess short.", excess_short, coin)
                self.execute_perp_cover(perp_exchange, excess_short, coin)
                perp_eff_qty = spot_filled
            elif spot_filled > perp_eff_qty + tol:
                excess_spot = spot_filled - perp_eff_qty
                logger.warning("   ⚠️ Spot overfilled by %.8f %s; selling excess spot.", excess_spot, coin)
                self.execute_spot_sell(spot_exchange, excess_spot, coin)
                spot_filled = perp_eff_qty

            final_qty = min(spot_filled, perp_eff_qty)
            if final_qty <= 0:
                raise RuntimeError("hedge reconciled to zero quantity")

            logger.info("\n📊 Delta-Neutral Position Summary:")
            logger.info("   Spot: %.8f %s bought", final_qty, coin)
            logger.info("   Perp: %.8f %s shorted", final_qty, coin)
            logger.info("   Spread: $%.4f per %s (%.3f%%)", spread_abs, coin, spread_pct)
            logger.info("   Net after taker fees: %.3f%%", opportunity.net_spread * 100)
            logger.info("\n✅ Delta-neutral position established")
            logger.info("\n📌 Next steps (manual):")
            logger.info("   1) 상장(빗썸 등) 시작 후 %s 입금", coin)
            logger.info("   2) 프리미엄에서 현물 매도")
            logger.info("   3) %s 선물 숏 청산", perp_exchange.upper())
            return HedgeExecutionResult(
                quantity=final_qty,
                spot_price=spot_price,
                perp_price=perp_price,
                gross_spread=opportunity.gross_spread,
                net_spread=opportunity.net_spread,
                spot_exchange=spot_exchange,
                perp_exchange=perp_exchange,
            )

        except Exception as e:
            if "perp_eff_qty" in locals() and perp_eff_qty > 0 and ("spot_filled" not in locals() or spot_filled <= 0):
                try:
                    logger.warning("⚠️ Spot leg failed after perp short; covering %.8f %s.", perp_eff_qty, coin)
                    self.execute_perp_cover(perp_exchange, perp_eff_qty, coin)
                except Exception as cover_exc:
                    logger.critical("❌ Emergency perp cover failed; manual check required: %s", cover_exc)
            logger.error("\n❌ Hedge execution failed: %s", e)
            return None

    def execute_perp_cover(self, exchange_name: str, quantity: float, coin: str) -> float:
        """Covers (buys back) a perpetual short with a reduce-only market order.

        Args:
            exchange_name: Perpetual exchange identifier.
            quantity: Base amount to cover.
            coin: Base asset symbol.

        Returns:
            Filled base quantity.

        Raises:
            RuntimeError: If exchange is not initialized or order fails.
            ValueError: If quantity is non-positive.
        """
        ex = self.exchange_manager.get_exchange(exchange_name)
        symbols = self.exchange_manager.get_symbols(exchange_name)
        if not ex or not symbols:
            raise RuntimeError(f"Exchange {exchange_name} not initialized")

        perp = ex["perp"]
        perp_symbol = symbols["perp"]
        perp_market = symbols.get("perp_market")
        name = exchange_name.lower()

        if quantity <= 0:
            raise ValueError("quantity must be > 0")

        qty = _round_by_market(quantity, perp_market)
        if perp_market:
            min_qty = perp_market.get("limits", {}).get("amount", {}).get("min", 0)
            if min_qty and qty < float(min_qty):
                qty = float(min_qty)

        ref_price = _best_ask(perp, perp_symbol)

        params: Dict[str, Any] = {"reduceOnly": True}
        if name == "okx":
            params.update({"tdMode": "isolated"})
        elif name == "bybit":
            params.update({"category": "linear"})
        elif name == "gateio":
            params.update({"settle": "usdt"})

        try:
            order = perp.create_order(symbol=perp_symbol, type="market", side="buy", amount=qty, params=params)

            order_id = (order or {}).get("id") or (order or {}).get("orderId") or ""
            if order_id and not _has_reliable_fill(order or {}, ref_price):
                order = _poll_fetch_order(perp, order_id, perp_symbol)

            filled, _ = _extract_filled_and_cost(order, ref_price)

            if filled <= 0 and order_id:
                alt_filled, _ = _extract_filled_cost_from_trades(perp, perp_symbol, order_id, ref_price)
                if alt_filled > 0:
                    filled = alt_filled

            logger.info("✅ %s Perp Cover: %.8f %s", exchange_name.upper(), filled, coin)
            if filled <= 0:
                raise RuntimeError(f"{exchange_name} perp cover resulted in 0 fill")
            return float(filled)
        except Exception as e:
            logger.error("❌ %s perp cover failed: %s", exchange_name.upper(), e)
            raise
