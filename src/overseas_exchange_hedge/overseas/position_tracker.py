"""Position tracking for average price and exit calculations."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from ..common.paths import state_file
from ..config import EXCHANGE_FEES

logger = logging.getLogger(__name__)

PositionEntry = Dict[str, Any]
PositionState = Dict[str, Any]


class PositionTracker:
    """Persists hedge entries and computes aggregate position metrics."""

    def __init__(self) -> None:
        self.positions_path = state_file("positions.json", legacy_filename="positions.json")
        self.positions: PositionState = self.load_positions()
        self._ensure_compatibility()
        self._recompute_totals()

    def load_positions(self) -> PositionState:
        """Loads existing positions from disk or returns an empty template."""
        if self.positions_path.exists():
            try:
                with self.positions_path.open("r", encoding="utf-8") as file:
                    return json.load(file)
            except (json.JSONDecodeError, OSError):
                pass
        return self._initial_state()

    def save_positions(self) -> None:
        """Persists the current position state to disk."""
        with self.positions_path.open("w", encoding="utf-8") as file:
            json.dump(self.positions, file, indent=2)

    def add_entry(
        self,
        coin: str,
        spot_price: float,
        quantity: float,
        spot_exchange: str,
        perp_exchange: str,
        perp_price: float,
        spread: float,
    ) -> PositionEntry:
        """Adds a new hedge entry and refreshes averages.

        Args:
            coin: Target asset symbol.
            spot_price: Executed spot price in USDT.
            quantity: Filled base asset quantity.
            spot_exchange: Spot venue name.
            perp_exchange: Perpetual venue name.
            perp_price: Executed perp price in USDT.
            spread: Net spread captured for the entry.

        Returns:
            The normalized entry record that was stored.
        """
        if self.positions["current_coin"] != coin:
            self.positions = self._initial_state(coin)

        spot_fee = self._get_fee(spot_exchange, "spot")
        perp_fee = self._get_fee(perp_exchange, "futures")

        spot_unit_with_fee = spot_price * (1 + spot_fee)
        perp_unit_after_fee = perp_price * (1 - perp_fee)

        entry: PositionEntry = {
            "timestamp": datetime.now().isoformat(),
            "coin": coin,
            "spot_price": spot_price,
            "quantity": quantity,
            "cost_usdt": spot_price * quantity,
            "spot_exchange": spot_exchange,
            "perp_exchange": perp_exchange,
            "perp_price": perp_price,
            "spread": spread,
            "spot_fee": spot_fee,
            "perp_fee": perp_fee,
            "remaining_quantity": quantity,
        }

        self.positions["entries"].append(entry)
        self.positions["total_quantity"] += quantity
        self.positions["total_cost_usdt"] += entry["cost_usdt"]
        self.positions["average_price"] = self.positions["total_cost_usdt"] / self.positions["total_quantity"]

        self.positions["total_spot_cost"] += spot_unit_with_fee * quantity
        self.positions["total_perp_proceeds"] += perp_unit_after_fee * quantity
        self._recompute_totals()
        self.save_positions()
        return entry

    def get_bithumb_targets(self, usdt_krw_rate: float) -> Optional[Dict[str, float]]:
        """Calculates Bithumb exit targets in KRW.

        Args:
            usdt_krw_rate: USDT price in KRW from a Korean venue.

        Returns:
            Target levels keyed by label, or None if no positions exist.
        """
        if self.positions["average_price"] == 0:
            return None

        avg_price = self.positions["average_price"]
        total_quantity = self.positions["total_quantity"]
        total_cost_usdt = self.positions["total_cost_usdt"]

        breakeven_price = avg_price * 1.0025

        return {
            "average_price_usdt": avg_price,
            "total_quantity": total_quantity,
            "total_cost_usdt": total_cost_usdt,
            "breakeven_krw": breakeven_price * usdt_krw_rate,
            "target_1_percent": breakeven_price * 1.01 * usdt_krw_rate,
            "target_3_percent": breakeven_price * 1.03 * usdt_krw_rate,
            "target_5_percent": breakeven_price * 1.05 * usdt_krw_rate,
            "target_10_percent": breakeven_price * 1.10 * usdt_krw_rate,
        }

    def display_position_summary(self, usdt_krw_rate: float) -> None:
        """Prints a summary of open positions and KRW targets."""
        if not self.positions["entries"]:
            logger.info("\n📊 포지션 없음")
            return

        coin = self.positions["current_coin"]
        avg_price = self.positions["average_price"]
        total_qty = self.positions["total_quantity"]
        total_cost = self.positions["total_cost_usdt"]

        logger.info("\n📊 현재 포지션 요약 (%s)", coin)
        logger.info("=" * 50)
        logger.info("  총 수량: %.6f %s", total_qty, coin)
        logger.info("  총 비용: %.2f USDT", total_cost)
        logger.info("  평균 단가: $%.2f", avg_price)
        logger.info("  진입 횟수: %s회", len(self.positions["entries"]))

        targets = self.get_bithumb_targets(usdt_krw_rate)
        if not targets:
            return

        logger.info("\n💰 빗썸 판매 목표가 (USDT ₩%s 기준)", f"{usdt_krw_rate:,.0f}")
        logger.info("=" * 50)
        logger.info("  손익분기점: ₩%s", f"{targets['breakeven_krw']:,.0f}")
        logger.info("  +1%% 수익: ₩%s", f"{targets['target_1_percent']:,.0f}")
        logger.info("  +3%% 수익: ₩%s", f"{targets['target_3_percent']:,.0f}")
        logger.info("  +5%% 수익: ₩%s", f"{targets['target_5_percent']:,.0f}")
        logger.info("  +10%% 수익: ₩%s", f"{targets['target_10_percent']:,.0f}")

        logger.info("\n💵 예상 수익 (5% 김프 기준)")
        logger.info("=" * 50)
        revenue_krw = targets["target_5_percent"] * total_qty
        cost_krw = targets["breakeven_krw"] * total_qty
        profit_krw = revenue_krw - cost_krw
        profit_usdt = profit_krw / usdt_krw_rate

        logger.info("  매도 금액: ₩%s", f"{revenue_krw:,.0f}")
        logger.info("  투자 금액: ₩%s", f"{cost_krw:,.0f}")
        logger.info("  순수익: ₩%s (%s USDT)", f"{profit_krw:,.0f}", f"{profit_usdt:,.2f}")

    def get_open_pairs(self) -> Dict[Tuple[str, str], Dict[str, float]]:
        """Aggregates remaining quantities and costs per (spot, perp) pair."""
        pairs: Dict[Tuple[str, str], Dict[str, float]] = {}
        for entry in self.positions.get("entries", []):
            remaining = entry.get("remaining_quantity", entry.get("quantity", 0.0))
            if remaining <= 0:
                continue
            key = (entry["spot_exchange"], entry["perp_exchange"])
            spot_fee = entry.get("spot_fee", 0.0)
            perp_fee = entry.get("perp_fee", 0.0)
            spot_unit = entry["spot_price"] * (1 + spot_fee)
            perp_unit = entry["perp_price"] * (1 - perp_fee)
            data = pairs.setdefault(key, {"quantity": 0.0, "spot_cost": 0.0, "perp_proceed": 0.0})
            data["quantity"] += remaining
            data["spot_cost"] += spot_unit * remaining
            data["perp_proceed"] += perp_unit * remaining
        return pairs

    def reduce_pair_position(self, spot_exchange: str, perp_exchange: str, quantity: float) -> float:
        """Reduces exposure for the specified pair in FIFO order.

        Args:
            spot_exchange: Spot exchange name.
            perp_exchange: Perpetual exchange name.
            quantity: Base amount to close.

        Returns:
            Actual reduced quantity after matching entries.
        """
        remaining_to_reduce = quantity
        reduced_total = 0.0
        for entry in self.positions.get("entries", []):
            if remaining_to_reduce <= 0:
                break
            if entry["spot_exchange"] != spot_exchange or entry["perp_exchange"] != perp_exchange:
                continue
            entry_remain = entry.get("remaining_quantity", entry["quantity"])
            if entry_remain <= 0:
                continue
            reduce_amt = min(entry_remain, remaining_to_reduce)
            spot_fee = entry.get("spot_fee", 0.0)
            perp_fee = entry.get("perp_fee", 0.0)
            spot_unit = entry["spot_price"] * (1 + spot_fee)
            perp_unit = entry["perp_price"] * (1 - perp_fee)

            entry["remaining_quantity"] = entry_remain - reduce_amt
            remaining_to_reduce -= reduce_amt
            reduced_total += reduce_amt

            self.positions["total_quantity"] -= reduce_amt
            self.positions["total_cost_usdt"] -= entry["spot_price"] * reduce_amt
            self.positions["total_spot_cost"] -= spot_unit * reduce_amt
            self.positions["total_perp_proceeds"] -= perp_unit * reduce_amt

        self._recompute_totals()
        self.save_positions()
        return reduced_total

    def _recompute_totals(self) -> None:
        """Recalculates aggregate metrics from stored entries."""
        total_quantity = 0.0
        total_cost_usdt = 0.0
        total_spot_cost = 0.0
        total_perp_proceeds = 0.0

        for entry in self.positions.get("entries", []):
            remaining = entry.get("remaining_quantity", entry.get("quantity", 0.0))
            if remaining <= 0:
                continue
            spot_fee = entry.get("spot_fee", 0.0)
            perp_fee = entry.get("perp_fee", 0.0)
            spot_unit = entry["spot_price"] * (1 + spot_fee)
            perp_unit = entry["perp_price"] * (1 - perp_fee)

            total_quantity += remaining
            total_cost_usdt += entry["spot_price"] * remaining
            total_spot_cost += spot_unit * remaining
            total_perp_proceeds += perp_unit * remaining

        self.positions["total_quantity"] = total_quantity
        self.positions["total_cost_usdt"] = total_cost_usdt
        self.positions["total_spot_cost"] = total_spot_cost
        self.positions["total_perp_proceeds"] = total_perp_proceeds

        if total_quantity > 0:
            self.positions["average_price"] = total_cost_usdt / total_quantity
            self.positions["average_spot_cost"] = total_spot_cost / total_quantity
            self.positions["average_perp_proceed"] = total_perp_proceeds / total_quantity
        else:
            self.positions["average_price"] = 0.0
            self.positions["average_spot_cost"] = 0.0
            self.positions["average_perp_proceed"] = 0.0

    def _ensure_compatibility(self) -> None:
        """Ensures new fields exist on legacy position files."""
        defaults = {
            "total_spot_cost": 0.0,
            "total_perp_proceeds": 0.0,
            "average_spot_cost": 0.0,
            "average_perp_proceed": 0.0,
        }
        for key, value in defaults.items():
            if key not in self.positions:
                self.positions[key] = value
        for entry in self.positions.get("entries", []):
            if "remaining_quantity" not in entry:
                entry["remaining_quantity"] = entry.get("quantity", 0.0)
            entry.setdefault("spot_fee", self._get_fee(entry.get("spot_exchange", ""), "spot"))
            entry.setdefault("perp_fee", self._get_fee(entry.get("perp_exchange", ""), "futures"))

    def _initial_state(self, coin: Optional[str] = None) -> PositionState:
        """Returns a blank position structure for the given coin."""
        return {
            "entries": [],
            "total_quantity": 0.0,
            "total_cost_usdt": 0.0,
            "average_price": 0.0,
            "total_spot_cost": 0.0,
            "total_perp_proceeds": 0.0,
            "average_spot_cost": 0.0,
            "average_perp_proceed": 0.0,
            "current_coin": coin,
        }

    def _get_fee(self, exchange: str, market_type: str) -> float:
        """Safely retrieves the taker fee for the given venue and market."""
        return EXCHANGE_FEES.get(exchange, {}).get(market_type, {}).get("taker", 0.0)
