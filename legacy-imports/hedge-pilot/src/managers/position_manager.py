"""
포지션 관리 모듈
"""
import logging
from typing import Dict
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """포지션 정보를 담는 클래스"""
    symbol: str
    value_usd: float = 0.0
    spot_amount: float = 0.0
    futures_contracts: int = 0
    entry_price: float = 0.0
    long_value: float = 0.0  # 롱 포지션 가치 (현물)
    short_value: float = 0.0  # 숏 포지션 가치 (선물)


class PositionManager:
    """포지션을 관리하는 클래스"""
    
    def __init__(self):
        self.positions: Dict[str, Position] = {}
    
    def get_position(self, symbol: str) -> Position:
        """심볼의 포지션 조회 (없으면 새로 생성)"""
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol=symbol)
        return self.positions[symbol]
    
    def update_position(self, symbol: str, value_change: float) -> None:
        """포지션 값 업데이트"""
        position = self.get_position(symbol)
        position.value_usd += value_change
        logger.info(f"{symbol} 포지션 업데이트: ${position.value_usd:.2f}")
    
    def get_existing_positions(self, symbol: str, korean_exchange, futures_exchange) -> float:
        """기존 헤징 포지션 조회 - 현물과 선물 모두 확인하여 균형 검증"""
        try:
            # 1. 한국 거래소 현물 포지션 조회
            spot_value_usd = 0.0
            balance = korean_exchange.get_balance(symbol)
            
            if balance and balance.get('total', 0) > 0:
                korean_ticker = korean_exchange.get_ticker(f"{symbol}/KRW")
                if korean_ticker and 'bid' in korean_ticker:  # bid 사용 (매도 시 가격)
                    krw_value = balance['total'] * korean_ticker['bid']
                    
                    usdt_krw_ticker = korean_exchange.get_ticker('USDT/KRW')
                    if usdt_krw_ticker and 'ask' in usdt_krw_ticker:  # ask 사용 (KRW->USD)
                        spot_value_usd = krw_value / usdt_krw_ticker['ask']
                        logger.info(f"현물 {symbol} 포지션: ${spot_value_usd:.2f}")
            
            # 2. 선물 거래소 숏 포지션 조회
            futures_value_usd = 0.0
            try:
                positions = futures_exchange.get_positions()
                futures_symbol = f"{symbol}/USDT:USDT"
                
                for pos in positions:
                    if pos.get('symbol') == futures_symbol and pos.get('side') == 'short':
                        futures_value_usd = abs(pos.get('notional', 0))
                        logger.info(f"선물 {symbol} 숏 포지션: ${futures_value_usd:.2f}")
                        break
            except Exception as e:
                logger.warning(f"선물 포지션 조회 실패: {e}")
            
            # 3. 포지션 균형 검증
            if spot_value_usd > 0 or futures_value_usd > 0:
                gap = abs(spot_value_usd - futures_value_usd)
                
                if gap > 10.0:  # $10 이상 차이
                    logger.warning(
                        f"⚠️ {symbol} 헤지 불균형 감지!\n"
                        f"  현물: ${spot_value_usd:.2f}\n"
                        f"  선물: ${futures_value_usd:.2f}\n"
                        f"  갭: ${gap:.2f}\n"
                        f"  → 리밸런싱 필요!"
                    )
                    
                    # 더 작은 값 반환 (안전한 쪽 선택)
                    return min(spot_value_usd, futures_value_usd)
                else:
                    logger.info(f"✅ {symbol} 헤지 균형 양호 (갭: ${gap:.2f})")
                    return (spot_value_usd + futures_value_usd) / 2  # 평균값 반환
            
            return 0.0
            
        except Exception as e:
            logger.error(f"{symbol} 기존 포지션 조회 실패: {e}")
            return 0.0
    
    def should_build_position(self, symbol: str, premium: float, max_position_usd: float) -> bool:
        """포지션을 구축해야 하는지 판단"""
        position = self.get_position(symbol)
        
        # 프리미엄이 0% 이하이고 최대 포지션에 도달하지 않았을 때
        return premium <= 0 and position.value_usd < max_position_usd
    
    def get_position_increment(self, symbol: str, max_position_usd: float, increment_usd: float) -> float:
        """포지션 증가 크기 계산"""
        position = self.get_position(symbol)
        remaining = max_position_usd - position.value_usd
        return min(increment_usd, remaining)
    
    def remove_position(self, symbol: str) -> None:
        """포지션 제거"""
        if symbol in self.positions:
            del self.positions[symbol]
            logger.info(f"{symbol} 포지션 제거됨")