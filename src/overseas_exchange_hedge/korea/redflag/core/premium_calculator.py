"""김치 프리미엄 계산 모듈."""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class PremiumCalculator:
    """김치 프리미엄을 계산하는 클래스"""

    def __init__(self, korean_exchange, futures_exchange):
        self.korean_exchange = korean_exchange
        self.futures_exchange = futures_exchange

    def calculate(self, symbol: str) -> Optional[float]:
        """
        김치 프리미엄 계산

        Args:
            symbol: 심볼 (예: 'XRP')

        Returns:
            프리미엄 퍼센트 또는 None
        """
        try:
            # 한국 거래소 가격 조회
            korean_ticker = self.korean_exchange.get_ticker(f"{symbol}/KRW")
            if not korean_ticker or "last" not in korean_ticker:
                logger.error(f"한국 거래소 {symbol} 가격 조회 실패")
                return None

            # 매수 가격 확인 (ask 가격이 없으면 중단)
            if korean_ticker.get("ask") is None:
                logger.error(f"{symbol} 한국 거래소 ask 가격 없음")
                return None
            krw_ask_price = korean_ticker["ask"]

            # USDT/KRW 환율 조회
            usdt_krw_price = self._get_usdt_krw_rate()
            if not usdt_krw_price:
                return None

            # 선물 거래소 가격 조회
            futures_ticker = self.futures_exchange.get_ticker(f"{symbol}/USDT:USDT")
            if not futures_ticker or "last" not in futures_ticker:
                logger.error(f"선물 거래소 {symbol} 가격 조회 실패")
                return None

            # 매도 가격 확인 (bid 가격이 없으면 중단)
            if futures_ticker.get("bid") is None:
                logger.error(f"{symbol} 선물 거래소 bid 가격 없음")
                return None
            usdt_bid_price = futures_ticker["bid"]

            # 프리미엄 계산
            # 한국에서 사는 가격을 USD로 변환
            usd_equivalent = krw_ask_price / usdt_krw_price
            # 프리미엄 = (한국 USD 가격 / 해외 USD 가격 - 1) * 100
            premium = ((usd_equivalent / usdt_bid_price) - 1) * 100

            logger.info(
                f"{symbol} 김치 프리미엄: {premium:.2f}% "
                f"(KRW: {krw_ask_price:,.0f}, USDT: {usdt_bid_price:.2f}, "
                f"USDT/KRW: {usdt_krw_price:,.0f})"
            )

            return premium

        except Exception as e:
            logger.error(f"{symbol} 프리미엄 계산 실패: {e}")
            return None

    def _get_usdt_krw_rate(self) -> Optional[float]:
        """USDT/KRW 환율을 조회한다.

        Returns:
            환율 값 또는 None.
        """
        try:
            usdt_krw_ticker = self.korean_exchange.get_ticker("USDT/KRW")

            if not usdt_krw_ticker:
                logger.error("USDT/KRW 티커 조회 실패")
                return None

            if "last" not in usdt_krw_ticker:
                logger.error("USDT/KRW last 가격 없음")
                return None

            return usdt_krw_ticker["last"]

        except Exception as e:
            logger.error(f"USDT/KRW 환율 조회 실패: {e}")
            return None
