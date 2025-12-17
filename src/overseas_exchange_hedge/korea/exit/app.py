#!/usr/bin/env python3
"""Unified exit manager for kimchi-premium based unwinds."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Dict, List

from ...common.logging_utils import setup_logging
from ...common.paths import state_file
from ...overseas.exchange_manager import ExchangeManager
from ...overseas.position_tracker import PositionTracker
from .kimchi_premium import KimchiPremiumCalculator
from .korean_exchanges import KoreanExchangeManager

logger = logging.getLogger(__name__)


class UnifiedExitManager:
    """Coordinates Korean exchange exits and overseas hedge unwinds."""

    def __init__(self):
        logger.info("\n초기화 중...")
        self.exchange_manager = ExchangeManager()
        self.exchange_manager.initialize_exchanges()
        self.position_tracker = PositionTracker()
        self.korean_manager = KoreanExchangeManager()
        self.premium_calculator = KimchiPremiumCalculator(self.exchange_manager, self.korean_manager)
        self.state_path = state_file("exit_state.json", legacy_filename="exit_state.json")
        self.state = self.load_state()

    def load_state(self) -> Dict:
        """Loads persisted exit state from disk."""
        if self.state_path.exists():
            try:
                with self.state_path.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("⚠️ 상태 로드 실패: %s", e)
        return {
            "active_orders": {},  # {exchange: {coin: [orders]}}
            "completed_sales": [],
            "positions": {},  # 실제 포지션 정보
            "status": "idle",
        }

    def save_state(self):
        """Writes the current state to disk."""
        with self.state_path.open("w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2, default=str)

    def scan_futures_positions(self, coin: str) -> Dict:
        """Scans perpetual exchanges for open positions in the target coin.

        Args:
            coin: Target coin symbol.

        Returns:
            Mapping of exchange name to position metadata.
        """
        positions = {}

        logger.info("\n📊 %s 선물 포지션 스캔 중...", coin)

        for exchange_name in self.exchange_manager.exchanges.keys():
            if "perp" not in self.exchange_manager.exchanges[exchange_name]:
                continue

            try:
                ex = self.exchange_manager.exchanges[exchange_name]["perp"]
                perp_positions = ex.fetch_positions()

                for pos in perp_positions:
                    symbol = pos.get("symbol", "")
                    # USDC/USDT:USDT 또는 USDC/USD 형식 모두 체크
                    if coin.upper() in symbol.upper() and pos.get("contracts", 0) != 0:
                        positions[exchange_name] = {
                            "symbol": symbol,
                            "contracts": abs(pos.get("contracts", 0)),
                            "side": pos.get("side"),
                            "entry_price": pos.get("markPrice", 0),
                            "pnl": pos.get("unrealizedPnl", 0),
                        }
                        logger.info("  ✅ %s: %.4f %s 숏 포지션", exchange_name.upper(), abs(pos["contracts"]), coin)

            except Exception as e:
                logger.warning("  ⚠️ %s 조회 실패: %s", exchange_name.upper(), e)

        if not positions:
            logger.error("  ❌ %s 선물 포지션 없음", coin)
        else:
            self.state["positions"][coin] = positions
            self.save_state()

        return positions

    def check_spot_balances(self, coin: str, korean_exchanges: List[str]) -> Dict:
        """Checks Korean exchange spot balances for the given coin.

        Args:
            coin: Target coin symbol.
            korean_exchanges: Exchanges to inspect.

        Returns:
            Mapping of exchange name to available quantity.
        """
        balances = {}

        logger.info("\n💰 한국 거래소 %s 잔고 확인...", coin)

        for exchange in korean_exchanges:
            try:
                balance = self.korean_manager.check_balance(exchange, coin)
                if balance > 0.0001:
                    balances[exchange] = balance
                    current_price = self.korean_manager.get_current_price(exchange, coin)
                    value_krw = balance * current_price if current_price else 0
                    logger.info("  ✅ %s: %.6f %s (₩%s)", exchange.upper(), balance, coin, f"{value_krw:,.0f}")
                else:
                    logger.warning("  ⚠️ %s: 잔고 없음", exchange.upper())
            except Exception as e:
                logger.error("  ❌ %s 조회 실패: %s", exchange.upper(), e)

        return balances

    def calculate_best_premiums(self, coin: str, korean_exchanges: List[str]) -> Dict:
        """Calculates the best kimchi premium per Korean exchange.

        Args:
            coin: Target coin symbol.
            korean_exchanges: Exchanges to compare against overseas venues.

        Returns:
            Mapping of Korean exchange to best premium details.
        """
        premiums = {}

        for korean_ex in korean_exchanges:
            best_premium = 0.0
            best_overseas = None

            for overseas_ex in self.exchange_manager.exchanges.keys():
                try:
                    premium, details = self.premium_calculator.calculate_kimchi_premium(coin, korean_ex, overseas_ex)
                    if premium and premium > best_premium:
                        best_premium = premium
                        best_overseas = overseas_ex
                except Exception:
                    continue

            if best_overseas:
                premiums[korean_ex] = {"premium": best_premium, "overseas": best_overseas}

        return premiums

    def place_smart_orders(
        self, exchange: str, coin: str, balance: float, target_premium: float, current_premium: float
    ):
        """Places staged limit orders based on current premium levels.

        Args:
            exchange: Korean exchange identifier.
            coin: Target coin symbol.
            balance: Available base asset balance.
            target_premium: Premium threshold for fills.
            current_premium: Current observed premium.

        Returns:
            List of created order dictionaries.
        """
        try:
            current_price = self.korean_manager.get_current_price(exchange, coin)
            if not current_price:
                return []

            orders = []

            # 김프에 따른 가격 레벨 설정 - 50%씩 2개 주문
            if current_premium >= target_premium - 0.5:
                # 김프가 목표에 근접 - 타이트한 주문
                price_levels = [
                    (current_price * 1.001, balance * 0.5),  # 50%
                    (current_price * 1.002, balance * 0.5),  # 50%
                ]
            else:
                # 김프가 낮음 - 넓은 범위
                price_levels = [
                    (current_price * 1.005, balance * 0.5),  # 50%
                    (current_price * 1.010, balance * 0.5),  # 50%
                ]

            symbol = f"{coin}/KRW"

            for target_price, amount in price_levels:
                # 최소 주문 금액 체크 (5,000원)
                if target_price * amount < 5000:
                    continue

                try:
                    # 빗썸은 소수점 8자리까지만 허용
                    if exchange == "bithumb":
                        amount = round(amount, 8)
                    else:
                        amount = round(amount, 6)

                    order = self.korean_manager.exchanges[exchange].create_limit_sell_order(
                        symbol=symbol, amount=amount, price=int(target_price)
                    )

                    orders.append(
                        {
                            "id": order["id"],
                            "price": target_price,
                            "amount": amount,
                            "filled": 0,
                            "status": "open",
                            "timestamp": datetime.now().isoformat(),
                            "premium_at_placement": current_premium,
                        }
                    )

                    logger.info("    📝 주문: %.6f %s @ ₩%s", amount, coin, f"{target_price:,.0f}")

                except Exception as e:
                    logger.error("    ❌ 주문 실패: %s", e)

            return orders

        except Exception as e:
            logger.error("  ❌ 주문 배치 실패: %s", e)
            return []

    def check_and_process_fills(self, exchange: str, coin: str, orders: List[Dict]) -> float:
        """Checks open orders for fills and returns newly filled quantity.

        Args:
            exchange: Korean exchange identifier.
            coin: Target coin symbol.
            orders: Active order list to inspect and update.

        Returns:
            Newly filled base quantity.
        """
        symbol = f"{coin}/KRW"
        total_filled = 0

        for order in orders:
            if order.get("status") == "closed":
                continue

            try:
                status = self.korean_manager.check_order_status(exchange, order["id"], symbol)

                # None 체크 추가
                filled_amount = status.get("filled", 0) or 0
                prev_filled = order.get("filled", 0) or 0

                if filled_amount > prev_filled:
                    new_fill = filled_amount - prev_filled
                    order["filled"] = filled_amount
                    order["status"] = status.get("status", "open")
                    total_filled += new_fill

                    logger.info("  💰 체결: %.6f %s @ ₩%s", new_fill, coin, f"{order['price']:,.0f}")

                    # 체결 기록
                    self.state["completed_sales"].append(
                        {
                            "timestamp": datetime.now().isoformat(),
                            "exchange": exchange,
                            "coin": coin,
                            "amount": new_fill,
                            "price": order["price"],
                        }
                    )

            except Exception as e:
                logger.warning("  ⚠️ 주문 상태 확인 실패: %s", e)

        return total_filled

    def unwind_futures_positions(self, coin: str, amount: float):
        """Closes overseas perpetual shorts matching the sold spot amount.

        Args:
            coin: Target coin symbol.
            amount: Base amount already sold on Korean venues.
        """
        positions = self.state.get("positions", {}).get(coin, {})
        remaining = amount

        for exchange_name, pos_info in positions.items():
            if remaining <= 0:
                break

            if pos_info["contracts"] <= 0:
                continue

            try:
                ex = self.exchange_manager.exchanges[exchange_name]["perp"]
                symbol = pos_info["symbol"]

                # 청산할 수량 (최대 현재 포지션만큼)
                close_amount = min(remaining, pos_info["contracts"])

                # 숏 포지션 청산 (시장가 매수)
                ex.create_market_buy_order(symbol=symbol, amount=close_amount, params={"reduce_only": True})

                logger.info("  ✅ %s 숏 청산: %.6f %s", exchange_name.upper(), close_amount, coin)

                # 포지션 업데이트
                pos_info["contracts"] -= close_amount
                remaining -= close_amount

            except Exception as e:
                logger.error("  ❌ %s 청산 실패: %s", exchange_name.upper(), e)

        self.save_state()

    def cancel_orders(self, exchange: str, coin: str, orders: List[Dict]) -> int:
        """Cancels all open orders for the coin on a specific exchange.

        Args:
            exchange: Korean exchange identifier.
            coin: Target coin symbol.
            orders: Active orders to cancel.

        Returns:
            Number of successfully canceled orders.
        """
        symbol = f"{coin}/KRW"
        canceled_count = 0

        for order in orders:
            if order.get("status") == "open":
                try:
                    success = self.korean_manager.cancel_order(exchange, order["id"], symbol)
                    if success:
                        order["status"] = "canceled"
                        canceled_count += 1
                except Exception:
                    pass

        return canceled_count

    def run_smart_exit(
        self,
        coin: str,
        korean_exchanges: List[str],
        target_premium: float = 3.0,
        order_premium: float = 2.8,
        check_interval: int = 10,
    ):
        """Runs the smart exit workflow for the selected coin and exchanges.

        Args:
            coin: Target coin symbol.
            korean_exchanges: Korean exchanges to monitor (e.g., ["bithumb"]).
            target_premium: Premium threshold to allow fills.
            order_premium: Premium threshold to place limit orders.
            check_interval: Monitoring interval in seconds.
        """
        logger.info("\n" + "=" * 60)
        logger.info("🤖 SMART EXIT MANAGER")
        logger.info("=" * 60)
        logger.info("코인: %s", coin)
        logger.info("주문 배치: 김프 %s%% 이상", order_premium)
        logger.info("체결 허용: 김프 %s%% 이상", target_premium)
        logger.info("거래소: %s", ", ".join(ex.upper() for ex in korean_exchanges))
        logger.info("=" * 60)

        # 1. 선물 포지션 스캔
        futures_positions = self.scan_futures_positions(coin)
        if not futures_positions:
            logger.error("\n❌ 선물 포지션이 없습니다. 먼저 헤지 포지션을 만드세요.")
            return

        # 2. 한국 거래소 잔고 확인
        spot_balances = self.check_spot_balances(coin, korean_exchanges)
        if not spot_balances:
            logger.error("\n❌ 한국 거래소에 잔고가 없습니다.")
            return

        logger.info("\n✅ 모니터링 시작...")
        logger.info("Ctrl+C로 중단 가능\n")

        try:
            while True:
                current_time = datetime.now().strftime("%H:%M:%S")
                logger.info("\n[%s] 김프 체크...", current_time)

                # 각 한국 거래소별로 처리
                for korean_ex, balance in spot_balances.items():
                    if balance < 0.0001:
                        continue

                    # 현재 김프 계산
                    premiums = self.calculate_best_premiums(coin, [korean_ex])
                    if korean_ex not in premiums:
                        continue

                    premium_info = premiums[korean_ex]
                    current_premium = premium_info["premium"]
                    best_overseas = premium_info["overseas"]

                    logger.info("\n📊 %s", korean_ex.upper())
                    logger.info("  김프: %.2f%% (vs %s)", current_premium, best_overseas.upper())

                    # 주문 관리
                    if "active_orders" not in self.state:
                        self.state["active_orders"] = {}
                    if korean_ex not in self.state["active_orders"]:
                        self.state["active_orders"][korean_ex] = {}

                    active_orders = self.state["active_orders"][korean_ex].get(coin, [])

                    # 김프에 따른 주문 관리
                    if current_premium >= order_premium:
                        # 김프 충분 - 주문 배치/유지
                        if not active_orders or all(o["status"] != "open" for o in active_orders):
                            # 새 주문 배치
                            logger.info("  📝 주문 배치 중...")
                            new_orders = self.place_smart_orders(
                                korean_ex, coin, balance, target_premium, current_premium
                            )
                            if new_orders:
                                self.state["active_orders"][korean_ex][coin] = new_orders
                                self.save_state()
                        else:
                            # 체결 확인
                            filled_amount = self.check_and_process_fills(korean_ex, coin, active_orders)

                            if filled_amount > 0:
                                # 선물 포지션 청산
                                logger.info("  🔄 선물 헤지 청산 중...")
                                self.unwind_futures_positions(coin, filled_amount)

                                # 잔고 업데이트
                                spot_balances[korean_ex] -= filled_amount

                            if current_premium >= target_premium:
                                logger.info("  ✅ 체결 대기 중")
                            else:
                                logger.info("  ⏳ 주문 유지")

                    else:
                        # 김프 부족 - 주문 취소
                        if active_orders and any(o["status"] == "open" for o in active_orders):
                            logger.info("  🚫 김프 부족 - 주문 취소")
                            canceled = self.cancel_orders(korean_ex, coin, active_orders)
                            if canceled > 0:
                                logger.info("    %s개 주문 취소됨", canceled)
                                # 취소된 주문 정리
                                self.state["active_orders"][korean_ex][coin] = [
                                    o for o in active_orders if o["status"] != "canceled"
                                ]
                                self.save_state()
                        else:
                            logger.info("  ⏸️ 대기 중")

                # 완료 체크
                total_remaining = sum(spot_balances.values())
                if total_remaining < 0.0001:
                    logger.info("\n🎉 모든 포지션 청산 완료!")
                    self.state["status"] = "completed"
                    self.save_state()
                    break

                time.sleep(check_interval)

        except KeyboardInterrupt:
            logger.info("\n⏸️ 중단됨. 상태 저장 중...")
            self.save_state()
            logger.info("✅ 저장 완료")


def main() -> None:
    """CLI entrypoint for the unified exit manager."""
    setup_logging()
    logger.info("\n" + "=" * 60)
    logger.info("🚀 UNIFIED EXIT MANAGER")
    logger.info("=" * 60)
    logger.info("\n통합 청산 관리 시스템:")
    logger.info("• 실제 선물 포지션 자동 감지")
    logger.info("• 빗썸/업비트 지원")
    logger.info("• 김프 기반 스마트 주문 관리")
    logger.info("• 체결 시 자동 헤지 청산")

    # 코인 선택
    coin = input("\n청산할 코인 [BTC]: ").strip().upper() or "BTC"

    # 거래소 선택
    logger.info("\n한국 거래소 선택:")
    logger.info("1. 빗썸")
    logger.info("2. 업비트")
    logger.info("3. 둘 다")

    exchange_choice = input("\n선택 [3]: ").strip() or "3"

    korean_exchanges = []
    if exchange_choice == "1":
        korean_exchanges = ["bithumb"]
        exchange_str = "빗썸"
    elif exchange_choice == "2":
        korean_exchanges = ["upbit"]
        exchange_str = "업비트"
    else:
        korean_exchanges = ["bithumb", "upbit"]
        exchange_str = "빗썸 + 업비트"

    # 김프 설정
    order_premium = float(input("\n주문 배치 김프 (%) [2.8]: ").strip() or "2.8")
    target_premium = float(input("체결 허용 김프 (%) [3.0]: ").strip() or "3.0")

    # 확인
    logger.info("\n" + "=" * 40)
    logger.info("📋 설정 확인")
    logger.info("=" * 40)
    logger.info("코인: %s", coin)
    logger.info("주문 배치: 김프 %s%% 이상", order_premium)
    logger.info("체결 허용: 김프 %s%% 이상", target_premium)
    logger.info("거래소: %s", exchange_str)

    confirm = input("\n시작하시겠습니까? (y/n) [y]: ").strip().lower() or "y"
    if confirm != "y":
        logger.info("취소됨")
        return

    # 실행
    try:
        manager = UnifiedExitManager()
        manager.exchange_manager.load_markets_for_coin(coin)
        manager.run_smart_exit(coin, korean_exchanges, target_premium, order_premium)
    except KeyboardInterrupt:
        logger.info("\n⛔ 사용자에 의해 중단됨")
    except Exception as e:
        logger.exception("\n❌ 오류 발생: %s", e)


if __name__ == "__main__":
    main()
