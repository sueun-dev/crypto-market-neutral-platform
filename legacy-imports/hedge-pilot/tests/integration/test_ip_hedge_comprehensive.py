#!/usr/bin/env python3
"""
IP 코인 헤지 포지션 종합 테스트
- 실제 거래소에서 IP 코인 매매
- 모든 포지션 관리 기능 테스트
"""

import sys
import os
import time
import logging
from datetime import datetime
from colorama import init, Fore, Style

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import settings
from src.exchanges.bithumb import BithumbExchange
from src.exchanges.gateio import GateIOExchange
from src.managers.position_manager import PositionManager
from src.core.order_executor import OrderExecutor
from src.core.position_balancer import PositionBalancer

# Initialize colorama for colored output
init()

# Configure logging with detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class IPHedgeTest:
    """IP 코인 헤지 테스트"""
    
    def __init__(self):
        """Initialize test components"""
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"IP 코인 헤지 포지션 종합 테스트")
        print(f"{'='*60}{Style.RESET_ALL}\n")
        
        # Test configuration
        self.symbol = "IP"
        self.test_amount_krw = 50000  # 5만원으로 테스트
        self.min_trade_amount = 10000  # 최소 거래 금액
        
        # Initialize exchanges
        print(f"{Fore.YELLOW}거래소 초기화 중...{Style.RESET_ALL}")
        self.bithumb = BithumbExchange(settings.KOREAN_EXCHANGE_CREDENTIALS)
        self.gateio = GateIOExchange(settings.FUTURES_EXCHANGE_CREDENTIALS)
        
        # Initialize managers
        self.position_manager = PositionManager(self.bithumb, self.gateio)
        self.order_executor = OrderExecutor(
            korean_exchange=self.bithumb,
            futures_exchange=self.gateio,
            position_manager=self.position_manager
        )
        self.position_balancer = PositionBalancer(
            position_manager=self.position_manager,
            order_executor=self.order_executor,
            korean_exchange=self.bithumb,
            futures_exchange=self.gateio
        )
        
        print(f"{Fore.GREEN}✓ 초기화 완료{Style.RESET_ALL}\n")
    
    def check_markets(self):
        """시장 정보 확인"""
        print(f"\n{Fore.CYAN}[1단계] 시장 정보 확인{Style.RESET_ALL}")
        print("-" * 40)
        
        # Check Bithumb
        print(f"{Fore.YELLOW}빗썸 IP/KRW 시장 확인...{Style.RESET_ALL}")
        bithumb_ticker = self.bithumb.get_ticker("IP/KRW")
        if bithumb_ticker:
            print(f"  현재가: {bithumb_ticker['last']:,.0f} KRW")
            print(f"  매수호가: {bithumb_ticker['ask']:,.0f} KRW")
            print(f"  매도호가: {bithumb_ticker['bid']:,.0f} KRW")
        else:
            print(f"{Fore.RED}  ✗ 빗썸 시장 정보 조회 실패{Style.RESET_ALL}")
            return False
        
        # Check Gate.io
        print(f"\n{Fore.YELLOW}Gate.io IP/USDT:USDT 선물 시장 확인...{Style.RESET_ALL}")
        gateio_ticker = self.gateio.get_ticker("IP/USDT:USDT")
        if gateio_ticker:
            print(f"  현재가: ${gateio_ticker['last']:.4f}")
            print(f"  매수호가: ${gateio_ticker['ask']:.4f}")
            print(f"  매도호가: ${gateio_ticker['bid']:.4f}")
        else:
            print(f"{Fore.RED}  ✗ Gate.io 시장 정보 조회 실패{Style.RESET_ALL}")
            return False
        
        # Check contract info
        markets = self.gateio.get_markets()
        ip_market = markets.get("IP/USDT:USDT")
        if ip_market:
            print(f"  계약 크기: {ip_market['contract_size']} IP")
        
        print(f"\n{Fore.GREEN}✓ 시장 정보 확인 완료{Style.RESET_ALL}")
        return True
    
    def check_balances(self):
        """잔고 확인"""
        print(f"\n{Fore.CYAN}[잔고 확인]{Style.RESET_ALL}")
        print("-" * 40)
        
        # Bithumb balance
        print(f"{Fore.YELLOW}빗썸 잔고:{Style.RESET_ALL}")
        bithumb_balance = self.bithumb.fetch_balance()
        if bithumb_balance and 'free' in bithumb_balance:
            ip_balance = bithumb_balance['free'].get('IP', 0)
            krw_balance = bithumb_balance['free'].get('KRW', 0)
            print(f"  IP: {ip_balance:.4f} 개")
            print(f"  KRW: {krw_balance:,.0f} 원")
        
        # Gate.io balance
        print(f"\n{Fore.YELLOW}Gate.io 잔고:{Style.RESET_ALL}")
        usdt_balance = self.gateio.get_balance('USDT')
        if usdt_balance:
            print(f"  USDT: ${usdt_balance['free']:.2f} (사용가능)")
            print(f"  USDT: ${usdt_balance['used']:.2f} (사용중)")
            print(f"  USDT: ${usdt_balance['total']:.2f} (총액)")
        
        return True
    
    def test_open_position(self):
        """포지션 오픈 테스트 (헤지 생성)"""
        print(f"\n{Fore.CYAN}[2단계] 포지션 오픈 테스트 - 헤지 생성{Style.RESET_ALL}")
        print("-" * 40)
        
        print(f"{Fore.YELLOW}IP 헤지 포지션 오픈 중...{Style.RESET_ALL}")
        print(f"  테스트 금액: {self.test_amount_krw:,} KRW")
        
        # Open hedge position
        success = self.order_executor.open_hedge_position(
            symbol=self.symbol,
            amount_in_krw=self.test_amount_krw
        )
        
        if success:
            print(f"{Fore.GREEN}✓ 헤지 포지션 오픈 성공!{Style.RESET_ALL}")
            time.sleep(3)  # Wait for exchange to process
            
            # Check position balance
            self._check_position_details()
            return True
        else:
            print(f"{Fore.RED}✗ 헤지 포지션 오픈 실패{Style.RESET_ALL}")
            return False
    
    def test_position_balance(self):
        """포지션 균형 확인"""
        print(f"\n{Fore.CYAN}[3단계] 포지션 균형 확인{Style.RESET_ALL}")
        print("-" * 40)
        
        balance = self.position_balancer.check_position_balance(self.symbol)
        
        if balance:
            print(f"{Fore.YELLOW}포지션 균형 상태:{Style.RESET_ALL}")
            print(f"  현물 수량: {balance.spot_quantity:.6f} IP")
            print(f"  선물 수량: {balance.futures_quantity:.6f} IP")
            print(f"  수량 차이: {balance.quantity_gap:.6f} IP ({balance.gap_percentage:.2f}%)")
            print(f"  현물 가치: ${balance.spot_value_usd:.2f}")
            print(f"  선물 가치: ${balance.futures_value_usd:.2f}")
            
            if balance.is_balanced:
                print(f"{Fore.GREEN}✓ 포지션 균형 상태 양호 (1% 이내){Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}⚠ 포지션 불균형 감지{Style.RESET_ALL}")
                
                if balance.needs_rebalancing:
                    print(f"{Fore.YELLOW}리밸런싱 필요 (2% 이상 차이){Style.RESET_ALL}")
            
            return balance
        else:
            print(f"{Fore.RED}✗ 포지션 균형 확인 실패{Style.RESET_ALL}")
            return None
    
    def test_partial_close(self, percentage=25):
        """부분 청산 테스트"""
        print(f"\n{Fore.CYAN}[4단계] 부분 청산 테스트 ({percentage}%){Style.RESET_ALL}")
        print("-" * 40)
        
        # Get current position
        position = self.position_manager.get_position(self.symbol)
        if not position:
            print(f"{Fore.RED}✗ 포지션 없음{Style.RESET_ALL}")
            return False
        
        print(f"{Fore.YELLOW}{percentage}% 청산 실행 중...{Style.RESET_ALL}")
        print(f"  청산 전 포지션 가치: ${position.value_usd:.2f}")
        
        # Execute partial close
        success = self.order_executor.close_position_percentage(
            symbol=self.symbol,
            percentage=percentage,
            current_value_usd=position.value_usd
        )
        
        if success:
            print(f"{Fore.GREEN}✓ {percentage}% 청산 성공!{Style.RESET_ALL}")
            time.sleep(3)  # Wait for exchange to process
            
            # Check balance after close
            print(f"\n{Fore.YELLOW}청산 후 균형 조정 중...{Style.RESET_ALL}")
            balance_success = self.position_balancer.balance_after_close(
                symbol=self.symbol,
                close_percentage=percentage
            )
            
            if balance_success:
                print(f"{Fore.GREEN}✓ 균형 조정 완료{Style.RESET_ALL}")
            
            # Check new position
            self._check_position_details()
            return True
        else:
            print(f"{Fore.RED}✗ 청산 실패{Style.RESET_ALL}")
            return False
    
    def test_rebalancing(self):
        """리밸런싱 테스트"""
        print(f"\n{Fore.CYAN}[5단계] 포지션 리밸런싱 테스트{Style.RESET_ALL}")
        print("-" * 40)
        
        # First check if rebalancing is needed
        balance = self.position_balancer.check_position_balance(self.symbol)
        
        if not balance:
            print(f"{Fore.RED}✗ 포지션 균형 확인 실패{Style.RESET_ALL}")
            return False
        
        if not balance.needs_rebalancing:
            print(f"{Fore.YELLOW}리밸런싱 불필요 (2% 미만 차이){Style.RESET_ALL}")
            
            # Force create imbalance for testing
            print(f"\n{Fore.YELLOW}테스트를 위해 의도적으로 불균형 생성...{Style.RESET_ALL}")
            # Buy small amount of spot only to create imbalance
            self.bithumb.create_market_order(
                symbol="IP/KRW",
                side="buy",
                amount=10000  # 1만원 추가 매수
            )
            time.sleep(3)
            
            # Recheck balance
            balance = self.position_balancer.check_position_balance(self.symbol)
        
        if balance and balance.needs_rebalancing:
            print(f"{Fore.YELLOW}리밸런싱 실행 중...{Style.RESET_ALL}")
            print(f"  현물 수량: {balance.spot_quantity:.6f} IP")
            print(f"  선물 수량: {balance.futures_quantity:.6f} IP")
            print(f"  수량 차이: {balance.quantity_gap:.6f} IP ({balance.gap_percentage:.2f}%)")
            
            success = self.position_balancer.rebalance_position(self.symbol)
            
            if success:
                print(f"{Fore.GREEN}✓ 리밸런싱 성공!{Style.RESET_ALL}")
                time.sleep(3)
                
                # Check balance after rebalancing
                new_balance = self.position_balancer.check_position_balance(self.symbol)
                if new_balance:
                    print(f"\n{Fore.YELLOW}리밸런싱 후 상태:{Style.RESET_ALL}")
                    print(f"  현물 수량: {new_balance.spot_quantity:.6f} IP")
                    print(f"  선물 수량: {new_balance.futures_quantity:.6f} IP")
                    print(f"  수량 차이: {new_balance.quantity_gap:.6f} IP ({new_balance.gap_percentage:.2f}%)")
                    
                    if new_balance.is_balanced:
                        print(f"{Fore.GREEN}✓ 균형 회복 완료!{Style.RESET_ALL}")
                
                return True
            else:
                print(f"{Fore.RED}✗ 리밸런싱 실패{Style.RESET_ALL}")
                return False
        
        return True
    
    def test_full_close(self):
        """전체 청산 테스트"""
        print(f"\n{Fore.CYAN}[6단계] 전체 포지션 청산 테스트{Style.RESET_ALL}")
        print("-" * 40)
        
        # Get current position
        position = self.position_manager.get_position(self.symbol)
        if not position:
            print(f"{Fore.YELLOW}포지션 없음{Style.RESET_ALL}")
            return True
        
        print(f"{Fore.YELLOW}전체 포지션 청산 중...{Style.RESET_ALL}")
        print(f"  청산 전 포지션 가치: ${position.value_usd:.2f}")
        
        # Execute full close
        success = self.order_executor.close_position_percentage(
            symbol=self.symbol,
            percentage=100,
            current_value_usd=position.value_usd
        )
        
        if success:
            print(f"{Fore.GREEN}✓ 전체 청산 성공!{Style.RESET_ALL}")
            time.sleep(3)
            
            # Verify no position remains
            self._check_position_details()
            
            # Check final balances
            self.check_balances()
            
            return True
        else:
            print(f"{Fore.RED}✗ 전체 청산 실패{Style.RESET_ALL}")
            return False
    
    def _check_position_details(self):
        """포지션 상세 정보 확인"""
        print(f"\n{Fore.YELLOW}현재 포지션 상태:{Style.RESET_ALL}")
        
        # Get position from manager
        position = self.position_manager.get_position(self.symbol)
        
        if position:
            print(f"  총 가치: ${position.value_usd:.2f}")
            print(f"  Long (현물):")
            print(f"    - 거래소: {', '.join(position.long_exchanges)}")
            print(f"    - 가치: ${position.long_value:.2f}")
            print(f"  Short (선물):")
            print(f"    - 거래소: {', '.join(position.short_exchanges)}")
            print(f"    - 가치: ${position.short_value:.2f}")
        else:
            print(f"  포지션 없음")
        
        # Get actual positions from exchanges
        print(f"\n{Fore.YELLOW}거래소별 실제 포지션:{Style.RESET_ALL}")
        
        # Bithumb spot
        bithumb_balance = self.bithumb.fetch_balance()
        if bithumb_balance and 'free' in bithumb_balance:
            ip_balance = bithumb_balance['free'].get('IP', 0)
            if ip_balance > 0:
                print(f"  빗썸 현물: {ip_balance:.6f} IP")
        
        # Gate.io futures
        gateio_positions = self.gateio.get_positions()
        for pos in gateio_positions:
            if 'IP' in pos.get('symbol', ''):
                print(f"  Gate.io 선물:")
                print(f"    - 방향: {pos.get('side')}")
                print(f"    - 계약수: {pos.get('contracts')}")
                print(f"    - 가치: ${abs(pos.get('notional', 0)):.2f}")
    
    def run_all_tests(self):
        """모든 테스트 실행"""
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"IP 코인 헤지 종합 테스트 시작")
        print(f"시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}{Style.RESET_ALL}\n")
        
        try:
            # 1. Check markets
            if not self.check_markets():
                print(f"{Fore.RED}시장 확인 실패. 테스트 중단.{Style.RESET_ALL}")
                return
            
            # 2. Check initial balances
            self.check_balances()
            
            # 3. Open hedge position
            if not self.test_open_position():
                print(f"{Fore.RED}포지션 오픈 실패. 테스트 중단.{Style.RESET_ALL}")
                return
            
            # 4. Check position balance
            self.test_position_balance()
            
            # Wait a bit
            print(f"\n{Fore.YELLOW}10초 대기 중...{Style.RESET_ALL}")
            time.sleep(10)
            
            # 5. Test partial close (25%)
            if self.test_partial_close(25):
                print(f"\n{Fore.YELLOW}10초 대기 중...{Style.RESET_ALL}")
                time.sleep(10)
            
            # 6. Test rebalancing
            self.test_rebalancing()
            
            # Wait a bit
            print(f"\n{Fore.YELLOW}10초 대기 중...{Style.RESET_ALL}")
            time.sleep(10)
            
            # 7. Test another partial close (50% of remaining)
            if self.test_partial_close(50):
                print(f"\n{Fore.YELLOW}10초 대기 중...{Style.RESET_ALL}")
                time.sleep(10)
            
            # 8. Final close
            self.test_full_close()
            
            print(f"\n{Fore.GREEN}{'='*60}")
            print(f"테스트 완료!")
            print(f"{'='*60}{Style.RESET_ALL}\n")
            
        except Exception as e:
            print(f"\n{Fore.RED}테스트 중 오류 발생: {e}{Style.RESET_ALL}")
            logger.exception("Test error")
            
            # Emergency close all positions
            print(f"\n{Fore.YELLOW}긴급 포지션 청산 시도...{Style.RESET_ALL}")
            try:
                self.test_full_close()
            except:
                pass

def main():
    """Main test function"""
    test = IPHedgeTest()
    
    # Confirm before starting
    print(f"\n{Fore.YELLOW}경고: 실제 거래가 실행됩니다!{Style.RESET_ALL}")
    print(f"테스트 코인: IP")
    print(f"테스트 금액: 50,000 KRW")
    print(f"거래소: 빗썸 (현물), Gate.io (선물)")
    
    response = input(f"\n계속하시겠습니까? (yes/no): ")
    if response.lower() != 'yes':
        print(f"{Fore.RED}테스트 취소됨{Style.RESET_ALL}")
        return
    
    # Run all tests
    test.run_all_tests()

if __name__ == "__main__":
    main()