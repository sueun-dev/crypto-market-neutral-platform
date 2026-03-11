"""포지션 균형 관리 모듈"""
from typing import Dict, Optional
import logging
from dataclasses import dataclass
from datetime import datetime
from src.config import settings
import time

logger = logging.getLogger(__name__)


@dataclass
class PositionBalance:
    """포지션 균형 상태"""
    symbol: str
    spot_quantity: float  # 현물 코인 개수
    futures_quantity: float  # 선물 코인 개수
    spot_value_usd: float  # 현물 USD 가치 (참고용)
    futures_value_usd: float  # 선물 USD 가치 (참고용)
    quantity_gap: float  # 개수 차이
    gap_percentage: float  # 개수 차이 비율
    is_balanced: bool
    needs_rebalancing: bool
    timestamp: datetime


class PositionBalancer:
    """포지션 균형 관리자"""
    
    def __init__(self, position_manager, order_executor, korean_exchange, futures_exchange):
        self.position_manager = position_manager
        self.order_executor = order_executor
        self.korean_exchange = korean_exchange
        self.futures_exchange = futures_exchange
        self.max_gap_usd = settings.MAX_POSITION_GAP_USD  # 최대 허용 갭
        self.rebalance_threshold = settings.REBALANCE_THRESHOLD_USD  # 리밸런싱 트리거 갭
        
    def check_position_balance(self, symbol: str) -> Optional[PositionBalance]:
        """특정 심볼의 포지션 균형 체크 - 코인 개수 기준"""
        try:
            # 현물 포지션 조회 (개수와 가치)
            spot_quantity, spot_value = self._get_spot_position_info(symbol)
            
            # 선물 포지션 조회 (개수와 가치)
            futures_quantity, futures_value = self._get_futures_position_info(symbol)
            
            # 개수 차이 계산 (헤지의 핵심)
            quantity_gap = abs(spot_quantity - futures_quantity)
            gap_percentage = (quantity_gap / max(spot_quantity, futures_quantity) * 100) if max(spot_quantity, futures_quantity) > 0 else 0
            
            # 균형 상태 판단 - 개수 기준 (1% 이내면 균형)
            is_balanced = gap_percentage <= 1.0
            needs_rebalancing = gap_percentage >= 2.0  # 2% 이상 차이시 리밸런싱
            
            balance = PositionBalance(
                symbol=symbol,
                spot_quantity=spot_quantity,
                futures_quantity=futures_quantity,
                spot_value_usd=spot_value,
                futures_value_usd=futures_value,
                quantity_gap=quantity_gap,
                gap_percentage=gap_percentage,
                is_balanced=is_balanced,
                needs_rebalancing=needs_rebalancing,
                timestamp=datetime.now()
            )
            
            # 로그 출력
            if not is_balanced:
                logger.warning(
                    f"⚠️ {symbol} 포지션 불균형 감지 - "
                    f"현물: {spot_quantity:.6f}개, 선물: {futures_quantity:.6f}개, "
                    f"개수 차이: {quantity_gap:.6f}개 ({gap_percentage:.2f}%)"
                )
            
            return balance
            
        except Exception as e:
            logger.error(f"{symbol} 포지션 균형 체크 실패: {e}")
            return None
    
    def _get_spot_position_info(self, symbol: str) -> tuple[float, float]:
        """현물 포지션 정보 조회 (개수, USD 가치)"""
        try:
            base_currency = symbol.split('/')[0]
            
            # 현물 잔고 조회 - Bithumb/Upbit의 get_balance 사용
            balance = self.korean_exchange.get_balance(base_currency)
            if not balance:
                return 0.0, 0.0
            
            spot_amount = balance.get('free', 0.0)
            if spot_amount <= 0:
                return 0.0, 0.0
            
            # 현재 매도 가격(bid)으로 USD 환산
            ticker = self.korean_exchange.get_ticker(symbol)
            if not ticker or 'bid' not in ticker:
                return spot_amount, 0.0
            
            # KRW 가격을 USD로 변환 (현물 매도 시 받을 KRW)
            krw_value = spot_amount * ticker['bid']
            
            # USDT/KRW 환율 조회 (KRW를 USD로 변환)
            usdt_krw_ticker = self.korean_exchange.get_ticker('USDT/KRW')
            if not usdt_krw_ticker or 'ask' not in usdt_krw_ticker:
                return spot_amount, 0.0
            
            # KRW를 USD로 변환 (실제로 KRW로 USDT를 살 때의 가격)
            usd_value = krw_value / usdt_krw_ticker['ask']
            
            return spot_amount, usd_value
            
        except Exception as e:
            logger.error(f"{symbol} 현물 포지션 조회 실패: {e}")
            return 0.0, 0.0
    
    def _get_spot_position_value(self, symbol: str) -> float:
        """현물 포지션 USD 가치만 조회 (기존 호환성 유지)"""
        _, value = self._get_spot_position_info(symbol)
        return value
    
    def _get_futures_position_info(self, symbol: str) -> tuple[float, float]:
        """선물 포지션 정보 조회 (개수, USD 가치)"""
        try:
            # GateIO futures 포지션 조회
            positions = self.futures_exchange.get_positions()
            
            if not positions:
                return 0.0, 0.0
            
            # 심볼 비교를 위한 정규화
            for position in positions:
                # Gate.io position에서 symbol 확인 (예: "IP/USDT:USDT")
                pos_symbol = position.get("symbol", "")
                
                # 심플하게 심볼이 포함되어 있는지 확인
                if symbol not in pos_symbol:
                    continue
                
                # 숏 포지션만 처리
                if position.get('side') != 'short':
                    continue
                
                # USD 가치
                val = position.get("value") or position.get("notional")
                usd_value = abs(float(val)) if val is not None else 0.0
                
                # 코인 개수 계산
                contracts = abs(position.get("contracts", 0))  # 계약 수
                mark_price = float(position.get("mark_price") or position.get("markPrice", 0))
                
                # Gate.io의 contract_size 정보 활용
                contract_info = self.futures_exchange.futures_markets.get(f"{symbol}/USDT:USDT", {})
                contract_size = contract_info.get('contract_size', 1)
                
                # 실제 코인 개수 = 계약수 × 계약크기
                coin_quantity = contracts * contract_size
                
                # 개수가 0이면 value/price로 역산
                if coin_quantity == 0 and usd_value > 0 and mark_price > 0:
                    coin_quantity = usd_value / mark_price
                
                return coin_quantity, usd_value
            
            return 0.0, 0.0
            
        except Exception as e:
            logger.error(f"{symbol} 선물 포지션 조회 실패: {e}")
            return 0.0, 0.0
    
    def _get_futures_position_value(self, symbol: str) -> float:
        """선물 포지션 USD 가치만 조회 (기존 호환성 유지)"""
        _, value = self._get_futures_position_info(symbol)
        return value
    
    def rebalance_position(self, symbol: str) -> bool:
        """포지션 리밸런싱 실행 - 코인 개수 기준"""
        try:
            balance = self.check_position_balance(symbol)
            
            if not balance or not balance.needs_rebalancing:
                return True
            
            logger.info(
                f"🔄 {symbol} 포지션 리밸런싱 시작 - "
                f"현물: {balance.spot_quantity:.6f}개, "
                f"선물: {balance.futures_quantity:.6f}개"
            )
            
            # 코인 개수 기준으로 조정
            if balance.spot_quantity > balance.futures_quantity:
                # 현물이 더 많음 -> 선물 숏 추가
                quantity_gap = balance.spot_quantity - balance.futures_quantity
                logger.info(f"📉 {symbol} 선물 숏 추가 필요: {quantity_gap:.6f}개")
                
                # 선물 숏 추가 주문 (개수 기준)
                success = self._add_futures_short_by_quantity(symbol, quantity_gap)
                
            else:
                # 선물이 더 많음 -> 현물 추가
                quantity_gap = balance.futures_quantity - balance.spot_quantity
                logger.info(f"📈 {symbol} 현물 추가 필요: {quantity_gap:.6f}개")
                
                # 현물 추가 주문 (개수 기준)
                success = self._add_spot_position_by_quantity(symbol, quantity_gap)
            
            if success:
                logger.info(f"✅ {symbol} 포지션 리밸런싱 완료")
            else:
                logger.error(f"❌ {symbol} 포지션 리밸런싱 실패")
            
            return success
            
        except Exception as e:
            logger.error(f"{symbol} 포지션 리밸런싱 실패: {e}")
            return False
    
    def _add_futures_short_by_quantity(self, symbol: str, quantity: float) -> bool:
        """선물 숏 포지션 추가 (코인 개수 기준)"""
        try:
            # 최소 주문 크기 확인 (예: BTC 0.0001개 이상)
            if quantity < 0.0001:
                logger.info(f"{symbol} 선물 추가 수량 너무 작음: {quantity:.6f}개")
                return True
            
            # Gate.io는 코인 개수를 받아서 내부적으로 계약수로 변환
            # params 없이 보내면 직접 호출로 인식되어 코인->계약 변환됨
            order = self.futures_exchange.create_market_order(
                symbol=f"{symbol}/USDT:USDT",
                side='sell',
                amount=quantity  # 코인 개수 (Gate.io가 계약수로 변환)
            )
            
            if order:
                logger.info(f"✅ {symbol} 선물 숏 추가 완료: {quantity:.6f}개")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"{symbol} 선물 숏 추가 실패: {e}")
            return False
    
    def _add_spot_position_by_quantity(self, symbol: str, quantity: float) -> bool:
        """현물 포지션 추가 (코인 개수 기준)"""
        try:
            # 최소 주문 크기 확인
            if quantity < 0.0001:
                logger.info(f"{symbol} 현물 추가 수량 너무 작음: {quantity:.6f}개")
                return True
            
            # 현재 가격 조회
            korean_ticker = self.korean_exchange.get_ticker(f"{symbol}/KRW")
            if not korean_ticker or 'ask' not in korean_ticker:
                return False
            
            # 코인 개수를 KRW 금액으로 변환 (매수는 KRW 금액으로만 가능)
            krw_amount = quantity * korean_ticker['ask']
            
            # 최소 주문 금액 확인 (업비트 5000원, 빗썸 1000원)
            min_order_krw = 5000 if self.korean_exchange.exchange_id.lower() == 'upbit' else 1000
            if krw_amount < min_order_krw:
                logger.info(f"{symbol} 주문 금액 너무 작음: {krw_amount:.0f}원 < {min_order_krw}원")
                return True
            
            # KRW 금액으로 매수 주문
            order = self.korean_exchange.create_market_order(
                symbol=f"{symbol}/KRW",
                side='buy',
                amount=krw_amount  # KRW 금액으로 변환해서 주문
            )
            
            if order:
                logger.info(f"✅ {symbol} 현물 추가 완료: {quantity:.6f}개 ({krw_amount:.0f}원)")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"{symbol} 현물 추가 실패: {e}")
            return False
    
    def _add_futures_short(self, symbol: str, amount_usd: float) -> bool:
        """선물 숏 포지션 추가 (매도)"""
        try:
            # 최소 주문 크기 확인
            if amount_usd < 10.0:
                logger.info(f"{symbol} 선물 추가 금액 너무 작음: ${amount_usd:.2f}")
                return True
            
            # 현재 가격으로 수량 계산
            futures_ticker = self.futures_exchange.get_ticker(f"{symbol}/USDT:USDT")
            if not futures_ticker or 'bid' not in futures_ticker:
                return False
            
            quantity = amount_usd / futures_ticker['bid']
            
            # 기존 create_market_order 사용
            order = self.futures_exchange.create_market_order(
                symbol=f"{symbol}/USDT:USDT",
                side='sell',
                amount=quantity
            )
            
            if order:
                logger.info(f"✅ {symbol} 선물 숏 추가 완료: ${amount_usd:.2f}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"{symbol} 선물 숏 추가 실패: {e}")
            return False
    
    def _add_spot_position(self, symbol: str, amount_usd: float) -> bool:
        """현물 포지션 추가"""
        try:
            # 최소 주문 크기 확인
            if amount_usd < 10.0:
                logger.info(f"{symbol} 현물 추가 금액 너무 작음: ${amount_usd:.2f}")
                return True
            
            # USDT/KRW 환율 조회
            usdt_krw_ticker = self.korean_exchange.get_ticker('USDT/KRW')
            if not usdt_krw_ticker or 'ask' not in usdt_krw_ticker:
                return False
            
            # 현재 가격 조회
            korean_ticker = self.korean_exchange.get_ticker(f"{symbol}/KRW")
            if not korean_ticker or 'ask' not in korean_ticker:
                return False
            
            # KRW 금액 계산 (USD를 KRW로 변환 - USDT 매도 가격)
            krw_amount = amount_usd * usdt_krw_ticker['bid']
            
            # 빗썸/업비트는 KRW 금액으로 매수
            order = self.korean_exchange.create_market_order(
                symbol=f"{symbol}/KRW",
                side='buy',
                amount=krw_amount
            )
            
            if order:
                logger.info(f"✅ {symbol} 현물 추가 완료: ${amount_usd:.2f}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"{symbol} 현물 추가 실패: {e}")
            return False
    
    def check_all_positions(self) -> Dict[str, PositionBalance]:
        """모든 활성 포지션의 균형 체크"""
        balances = {}
        
        for symbol in self.position_manager.positions.keys():
            balance = self.check_position_balance(symbol)
            if balance:
                balances[symbol] = balance
        
        # 불균형 포지션 로그
        for symbol, balance in balances.items():
            if not balance.is_balanced:
                logger.warning(
                    f"⚠️ {symbol} 불균형: 갭 ${balance.gap_usd:.2f}"
                )
        
        return balances
    
    def balance_after_close(self, symbol: str, close_percentage: float = None) -> bool:
        """청산 후 포지션 균형 조정 - 코인 개수 기준
        
        청산 후 한쪽이 더 많이 남은 경우, 많은 쪽을 추가로 청산하여
        양쪽 포지션의 코인 개수를 일치시킴
        """
        try:
            # 청산 후 잠시 대기 (거래소 반영 시간)
            time.sleep(2)
            
            # 현재 균형 체크
            balance = self.check_position_balance(symbol)
            if not balance:
                return False
            
            # 균형이 맞으면 종료
            if balance.is_balanced:
                logger.info(f"✅ {symbol} 청산 후 균형 유지됨: 개수 차이 {balance.quantity_gap:.6f}개 ({balance.gap_percentage:.2f}%)")
                return True
            
            logger.warning(
                f"⚠️ {symbol} 청산 후 불균형 - "
                f"현물: {balance.spot_quantity:.6f}개, "
                f"선물: {balance.futures_quantity:.6f}개, "
                f"개수 차이: {balance.quantity_gap:.6f}개"
            )
            
            # 더 많이 남은 쪽을 추가 청산 (코인 개수 기준)
            if balance.spot_quantity > balance.futures_quantity:
                # 현물이 더 많음 -> 현물 추가 청산
                excess_quantity = balance.spot_quantity - balance.futures_quantity
                
                # 최소 주문 크기 확인
                if excess_quantity < 0.0001:
                    logger.info(f"{symbol} 추가 청산 수량 너무 작음: {excess_quantity:.6f}개")
                    return True
                
                logger.info(f"📉 {symbol} 현물 추가 청산: {excess_quantity:.6f}개")
                success = self._close_excess_spot_by_quantity(symbol, excess_quantity)
                
            else:
                # 선물이 더 많음 -> 선물 추가 청산
                excess_quantity = balance.futures_quantity - balance.spot_quantity
                
                # 최소 주문 크기 확인
                if excess_quantity < 0.0001:
                    logger.info(f"{symbol} 추가 청산 수량 너무 작음: {excess_quantity:.6f}개")
                    return True
                
                logger.info(f"📈 {symbol} 선물 추가 청산: {excess_quantity:.6f}개")
                success = self._close_excess_futures_by_quantity(symbol, excess_quantity)
            
            if success:
                # 재확인
                time.sleep(2)
                final_balance = self.check_position_balance(symbol)
                if final_balance and final_balance.is_balanced:
                    logger.info(f"✅ {symbol} 균형 조정 완료: 개수 차이 {final_balance.quantity_gap:.6f}개")
                    return True
                else:
                    logger.warning(f"⚠️ {symbol} 균형 조정 후에도 갭 존재: {final_balance.quantity_gap:.6f}개")
            
            return success
            
        except Exception as e:
            logger.error(f"{symbol} 청산 후 균형 조정 실패: {e}")
            return False
    
    def _close_excess_spot_by_quantity(self, symbol: str, quantity: float) -> bool:
        """초과 현물 청산 (코인 개수 기준)"""
        try:
            # 빗썸은 4자리 반올림
            if self.korean_exchange.exchange_id.lower() == 'bithumb':
                quantity = round(quantity, 4)
            
            # 현물 매도 주문 - 기존 create_market_order 사용
            order = self.korean_exchange.create_market_order(
                symbol=f"{symbol}/KRW",
                side='sell',
                amount=quantity  # 코인 개수로 주문
            )
            
            if order:
                logger.info(f"✅ {symbol} 현물 추가 청산 완료: {quantity:.6f}개")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"{symbol} 현물 추가 청산 실패: {e}")
            return False
    
    def _close_excess_futures_by_quantity(self, symbol: str, quantity: float) -> bool:
        """초과 선물 청산 (코인 개수 기준)"""
        try:
            # Gate.io는 코인 개수를 받아서 내부적으로 계약수로 변환
            # reduce_only는 포지션 청산 전용 모드
            order = self.futures_exchange.create_market_order(
                symbol=f"{symbol}/USDT:USDT",
                side='buy',
                amount=quantity,  # 코인 개수 (Gate.io가 계약수로 변환)
                params={'reduce_only': True}  # 포지션 청산 모드
            )
            
            if order:
                logger.info(f"✅ {symbol} 선물 추가 청산 완료: {quantity:.6f}개")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"{symbol} 선물 추가 청산 실패: {e}")
            return False
    
    def _close_excess_spot(self, symbol: str, amount_usd: float) -> bool:
        """초과 현물 청산"""
        try:
            # 현재 가격 조회
            korean_ticker = self.korean_exchange.get_ticker(f"{symbol}/KRW")
            if not korean_ticker or 'bid' not in korean_ticker:
                return False
            
            # USDT/KRW 환율
            usdt_krw_ticker = self.korean_exchange.get_ticker('USDT/KRW')
            if not usdt_krw_ticker or 'ask' not in usdt_krw_ticker:
                return False
            
            # KRW 가격을 USD로 변환하여 수량 계산
            ticker_usd = korean_ticker['bid'] / usdt_krw_ticker['ask']
            quantity = amount_usd / ticker_usd
            
            # 빗썸은 4자리 반올림
            if self.korean_exchange.exchange_id.lower() == 'bithumb':
                quantity = round(quantity, 4)
            
            # 현물 매도 주문 - 기존 create_market_order 사용
            order = self.korean_exchange.create_market_order(
                symbol=f"{symbol}/KRW",
                side='sell',
                amount=quantity
            )
            
            if order:
                logger.info(f"✅ {symbol} 현물 추가 청산 완료: ${amount_usd:.2f}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"{symbol} 현물 추가 청산 실패: {e}")
            return False
    
    def _close_excess_futures(self, symbol: str, amount_usd: float) -> bool:
        """초과 선물 청산 (숏 포지션 매수로 청산)"""
        try:
            # 현재 가격 조회 (숏 청산 = 매수이므로 ask 사용)
            futures_ticker = self.futures_exchange.get_ticker(f"{symbol}/USDT:USDT")
            if not futures_ticker or 'ask' not in futures_ticker:
                return False
            
            quantity = amount_usd / futures_ticker['ask']
            
            # 숏 포지션 청산 (buy로 청산) - 기존 create_market_order 사용
            order = self.futures_exchange.create_market_order(
                symbol=f"{symbol}/USDT:USDT",
                side='buy',
                amount=quantity,
                params={'reduce_only': True}  # 포지션 청산 모드
            )
            
            if order:
                logger.info(f"✅ {symbol} 선물 추가 청산 완료: ${amount_usd:.2f}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"{symbol} 선물 추가 청산 실패: {e}")
            return False