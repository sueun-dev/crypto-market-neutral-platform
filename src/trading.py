"""
Trading module - handles order execution and position management (Bybit-safe + fast spot after perp-ack)
- Fast legging: proceed with spot immediately after perp order ACK (optional)
- Robust fill polling (+ myTrades fallback for Bybit)
- OKX 1x leverage enforcement (isolated, net/one-way)
- Gate.io market buy with quote 'cost'
- Bybit V5-safe: category='linear', isolated margin, positionIdx fallback (0 -> 2 -> None)
- Precision-safe sizing, defensive parsing for ccxt responses
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple
import time
import math

from .exchanges import ExchangeManager
from . import utils


# --- Behavior knobs ---
FILL_POLL_SECONDS   = 8.0     # standard polling window
FILL_POLL_INTERVAL  = 0.25
FAST_POLL_SECONDS   = 1.0     # short window when fast mode is on
PROCEED_ON_PERP_ACK = True    # True: spot fires immediately after perp ACK (or short poll)
MIN_NOTIONAL_SAFETY = 1e-6


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
    """Round a base quantity to market precision/steps if available."""
    if not market_meta:
        return round(quantity, 6)
    return utils.round_to_precision(quantity, market_meta)


def _coalesce(*vals, default=0.0) -> float:
    """Return first value convertible to float; else default."""
    for v in vals:
        if v is None:
            continue
        try:
            return float(v)
        except Exception:
            continue
    return float(default)


def _extract_filled_and_cost(order: Dict, fallback_price: float) -> Tuple[float, float]:
    """
    Extract filled base amount and cost(quote). Fall back to amount*fallback_price.
    Aggregate from nested trades when present.
    """
    if not order:
        return 0.0, 0.0

    filled = _coalesce(order.get("filled"), order.get("amount"))
    cost   = _coalesce(order.get("cost"),   filled * fallback_price)

    trades = order.get("trades") or []
    if trades and (filled <= 0 or cost <= 0):
        t_base = 0.0
        t_quote = 0.0
        for t in trades:
            t_base  += _coalesce(t.get("amount"), t.get("filled"), default=0.0)
            t_quote += _coalesce(t.get("cost"), default=0.0)
        filled = max(filled, t_base)
        cost   = max(cost,   t_quote if t_quote > 0 else filled * fallback_price)

    return float(filled or 0.0), float(cost or 0.0)


def _poll_fetch_order(exchange, order_id: str, symbol: str, fast: bool = False) -> Dict:
    """
    Poll fetch_order for a short/normal period.
    - Normal: wait until closed/filled or timeout
    - Fast: return as soon as we see the order (status open/new also OK to proceed)
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


def _extract_filled_cost_from_trades(exchange, symbol: str, order_id: str, fallback_price: float) -> Tuple[float, float]:
    """
    For Bybit: fetch_my_trades may show fills before fetch_order does.
    """
    try:
        trades = exchange.fetch_my_trades(symbol, since=None, limit=30)
        base = 0.0
        quote = 0.0
        for t in trades or []:
            if t.get("order") == order_id:
                base  += _coalesce(t.get("amount"))
                quote += _coalesce(t.get("cost"), default=0.0)
        if base > 0:
            return base, (quote if quote > 0 else base * fallback_price)
    except Exception:
        pass
    return 0.0, 0.0


