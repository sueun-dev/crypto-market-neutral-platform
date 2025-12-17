"""주문 실행 모듈."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class OrderExecutor:
    """주문 실행을 담당하는 클래스"""

    def __init__(self, korean_exchange, futures_exchange):
        self.korean_exchange = korean_exchange
        self.futures_exchange = futures_exchange

    def execute_hedge_position(self, symbol: str, amount_usd: float) -> bool:
        """
        헤지 포지션 실행 (현물 매수 + 선물 숏)

        Args:
            symbol: 심볼
            amount_usd: USD 금액

        Returns:
            성공 여부
        """
        try:
            # 선물 레버리지 1배 고정 (롱 진입 방지 안전장치)
            if hasattr(self.futures_exchange, "set_leverage"):
                leverage_symbol = f"{symbol}/USDT:USDT"
                try:
                    self.futures_exchange.set_leverage(leverage_symbol, 1)
                except Exception as e:
                    logger.warning(f"{symbol} 레버리지 설정 실패 (무시): {e}")

            # 가격 정보 조회
            prices = self._get_prices(symbol)
            if not prices:
                return False

            krw_ask_price, futures_bid_price, usdt_krw_rate = prices

            # 수량 계산
            quantity = amount_usd / futures_bid_price

            # 빗썸은 8자리 반올림
            if self.korean_exchange.exchange_id.lower() == "bithumb":
                quantity = round(quantity, 8)

            # KRW 금액 계산
            krw_amount = quantity * krw_ask_price
            actual_usd_value = krw_amount / usdt_krw_rate

            logger.info(f"주문 계산: {quantity:.4f} {symbol}, KRW: {krw_amount:,.0f}, USD: ${actual_usd_value:.2f}")

            # 잔고 확인
            if not self._check_balances(krw_amount, amount_usd):
                return False

            # 선물 수량 계산 (GateIO는 계약 단위)
            futures_quantity = self._calculate_futures_quantity(symbol, quantity)
            if futures_quantity is None:
                return False

            # 동시 주문 실행
            success = self._execute_concurrent_orders(symbol, quantity, futures_quantity, "open")

            if success:
                logger.info(f"헤지 포지션 실행 성공: {quantity:.4f} {symbol} (포지션 가치: ${amount_usd:.2f})")

            return success

        except Exception as e:
            logger.error(f"헤지 포지션 실행 실패: {e}")
            return False

    def close_position_percentage(self, symbol: str, percentage: float, position_value_usd: float) -> bool:
        """
        포지션의 일정 비율 청산

        Args:
            symbol: 심볼
            percentage: 청산 비율 (%)
            position_value_usd: 현재 포지션 가치

        Returns:
            성공 여부
        """
        try:
            if not 0 < percentage <= 100:
                logger.error(f"잘못된 비율: {percentage}%")
                return False

            # 실제 보유 수량 확인
            spot_balance = self.korean_exchange.get_balance(symbol)
            if not spot_balance:
                logger.error(f"{symbol} 잔고 조회 실패")
                return False

            actual_spot_quantity = spot_balance["free"]
            logger.info(f"실제 {symbol} 보유량: {actual_spot_quantity:.8f}")

            # 청산할 USD 금액 계산
            close_amount_usd = position_value_usd * (percentage / 100)

            # 현재 가격으로 이상적인 수량 계산
            futures_ticker = self.futures_exchange.get_ticker(f"{symbol}/USDT:USDT")
            if not futures_ticker or "bid" not in futures_ticker or "ask" not in futures_ticker:
                return False

            mid_price = (futures_ticker["bid"] + futures_ticker["ask"]) / 2
            ideal_quantity = close_amount_usd / mid_price

            # 실제 청산할 수량 결정 (보유량과 이상적인 수량 중 작은 값)
            if percentage >= 100:
                # 100% 청산 시 모든 보유량 청산
                quantity = actual_spot_quantity
                logger.info(f"전체 청산: {quantity:.8f} {symbol}")
            else:
                # 부분 청산 시 계산된 수량과 보유량 중 작은 값 사용
                quantity = min(ideal_quantity, actual_spot_quantity)

            # 빗썸은 8자리 반올림
            if self.korean_exchange.exchange_id.lower() == "bithumb":
                quantity = round(quantity, 8)

            # 수량이 너무 작으면 중단
            if quantity < 0.00000001:
                logger.warning(f"청산할 수량이 너무 작음: {quantity:.8f} {symbol}")
                return False

            # 선물 포지션 확인 및 수량 조정
            futures_positions = self.futures_exchange.get_positions()
            futures_position = None
            for pos in futures_positions:
                if pos["symbol"] == f"{symbol}/USDT:USDT":
                    futures_position = pos
                    break

            if futures_position:
                # 실제 선물 포지션 계약 수
                actual_futures_contracts = futures_position["contracts"]

                # 계산된 선물 수량
                calculated_futures_quantity = self._calculate_futures_quantity(symbol, quantity)
                if calculated_futures_quantity is None:
                    return False

                # 실제 청산할 선물 계약 수 (보유 계약과 계산된 계약 중 작은 값)
                if percentage >= 100:
                    futures_quantity = actual_futures_contracts
                else:
                    futures_quantity = min(calculated_futures_quantity, actual_futures_contracts)

                logger.info(
                    "선물 포지션: %s contracts, 청산 예정: %s contracts",
                    actual_futures_contracts,
                    futures_quantity,
                )
            else:
                # 선물 포지션이 없으면 계산된 수량 사용
                futures_quantity = self._calculate_futures_quantity(symbol, quantity)
                if futures_quantity is None:
                    return False

            logger.info(
                f"{percentage}% 포지션 청산: {quantity:.8f} {symbol} 현물, "
                f"{futures_quantity:.8f} 선물 (${close_amount_usd:.2f})"
            )

            # 동시 주문 실행
            success = self._execute_concurrent_orders(symbol, quantity, futures_quantity, "close")

            if success:
                logger.info(f"{percentage}% 포지션 청산 성공: {quantity:.4f} {symbol}")

            return success

        except Exception as e:
            logger.error(f"포지션 청산 실패: {e}")
            return False

    def _get_prices(self, symbol: str) -> Optional[Tuple[float, float, float]]:
        """현재 가격 정보를 조회한다.

        Args:
            symbol: 조회할 심볼.

        Returns:
            (KRW 매수호가, 선물 BID, USDT/KRW 환율) 튜플 또는 None.
        """
        try:
            # 한국 거래소 가격
            korean_ticker = self.korean_exchange.get_ticker(f"{symbol}/KRW")
            if not korean_ticker or "last" not in korean_ticker:
                logger.error("한국 거래소 가격 조회 실패")
                return None

            if korean_ticker.get("ask") is None:
                logger.error("한국 거래소 ask 가격 없음")
                return None
            krw_ask_price = korean_ticker["ask"]

            # 선물 거래소 가격
            futures_ticker = self.futures_exchange.get_ticker(f"{symbol}/USDT:USDT")
            if not futures_ticker or "bid" not in futures_ticker:
                logger.error("선물 거래소 bid 가격 조회 실패")
                return None

            futures_bid_price = futures_ticker["bid"]  # 숏 진입 시 실제 체결가

            # USDT/KRW 환율
            usdt_krw_ticker = self.korean_exchange.get_ticker("USDT/KRW")
            if not usdt_krw_ticker or "last" not in usdt_krw_ticker:
                logger.error("USDT/KRW 환율 조회 실패")
                return None
            usdt_krw_rate = usdt_krw_ticker["last"]

            return krw_ask_price, futures_bid_price, usdt_krw_rate

        except Exception as e:
            logger.error(f"가격 정보 조회 실패: {e}")
            return None

    def _calculate_futures_quantity(self, symbol: str, quantity: float) -> Optional[float]:
        """선물 주문 수량을 계산한다 (GateIO는 계약 단위를 사용).

        Args:
            symbol: 심볼.
            quantity: 베이스 수량.

        Returns:
            선물 주문에 사용할 수량(또는 계약 수), 실패 시 None.
        """
        try:
            if self.futures_exchange.exchange_id.lower() == "gateio":
                markets = self.futures_exchange.get_markets()
                futures_symbol = f"{symbol}/USDT:USDT"

                if futures_symbol in markets:
                    contract_size = markets[futures_symbol].get("contract_size")
                    if not contract_size:
                        logger.error(f"{symbol} contract_size 정보 없음")
                        return None

                    # Gate.io는 소수점 계약 지원 - 정확한 수량 계산
                    contracts = quantity / contract_size

                    # 최소 1 USD 확인 (BTC $70,000 기준 약 0.143 contracts)
                    if contracts < 1:
                        logger.error(f"수량이 너무 작음: {quantity:.4f} {symbol} = {contracts:.4f} contracts (최소: 1)")
                        return None

                    logger.info(
                        f"GateIO 선물: {quantity:.8f} {symbol} = {contracts:.4f} contracts (계약 크기: {contract_size})"
                    )
                    return contracts

            return quantity

        except Exception as e:
            logger.error(f"선물 수량 계산 실패: {e}")
            return None

    def _check_minimum_order_size(self, actual_usd: float, target_usd: float) -> bool:
        """최소 주문 크기를 만족하는지 확인한다."""
        from ..config.settings import settings

        korean_min = settings.MIN_ORDER_SIZES.get(self.korean_exchange.exchange_id.lower(), 0)
        futures_min = settings.MIN_ORDER_SIZES.get(self.futures_exchange.exchange_id.lower(), 0)

        if actual_usd < korean_min:
            logger.error(f"한국 거래소 최소 주문 크기 미달: ${actual_usd:.2f} < ${korean_min}")
            return False

        if target_usd < futures_min:
            logger.error(f"선물 거래소 최소 주문 크기 미달: ${target_usd:.2f} < ${futures_min}")
            return False

        return True

    def _check_balances(self, krw_amount: float, usd_amount: float) -> bool:
        """필요한 잔고가 충분한지 확인한다."""
        try:
            # KRW 잔고 확인
            krw_balance = self.korean_exchange.get_balance("KRW")
            if krw_balance and krw_balance.get("free", 0) < krw_amount:
                logger.error(f"KRW 잔고 부족: {krw_balance.get('free', 0):,.0f} < {krw_amount:,.0f}")
                return False

            # USDT 잔고 확인
            usdt_balance = self.futures_exchange.get_balance("USDT")
            if usdt_balance and usdt_balance.get("free", 0) < usd_amount:
                logger.error(f"USDT 잔고 부족: ${usdt_balance.get('free', 0):.2f} < ${usd_amount:.2f}")
                return False

            return True

        except Exception as e:
            logger.warning(f"잔고 확인 실패: {e}. 주의하여 진행.")
            return True

    def _execute_concurrent_orders(
        self, symbol: str, spot_quantity: float, futures_quantity: float, operation: str
    ) -> bool:
        """현물과 선물 주문을 동시에 실행한다."""
        with ThreadPoolExecutor(max_workers=2) as executor:
            if operation == "open":
                # 포지션 열기: 현물 매수 + 선물 숏
                # Bithumb와 Upbit 모두 매수 시 KRW 금액을 받음
                if self.korean_exchange.exchange_id.lower() in ["bithumb", "upbit"]:
                    # 현재 가격으로 KRW 금액 계산
                    ticker = self.korean_exchange.get_ticker(f"{symbol}/KRW")
                    krw_amount = spot_quantity * ticker["ask"]
                    spot_future = executor.submit(
                        self.korean_exchange.create_market_order, f"{symbol}/KRW", "buy", krw_amount
                    )
                else:
                    # 다른 거래소는 수량을 받음
                    spot_future = executor.submit(
                        self.korean_exchange.create_market_order, f"{symbol}/KRW", "buy", spot_quantity
                    )
                # GateIO에게 이미 계약 수로 변환되었음을 알림
                if self.futures_exchange.exchange_id.lower() == "gateio":
                    futures_params = {"from_order_executor": True}
                else:
                    futures_params = None
                futures_future = executor.submit(
                    self.futures_exchange.create_market_order,
                    f"{symbol}/USDT:USDT",
                    "sell",
                    futures_quantity,
                    futures_params,
                )
            else:
                # 포지션 닫기: 현물 매도 + 선물 숏 커버 (reduce_only 필수)
                spot_future = executor.submit(
                    self.korean_exchange.create_market_order, f"{symbol}/KRW", "sell", spot_quantity
                )
                # GateIO에게 이미 계약 수로 변환되었음을 알림
                if self.futures_exchange.exchange_id.lower() == "gateio":
                    futures_params = {"reduce_only": True, "from_order_executor": True}
                else:
                    futures_params = {"reduce_only": True}
                futures_future = executor.submit(
                    self.futures_exchange.create_market_order,
                    f"{symbol}/USDT:USDT",
                    "buy",
                    futures_quantity,
                    futures_params,  # 절대 롱 포지션 생성 방지
                )

            try:
                spot_result = spot_future.result(timeout=30)
                futures_result = futures_future.result(timeout=30)

                if not spot_result or not futures_result:
                    logger.error("하나 이상의 주문 실패")
                    # 부분 실행 복구 시도
                    self._handle_partial_execution(
                        symbol, spot_quantity, futures_quantity, spot_result, futures_result, operation
                    )
                    return False

                return True

            except FuturesTimeoutError:
                logger.error("주문 실행 타임아웃")
                spot_future.cancel()
                futures_future.cancel()
                return False

    def _handle_partial_execution(
        self,
        symbol: str,
        spot_quantity: float,
        futures_quantity: float,
        spot_result: Optional[Dict],
        futures_result: Optional[Dict],
        operation: str,
    ) -> None:
        """부분 실행 처리"""
        try:
            if operation == "open":
                if spot_result and not futures_result:
                    logger.warning("선물 주문 실패, 현물 주문 되돌리기")
                    # 매수한 현물을 되팔기 - 매도는 수량 기반
                    self.korean_exchange.create_market_order(f"{symbol}/KRW", "sell", spot_quantity)
                elif futures_result and not spot_result:
                    logger.warning("현물 주문 실패, 선물 포지션 닫기")
                    self.futures_exchange.create_market_order(
                        f"{symbol}/USDT:USDT", "buy", futures_quantity, {"reduce_only": True}
                    )
            else:
                logger.critical(f"포지션 청산 부분 실행! {symbol} 수동 확인 필요")

        except Exception as e:
            logger.error(f"부분 실행 복구 실패: {e}")
