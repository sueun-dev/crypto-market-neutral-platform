"""
헤징 봇 핵심 로직
"""
import logging
from typing import List, Dict, Set, Tuple
from datetime import datetime

from src.config import settings
from src.core.premium_calculator import PremiumCalculator
from src.core.order_executor import OrderExecutor
from src.core.position_balancer import PositionBalancer
from src.managers.position_manager import PositionManager
from src.managers.timer_manager import TimerManager

logger = logging.getLogger(__name__)


class HedgeBot:
    """레드플래그 헤징 봇"""
    
    def __init__(self, korean_exchange, futures_exchange):
        # Validate exchanges are not None
        if korean_exchange is None or futures_exchange is None:
            raise ValueError("Both korean_exchange and futures_exchange must be provided")
        
        self.korean_exchange = korean_exchange
        self.futures_exchange = futures_exchange
        
        # 심볼 리스트
        self.symbols: List[str] = []
        
        # 관리자 초기화
        self.position_manager = PositionManager()
        self.timer_manager = TimerManager()
        self.premium_calculator = PremiumCalculator(korean_exchange, futures_exchange)
        self.order_executor = OrderExecutor(korean_exchange, futures_exchange)
        self.position_balancer = PositionBalancer(
            self.position_manager, 
            self.order_executor,
            korean_exchange,
            futures_exchange
        )
        
        # 실패 추적
        self.failed_attempts: Dict[str, int] = {}
        
        # 진행중인 주문 추적 (중복 방지)
        self.orders_in_progress: Set[Tuple[str, str]] = set()
    
    def add_symbol(self, symbol: str) -> bool:
        """심볼 추가 및 검증"""
        try:
            # 한국 거래소 확인
            korean_ticker = self.korean_exchange.get_ticker(f"{symbol}/KRW")
            if not korean_ticker:
                logger.error(f"{symbol}/KRW를 {self.korean_exchange.exchange_id}에서 찾을 수 없음")
                return False
            
            # 선물 거래소 확인
            futures_ticker = self.futures_exchange.get_ticker(f"{symbol}/USDT:USDT")
            if not futures_ticker:
                logger.error(f"{symbol}/USDT:USDT를 {self.futures_exchange.exchange_id}에서 찾을 수 없음")
                return False
            
            logger.info(f"거래 페어 확인됨: {symbol}/KRW와 {symbol}/USDT:USDT")
            
            # 기존 포지션 확인
            existing_value = self.position_manager.get_existing_positions(
                symbol, self.korean_exchange, self.futures_exchange
            )
            
            # 포지션 설정
            position = self.position_manager.get_position(symbol)
            position.value_usd = existing_value
            
            if existing_value > 0:
                logger.info(f"📊 기존 {symbol} 포지션 발견: ${existing_value:.2f}")
                
                # 초기 균형 체크 및 자동 리밸런싱
                balance = self.position_balancer.check_position_balance(symbol)
                if balance and balance.needs_rebalancing:
                    logger.warning(
                        f"⚠️ {symbol} 초기 헤지 불균형 감지! "
                        f"갭: ${balance.gap_usd:.2f}"
                    )
                    logger.info(f"🔄 자동 리밸런싱 시작...")
                    if self.position_balancer.rebalance_position(symbol):
                        logger.info(f"✅ {symbol} 초기 리밸런싱 완료")
                    else:
                        logger.error(f"❌ {symbol} 초기 리밸런싱 실패 - 수동 확인 필요")
            
            # 타이머 초기화
            self.timer_manager.initialize_symbol(symbol)
            
            # 실패 카운터 초기화
            self.failed_attempts[symbol] = 0
            
            # 심볼 추가
            self.symbols.append(symbol)
            
            return True
            
        except Exception as e:
            logger.error(f"{symbol} 추가 실패: {e}")
            return False
    
    def process_symbol(self, symbol: str) -> None:
        """심볼 처리"""
        try:
            # 중복 주문 방지
            if self._is_order_in_progress(symbol):
                return
            
            # 프리미엄 계산
            premium = self.premium_calculator.calculate(symbol)
            if premium is None:
                return
            
            # 현재 포지션
            position = self.position_manager.get_position(symbol)
            
            # 상태 출력
            self._print_status(symbol, premium, position.value_usd)
            
            # 포지션 구축 확인
            if self._should_build_position(premium, position.value_usd):
                self._build_position(symbol)
            
            # 이익 실현 확인
            elif position.value_usd > 0:
                self._check_profit_taking(symbol, premium, position.value_usd)
        
        except Exception as e:
            logger.error(f"{symbol} 처리 중 오류: {e}")
    
    def _should_build_position(self, premium: float, position_value: float) -> bool:
        """포지션 구축 여부 판단"""
        return (
            premium <= settings.BUILD_POSITION_PREMIUM and
            position_value < settings.MAX_POSITION_USD
        )
    
    def _build_position(self, symbol: str) -> None:
        """포지션 구축"""
        increment = self.position_manager.get_position_increment(
            symbol, settings.MAX_POSITION_USD, settings.POSITION_INCREMENT_USD
        )
            
        # 최소 주문 크기 확인 (거래소 제한 여유롭게 고려)
        if increment < 10.0:  # $10 미만이면 건너뛰기
            logger.info(f"{symbol} 주문 크기 너무 작음: ${increment:.2f} < $10")
            return
        
        order_key = (symbol, 'hedge')
        self.orders_in_progress.add(order_key)
        
        try:
            success = self.order_executor.execute_hedge_position(symbol, increment)
            
            if success:
                self.position_manager.update_position(symbol, increment)
                logger.info(f"📈 {symbol} 포지션 구축: ${increment:.2f}")
                self.failed_attempts[symbol] = 0
                
                # 포지션 균형 체크 및 리밸런싱
                balance = self.position_balancer.check_position_balance(symbol)
                if balance and balance.needs_rebalancing:
                    logger.info(f"🔄 {symbol} 포지션 리밸런싱 필요")
                    self.position_balancer.rebalance_position(symbol)
            else:
                self._handle_failure(symbol)
                
        finally:
            self.orders_in_progress.discard(order_key)
    
    def _check_profit_taking(self, symbol: str, premium: float, position_value: float) -> None:
        """이익 실현 확인"""
        # 실패 횟수 확인
        if self.failed_attempts.get(symbol, 0) >= settings.MAX_FAILED_ATTEMPTS:
            logger.warning(f"⚠️ {symbol}: 여러 번 실패로 건너뜀. 수동 확인 필요.")
            return
        
        # 이익 실현 단계 확인
        result = self.timer_manager.check_profit_taking(
            symbol, premium, settings.PROFIT_STAGES
        )
        
        if result:
            target_premium, close_percentage = result
            
            if close_percentage == 100:
                self._close_all_position(symbol, premium)
            else:
                self._close_partial_position(symbol, close_percentage, position_value, target_premium)
    
    def _close_all_position(self, symbol: str, premium: float) -> None:
        """전체 포지션 청산"""
        order_key = (symbol, 'close_100')
        self.orders_in_progress.add(order_key)
        
        try:
            position = self.position_manager.get_position(symbol)
            success = self.order_executor.close_position_percentage(
                symbol, 100, position.value_usd
            )
            
            if success:
                logger.info(f"🎯 {symbol} 전체 포지션 청산! 프리미엄: {premium:.2f}%")
                
                # 전체 청산시 균형 조정 불필요 - 포지션이 없음
                
                self._cleanup_symbol(symbol)
            else:
                logger.error(f"❌ {symbol} 전체 청산 실패. 다음 사이클에 재시도.")
                self._handle_failure(symbol)
                
        finally:
            self.orders_in_progress.discard(order_key)
    
    def _close_partial_position(
        self, symbol: str, close_percentage: float, 
        position_value: float, target_premium: float
    ) -> None:
        """부분 포지션 청산"""
        order_key = (symbol, f'close_{close_percentage}')
        self.orders_in_progress.add(order_key)
        
        try:
            # 타이머 먼저 설정 (중복 주문 방지)
            old_timer = self.timer_manager.reset_timer(symbol, target_premium)
            self.timer_manager.set_timer(symbol, target_premium)
            
            success = self.order_executor.close_position_percentage(
                symbol, close_percentage, position_value
            )
            
            if success:
                # 포지션 업데이트
                close_amount = position_value * (close_percentage / 100)
                self.position_manager.update_position(symbol, -close_amount)
                
                logger.info(f"💰 {symbol} {close_percentage}% 이익 실현!")
                
                # 부분 청산 후 균형 조정
                self.position_balancer.balance_after_close(symbol, close_percentage)
                
                self.failed_attempts[symbol] = 0
            else:
                # 실패시 타이머 복원
                if old_timer:
                    self.timer_manager.stage_timers[symbol][target_premium] = old_timer
                logger.error(f"❌ {symbol} {target_premium}% 이익 실패. 재시도.")
                self._handle_failure(symbol)
                
        finally:
            self.orders_in_progress.discard(order_key)
    
    def _cleanup_symbol(self, symbol: str) -> None:
        """심볼 정리"""
        self.symbols.remove(symbol)
        self.position_manager.remove_position(symbol)
        self.timer_manager.remove_symbol(symbol)
        
        if symbol in self.failed_attempts:
            del self.failed_attempts[symbol]
    
    def _handle_failure(self, symbol: str) -> None:
        """실패 처리"""
        self.failed_attempts[symbol] = self.failed_attempts.get(symbol, 0) + 1
        
        if self.failed_attempts[symbol] >= settings.MAX_FAILED_ATTEMPTS:
            logger.critical(f"{symbol} 다중 실패! 수동 확인 필요.")
    
    def _is_order_in_progress(self, symbol: str) -> bool:
        """주문 진행중 확인"""
        for order_key in self.orders_in_progress:
            if order_key[0] == symbol:
                logger.warning(f"{symbol} 주문이 이미 진행중")
                return True
        return False
    
    
    def _print_status(self, symbol: str, premium: float, position_value: float) -> None:
        """상태 출력"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logger.info(f"[{timestamp}] {symbol} 프리미엄: {premium:.2f}% | 포지션: ${position_value:.2f}")
    
    def run_cycle(self) -> bool:
        """한 사이클 실행"""
        try:
            # 모든 심볼 처리
            for symbol in self.symbols.copy():  # copy()로 안전하게 순회
                self.process_symbol(symbol)
            
            # 모든 심볼이 청산되었는지 확인
            return len(self.symbols) > 0
            
        except Exception as e:
            logger.error(f"사이클 실행 중 오류: {e}")
            return True  # 오류시에도 계속 실행