def _enforce_min_spot(market_meta: Optional[dict], ref_price: float, qty: float) -> float:
    """
    Ensure spot order meets minQty and minNotional(cost) requirements by up-adjusting.
    """
    if not market_meta or ref_price <= 0:
        return qty
    limits  = market_meta.get('limits') or {}
    min_qty = float((limits.get('amount') or {}).get('min') or 0)
    min_cost= float((limits.get('cost')   or {}).get('min') or 0)

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
    def __init__(self, exchange_manager: ExchangeManager):
        self.exchange_manager = exchange_manager

    # ---------- Leverage & mode helpers (OKX/Bybit/GateIO-safe) ----------
    def _ensure_one_x_leverage(self, exchange_name: str, symbol: str) -> None:
        """
        Always enforce 1x for delta-neutral hedging.

        OKX:
          - one-way/net mode (False)
          - isolated margin via mgnMode
        Bybit:
          - try one-way (set_position_mode False)
          - isolated margin + leverage 1 with category='linear'
        GateIO:
          - leverage 1 if applicable
        """
        ex = self.exchange_manager.get_exchange(exchange_name)
        if not ex:
            raise RuntimeError(f"{exchange_name} not initialized")

        perp = ex["perp"]
        name = exchange_name.lower()

        try:
            if name == "okx":
                try:
                    perp.set_position_mode(False)  # net (one-way)
                except Exception:
                    pass
                perp.set_leverage(1, symbol, params={"mgnMode": "isolated"})

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
                    perp.set_leverage(1, symbol, params={"category": "linear"})
                except Exception:
                    pass

            elif name == "gateio":
                try:
                    perp.set_leverage(1, symbol)
                except Exception:
                    pass

        except Exception as e:
            raise RuntimeError(f"Failed to set 1x leverage/mode on {exchange_name}: {e}")

    # ---------- Spot Buy ----------
    def execute_spot_buy(self, exchange_name: str, amount_usdt: float, coin: str) -> float:
        """
        Execute spot market buy order using quote amount (USD(T)) as budget.
        Returns filled base quantity.
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
                if "options" in spot.__dict__:
                    spot.options["createMarketBuyOrderRequiresPrice"] = False
                order = spot.create_market_buy_order(
                    spot_symbol,
                    amount=amount_usdt,
                    params={"cost": amount_usdt}
                )
            else:
                slippage = 0.004
                pay_price = ref_price * (1.0 + slippage)
                qty = max(amount_usdt / max(pay_price, 1e-12), MIN_NOTIONAL_SAFETY)
                qty = _enforce_min_spot(spot_market, ref_price, qty)
                order = spot.create_order(
                    symbol=spot_symbol,
                    type="market",
                    side="buy",
                    amount=qty
                )

            order_id = (order or {}).get("id") or (order or {}).get("orderId") or ""
            if order_id:
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
                            order2 = spot.create_order(
                                symbol=spot_symbol, type="market", side="buy", amount=bump_qty
                            )
                            oid2 = (order2 or {}).get("id") or ""
                            if oid2:
                                order2 = _poll_fetch_order(spot, oid2, spot_symbol)
                            filled, cost = _extract_filled_and_cost(order2, ref_price)

            print(f"✅ {exchange_name.upper()} Spot Buy: {filled:.8f} {coin} for ${cost:.2f}")
            if filled <= 0:
                raise RuntimeError(f"{exchange_name} spot buy resulted in 0 fill")
            return float(filled)

        except Exception as e:
            print(f"❌ {exchange_name.upper()} spot buy failed: {e}")
            raise

    # ---------- Perp Short ----------
    def execute_perp_short(self, exchange_name: str, quantity: float, coin: str, fast: bool = PROCEED_ON_PERP_ACK) -> Tuple[float, Optional[str]]:
        """
        Execute perpetual market short.
        - When fast=True, return as soon as order ack/short-poll is visible (may return requested qty if fills not yet posted).
        Returns: (effective_filled_or_requested, last_order_id)
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
            min_qty = perp_market.get('limits', {}).get('amount', {}).get('min', 0)
            if min_qty and qty < float(min_qty):
                qty = float(min_qty)

        ref_price = _best_bid(perp, perp_symbol)

        def _try_place(position_idx: Optional[int]) -> Tuple[float, float, Dict, str]:
            params = {"reduceOnly": False}
            if name == "okx":
                params.update({"tdMode": "isolated"})
            elif name == "bybit":
                params.update({"category": "linear"})
                if position_idx is not None:
                    # 0=one-way, 2=hedge-short
                    params.update({"positionIdx": position_idx})

            order = perp.create_order(
                symbol=perp_symbol,
                type="market",
                side="sell",
                amount=qty,
                params=params
            )

            order_id = (order or {}).get("id") or (order or {}).get("orderId") or ""
            if order_id:
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

            print(f"✅ {exchange_name.upper()} Perp Short(ack): {effective:.8f} {coin} @ ${price:.4f}")
            if effective <= 0:
                raise RuntimeError(f"{exchange_name} perp short resulted in 0 fill")
            return float(effective), order_id

        except Exception as e:
            print(f"❌ {exchange_name.upper()} perp short failed: {e}")
            raise

    # ---------- Full Hedge ----------
    def execute_hedge(
        self,
        spot_exchange: str,
        perp_exchange: str,
        spot_price: float,
        perp_price: float,
        coin: str,
        entry_amount: float = 50.0
    ) -> bool:
        """
        Execute delta-neutral hedge:
          1) Perp short first (fast path if enabled)
          2) Spot buy sized to perp (effective) quantity
          3) Reconcile slight mismatch via a tiny reduceOnly order (perp side)
        """
        print(f"Spot: {spot_exchange.upper()} @ ${spot_price:.4f}")
        print(f"Perp: {perp_exchange.upper()} @ ${perp_price:.4f}")
        spread_abs = perp_price - spot_price
        spread_pct = spread_abs / spot_price * 100.0 if spot_price > 0 else 0.0
        print(f"Spread: ${spread_abs:.4f} ({spread_pct:.3f}%)")

        try:
            # 1) Size target
            target_qty = entry_amount / max(spot_price, 1e-12)

            perp_symbols = self.exchange_manager.get_symbols(perp_exchange)
            perp_market  = perp_symbols.get('perp_market') if perp_symbols else None
            perp_qty     = _round_by_market(target_qty, perp_market)
            if perp_market:
                min_qty = perp_market.get('limits', {}).get('amount', {}).get('min', 0)
                if min_qty and perp_qty < float(min_qty):
                    perp_qty = float(min_qty)

            # 2) Perp first (fast)
            perp_eff_qty, perp_order_id = self.execute_perp_short(perp_exchange, perp_qty, coin, fast=PROCEED_ON_PERP_ACK)

            # 3) Spot immediately using the effective perp quantity
            spot_usdt = perp_eff_qty * spot_price
            spot_filled = self.execute_spot_buy(spot_exchange, spot_usdt, coin)

            # 4) Reconcile: fetch actual perp position & align with spot
            try:
                ex_perp = self.exchange_manager.get_exchange(perp_exchange)["perp"]
                positions = ex_perp.fetch_positions()
                real_perp = None
                for p in positions or []:
                    sym = (p.get("symbol") or "")
                    if sym and coin.upper() in sym.upper():
                        # prefer contracts/size
                        real_perp = _coalesce(p.get("contracts"), p.get("contractsSize"), p.get("size"))
                        break
                if not real_perp or real_perp <= 0:
                    # fallback to effective
                    real_perp = perp_eff_qty

                diff = spot_filled - real_perp  # +: spot>perp, -: spot<perp
                tol  = 1e-6   # 1-2 ticks 수준이면 무시
                if abs(diff) > tol:
                    side = "buy" if diff > 0 else "sell"
                    amt  = abs(diff)
                    ex_perp.create_order(
                        symbol=self.exchange_manager.get_symbols(perp_exchange)["perp"],
                        type="market",
                        side=side,
                        amount=amt,
                        params={"reduceOnly": True}
                    )
            except Exception:
                # reconciliation is best-effort
                pass

            print("\n📊 Delta-Neutral Position Summary:")
            print(f"   Spot: {spot_filled:.8f} {coin} bought")
            print(f"   Perp: {perp_eff_qty:.8f} {coin} shorted (effective)")
            print(f"   Spread: ${spread_abs:.4f} per {coin} ({spread_pct:.3f}%)")
            print("\n✅ Delta-neutral position established")
            print("\n📌 Next steps (manual):")
            print(f"   1) 상장(빗썸 등) 시작 후 {coin} 입금")
            print(f"   2) 프리미엄에서 현물 매도")
            print(f"   3) {perp_exchange.upper()} 선물 숏 청산")
            return True

        except Exception as e:
            print(f"\n❌ Hedge execution failed: {e}")
            return False

    # ---------- Position Check ----------
    def check_positions(self, coin: str) -> Dict[str, Dict]:
        """
        Check spot balances and perp positions across all configured exchanges.
        Returns:
          {
            'okx': {
              'spot_balance': 0.1234,
              'perp_position': {'contracts': ..., 'side': ..., 'percentage': ..., 'unrealized_pnl': ...} | None
            },
            ...
          }
        """
        results: Dict[str, Dict] = {}
        for exchange_name in self.exchange_manager.symbols.keys():
            try:
                ex = self.exchange_manager.get_exchange(exchange_name)
                spot_bal = ex["spot"].fetch_balance()
                free_map = (spot_bal or {}).get("free", {})
                coin_free = float(free_map.get(coin, 0.0))

                perp_positions = ex["perp"].fetch_positions()
                perp_position = None
                for pos in perp_positions or []:
                    sym = pos.get("symbol") or ""
                    if sym and coin.upper() in sym.upper():
                        perp_position = {
                            "contracts": _coalesce(pos.get("contracts")),
                            "side": pos.get("side"),
                            "percentage": _coalesce(pos.get("percentage")),
                            "unrealized_pnl": _coalesce(pos.get("unrealizedPnl"), pos.get("unrealizedPnlUsd")),
                        }
                        break

                results[exchange_name] = {
                    "spot_balance": coin_free,
                    "perp_position": perp_position,
                }

            except Exception as e:
                print(f"⚠️ {exchange_name.upper()} position check failed: {e}")

        return results
