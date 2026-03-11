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
            if not korean_ticker or 'ask' not in korean_ticker:
                logger.error(f"한국 거래소 {symbol} ask 가격 조회 실패")
                return None
            
            krw_ask_price = korean_ticker['ask']
            
            # USDT/KRW 환율 조회
            usdt_krw_price = self._get_usdt_krw_rate()
            if not usdt_krw_price:
                return None
            
            # 선물 거래소 가격 조회
            futures_ticker = self.futures_exchange.get_ticker(f"{symbol}/USDT:USDT")
            if not futures_ticker or 'bid' not in futures_ticker:
                logger.error(f"선물 거래소 {symbol} bid 가격 조회 실패")
                return None
            
            usdt_bid_price = futures_ticker['bid']
            
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
        """USDT/KRW 환율 조회 (ask 가격 사용)"""
        try:
            usdt_krw_ticker = self.korean_exchange.get_ticker('USDT/KRW')
            
            if not usdt_krw_ticker or 'ask' not in usdt_krw_ticker:
                logger.error("USDT/KRW ask 가격 조회 실패")
                return None
            
            return usdt_krw_ticker['ask']
            
        except Exception as e:
            logger.error(f"USDT/KRW 환율 조회 실패: {e}")
            return None