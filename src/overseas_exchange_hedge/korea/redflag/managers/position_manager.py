"""포지션 관리 모듈."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """포지션 정보를 담는 클래스."""

    symbol: str
    value_usd: float = 0.0
    spot_amount: float = 0.0
    futures_contracts: int = 0
    entry_price: float = 0.0


class PositionManager:
    """포지션을 관리하는 클래스"""

    def __init__(self):
        self.positions: Dict[str, Position] = {}

    def get_position(self, symbol: str) -> Position:
        """심볼의 포지션을 조회하거나 새로 생성한다.

        Args:
            symbol: 심볼.

        Returns:
            Position 인스턴스.
        """
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol=symbol)
        return self.positions[symbol]

    def update_position(self, symbol: str, value_change: float) -> None:
        """포지션 USD 값을 업데이트한다."""
        position = self.get_position(symbol)
        position.value_usd += value_change
        logger.info(f"{symbol} 포지션 업데이트: ${position.value_usd:.2f}")

    def get_existing_positions(self, symbol: str, korean_exchange, futures_exchange) -> float:
        """기존 헤징 포지션을 조회한다.

        현물 잔고 기준으로 USD 가치를 계산한다.

        Args:
            symbol: 심볼.
            korean_exchange: 한국 거래소 객체.
            futures_exchange: 선물 거래소 객체.

        Returns:
            기존 포지션의 USD 가치.
        """
        try:
            # 한국 거래소 현물 잔고만 확인
            balance = korean_exchange.get_balance(symbol)
            if balance and balance.get("total", 0) > 0:
                korean_ticker = korean_exchange.get_ticker(f"{symbol}/KRW")
                if korean_ticker and "last" in korean_ticker:
                    krw_value = balance["total"] * korean_ticker["last"]

                    usdt_krw_ticker = korean_exchange.get_ticker("USDT/KRW")
                    if usdt_krw_ticker and "last" in usdt_krw_ticker:
                        usd_value = krw_value / usdt_krw_ticker["last"]
                        logger.info(f"기존 {symbol} 헤징 포지션: ${usd_value:.2f}")
                        return usd_value

            return 0.0

        except Exception as e:
            logger.error(f"{symbol} 기존 포지션 조회 실패: {e}")
            return 0.0

    def should_build_position(self, symbol: str, premium: float, max_position_usd: float) -> bool:
        """포지션 구축 여부를 판단한다."""
        position = self.get_position(symbol)

        # 프리미엄이 0% 이하이고 최대 포지션에 도달하지 않았을 때
        return premium <= 0 and position.value_usd < max_position_usd

    def get_position_increment(self, symbol: str, max_position_usd: float, increment_usd: float) -> float:
        """포지션 증가 크기를 계산한다."""
        position = self.get_position(symbol)
        remaining = max_position_usd - position.value_usd
        return min(increment_usd, remaining)

    def remove_position(self, symbol: str) -> None:
        """포지션을 제거한다."""
        if symbol in self.positions:
            del self.positions[symbol]
            logger.info(f"{symbol} 포지션 제거됨")
