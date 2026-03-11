#!/usr/bin/env python3
"""
포지션 밸런싱 종합 테스트
- 실제 IP 코인으로 불균형 생성 및 리밸런싱 테스트
"""

import sys
import os
import time
import logging
from datetime import datetime
from colorama import init, Fore, Style

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.exchanges.bithumb import BithumbExchange
from src.exchanges.gateio import GateIOExchange
from src.managers.position_manager import PositionManager
from src.core.order_executor import OrderExecutor
from src.core.position_balancer import PositionBalancer
from dotenv import load_dotenv

# Initialize colorama
init()

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class PositionBalanceTest:
    """포지션 밸런싱 테스트"""
    
    def __init__(self):
        """Initialize test components"""
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"포지션 밸런싱 종합 테스트")
        print(f"{'='*60}{Style.RESET_ALL}\n")
        
        # Initialize exchanges
        print(f"{Fore.YELLOW}거래소 초기화 중...{Style.RESET_ALL}")
        
        self.bithumb = BithumbExchange(
            os.getenv('BITHUMB_API_KEY'),
            os.getenv('BITHUMB_API_SECRET')
        )
        
        gateio_creds = {
            'apiKey': os.getenv('GATEIO_API_KEY'),
            'secret': os.getenv('GATEIO_API_SECRET')
        }
        self.gateio = GateIOExchange(gateio_creds)
        
        # Initialize managers
        self.position_manager = PositionManager()
        self.order_executor = OrderExecutor(
            korean_exchange=self.bithumb,
            futures_exchange=self.gateio
        )
        self.position_balancer = PositionBalancer(
            position_manager=self.position_manager,
            order_executor=self.order_executor,
            korean_exchange=self.bithumb,
            futures_exchange=self.gateio
        )
        
        self.symbol = "IP"
        print(f"{Fore.GREEN}✓ 초기화 완료{Style.RESET_ALL}\n")
    
    def check_current_state(self):
        """현재 상태 확인"""
        print(f"\n{Fore.CYAN}[현재 상태 확인]{Style.RESET_ALL}")
        print("-" * 40)
        
        # Bithumb balance
        ip_balance = self.bithumb.get_balance(self.symbol)
        spot_amount = ip_balance['free'] if ip_balance else 0
        print(f"빗썸 {self.symbol}: {spot_amount:.6f}개")
        
        # Gate.io positions
        positions = self.gateio.get_positions()
        futures_contracts = 0
        for pos in positions:
            if self.symbol in pos.get('symbol', ''):
                futures_contracts = abs(pos['contracts'])
                print(f"Gate.io 선물: {futures_contracts} contracts")
                print(f"  방향: {pos['side']}")
                print(f"  가치: ${abs(pos.get('notional', 0)):.2f}")
        
        # Position balance
        balance = self.position_balancer.check_position_balance(self.symbol)
        if balance:
            print(f"\n균형 상태:")
            print(f"  현물: {balance.spot_quantity:.6f} {self.symbol}")
            print(f"  선물: {balance.futures_quantity:.6f} {self.symbol}")
            print(f"  차이: {balance.quantity_gap:.6f} ({balance.gap_percentage:.2f}%)")
            
            if balance.is_balanced:
                print(f"  {Fore.GREEN}✓ 균형 상태{Style.RESET_ALL}")
            else:
                print(f"  {Fore.YELLOW}⚠ 불균형 상태{Style.RESET_ALL}")
        
        return spot_amount, futures_contracts, balance
    
    def test_1_create_imbalance_spot(self):
        """테스트 1: 현물 일부 매도하여 불균형 생성"""
        print(f"\n{Fore.CYAN}[테스트 1] 현물 일부 매도 - 불균형 생성{Style.RESET_ALL}")
        print("-" * 40)
        
        # Check current state
        spot_amount, futures_contracts, balance = self.check_current_state()
        
        if spot_amount < 1:
            print(f"{Fore.RED}현물 보유량 부족. 먼저 헤지 포지션을 생성하세요.{Style.RESET_ALL}")
            return False
        
        # Sell 1 IP from spot
        sell_amount = 1.0
        print(f"\n{Fore.YELLOW}빗썸에서 {sell_amount} {self.symbol} 매도 중...{Style.RESET_ALL}")
        
        order = self.bithumb.create_market_order(
            symbol=f"{self.symbol}/KRW",
            side='sell',
            amount=sell_amount
        )
        
        if order:
            print(f"{Fore.GREEN}✓ 매도 완료{Style.RESET_ALL}")
            time.sleep(3)  # Wait for exchange
            
            # Check new balance
            print(f"\n{Fore.YELLOW}매도 후 상태:{Style.RESET_ALL}")
            new_spot, new_futures, new_balance = self.check_current_state()
            
            if new_balance and not new_balance.is_balanced:
                print(f"\n{Fore.GREEN}✓ 불균형 생성 성공!{Style.RESET_ALL}")
                print(f"  이전: 현물 {spot_amount:.6f} / 선물 {futures_contracts}")
                print(f"  현재: 현물 {new_spot:.6f} / 선물 {new_futures}")
                return True
        
        print(f"{Fore.RED}✗ 매도 실패{Style.RESET_ALL}")
        return False
    
    def test_2_create_imbalance_futures(self):
        """테스트 2: 선물 일부 청산하여 불균형 생성"""
        print(f"\n{Fore.CYAN}[테스트 2] 선물 일부 청산 - 불균형 생성{Style.RESET_ALL}")
        print("-" * 40)
        
        # Check current state
        spot_amount, futures_contracts, balance = self.check_current_state()
        
        if futures_contracts < 1:
            print(f"{Fore.RED}선물 포지션 부족. 먼저 헤지 포지션을 생성하세요.{Style.RESET_ALL}")
            return False
        
        # Close 1 contract from futures
        close_contracts = 1
        print(f"\n{Fore.YELLOW}Gate.io에서 {close_contracts} contract 청산 중...{Style.RESET_ALL}")
        
        # Get contract size
        markets = self.gateio.get_markets()
        contract_size = markets.get(f"{self.symbol}/USDT:USDT", {}).get('contract_size', 1)
        close_amount = close_contracts * contract_size
        
        order = self.gateio.create_market_order(
            symbol=f"{self.symbol}/USDT:USDT",
            side='buy',  # Buy to close short
            amount=close_amount,
            params={'reduce_only': True}
        )
        
        if order:
            print(f"{Fore.GREEN}✓ 청산 완료{Style.RESET_ALL}")
            time.sleep(3)  # Wait for exchange
            
            # Check new balance
            print(f"\n{Fore.YELLOW}청산 후 상태:{Style.RESET_ALL}")
            new_spot, new_futures, new_balance = self.check_current_state()
            
            if new_balance and not new_balance.is_balanced:
                print(f"\n{Fore.GREEN}✓ 불균형 생성 성공!{Style.RESET_ALL}")
                print(f"  이전: 현물 {spot_amount:.6f} / 선물 {futures_contracts}")
                print(f"  현재: 현물 {new_spot:.6f} / 선물 {new_futures}")
                return True
        
        print(f"{Fore.RED}✗ 청산 실패{Style.RESET_ALL}")
        return False
    
    def test_3_automatic_rebalancing(self):
        """테스트 3: 자동 리밸런싱"""
        print(f"\n{Fore.CYAN}[테스트 3] 자동 리밸런싱{Style.RESET_ALL}")
        print("-" * 40)
        
        # Check current balance
        balance = self.position_balancer.check_position_balance(self.symbol)
        
        if not balance:
            print(f"{Fore.RED}포지션 확인 실패{Style.RESET_ALL}")
            return False
        
        print(f"현재 상태:")
        print(f"  현물: {balance.spot_quantity:.6f} {self.symbol}")
        print(f"  선물: {balance.futures_quantity:.6f} {self.symbol}")
        print(f"  차이: {balance.gap_percentage:.2f}%")
        
        if balance.is_balanced:
            print(f"{Fore.YELLOW}이미 균형 상태입니다. 리밸런싱 불필요.{Style.RESET_ALL}")
            return True
        
        if not balance.needs_rebalancing:
            print(f"{Fore.YELLOW}차이가 2% 미만. 리밸런싱 임계값 미달.{Style.RESET_ALL}")
            print(f"  현재 차이: {balance.gap_percentage:.2f}%")
            print(f"  임계값: 2%")
            return True
        
        # Execute rebalancing
        print(f"\n{Fore.YELLOW}리밸런싱 실행 중...{Style.RESET_ALL}")
        success = self.position_balancer.rebalance_position(self.symbol)
        
        if success:
            print(f"{Fore.GREEN}✓ 리밸런싱 성공!{Style.RESET_ALL}")
            time.sleep(3)
            
            # Check new balance
            new_balance = self.position_balancer.check_position_balance(self.symbol)
            if new_balance:
                print(f"\n리밸런싱 후:")
                print(f"  현물: {new_balance.spot_quantity:.6f} {self.symbol}")
                print(f"  선물: {new_balance.futures_quantity:.6f} {self.symbol}")
                print(f"  차이: {new_balance.gap_percentage:.2f}%")
                
                if new_balance.is_balanced:
                    print(f"\n{Fore.GREEN}✓ 균형 복구 완료!{Style.RESET_ALL}")
            
            return True
        else:
            print(f"{Fore.RED}✗ 리밸런싱 실패{Style.RESET_ALL}")
            return False
    
    def test_4_partial_close_with_balance(self):
        """테스트 4: 부분 청산 후 균형 조정"""
        print(f"\n{Fore.CYAN}[테스트 4] 부분 청산 후 균형 조정{Style.RESET_ALL}")
        print("-" * 40)
        
        # Check current position
        position = self.position_manager.get_position(self.symbol)
        spot_amount, futures_contracts, balance = self.check_current_state()
        
        if spot_amount < 2 or futures_contracts < 2:
            print(f"{Fore.YELLOW}포지션이 너무 작습니다. 테스트 건너뜀.{Style.RESET_ALL}")
            return True
        
        # Calculate position value
        ticker = self.bithumb.get_ticker(f"{self.symbol}/KRW")
        usdt_ticker = self.bithumb.get_ticker('USDT/KRW')
        if ticker and usdt_ticker:
            position_value_krw = spot_amount * ticker['last']
            position_value_usd = position_value_krw / usdt_ticker['ask']
        else:
            position_value_usd = 100  # Default estimate
        
        # Close 50% of position
        print(f"\n{Fore.YELLOW}50% 포지션 청산 중...{Style.RESET_ALL}")
        print(f"  예상 청산량: {spot_amount * 0.5:.6f} {self.symbol}")
        
        success = self.order_executor.close_position_percentage(
            symbol=self.symbol,
            percentage=50,
            position_value_usd=position_value_usd
        )
        
        if success:
            print(f"{Fore.GREEN}✓ 50% 청산 성공{Style.RESET_ALL}")
            time.sleep(3)
            
            # Check balance after close
            print(f"\n{Fore.YELLOW}청산 후 균형 확인...{Style.RESET_ALL}")
            new_balance = self.position_balancer.check_position_balance(self.symbol)
            
            if new_balance and not new_balance.is_balanced:
                print(f"  불균형 감지: {new_balance.gap_percentage:.2f}%")
                print(f"\n{Fore.YELLOW}균형 조정 중...{Style.RESET_ALL}")
                
                # Execute balance adjustment
                adjust_success = self.position_balancer.balance_after_close(
                    symbol=self.symbol,
                    close_percentage=50
                )
                
                if adjust_success:
                    print(f"{Fore.GREEN}✓ 균형 조정 완료{Style.RESET_ALL}")
                    
                    # Final check
                    final_balance = self.position_balancer.check_position_balance(self.symbol)
                    if final_balance:
                        print(f"\n최종 상태:")
                        print(f"  현물: {final_balance.spot_quantity:.6f} {self.symbol}")
                        print(f"  선물: {final_balance.futures_quantity:.6f} {self.symbol}")
                        print(f"  차이: {final_balance.gap_percentage:.2f}%")
                else:
                    print(f"{Fore.RED}✗ 균형 조정 실패{Style.RESET_ALL}")
            else:
                print(f"{Fore.GREEN}✓ 청산 후에도 균형 유지{Style.RESET_ALL}")
            
            return True
        else:
            print(f"{Fore.RED}✗ 청산 실패{Style.RESET_ALL}")
            return False
    
    def test_5_stress_test(self):
        """테스트 5: 스트레스 테스트 - 여러 번 불균형 생성 및 복구"""
        print(f"\n{Fore.CYAN}[테스트 5] 스트레스 테스트{Style.RESET_ALL}")
        print("-" * 40)
        
        iterations = 3
        print(f"{iterations}회 반복 테스트")
        
        for i in range(iterations):
            print(f"\n{Fore.YELLOW}=== 반복 {i+1}/{iterations} ==={Style.RESET_ALL}")
            
            # Create imbalance
            if i % 2 == 0:
                # Sell spot
                print("현물 0.5개 매도...")
                self.bithumb.create_market_order(
                    symbol=f"{self.symbol}/KRW",
                    side='sell',
                    amount=0.5
                )
            else:
                # Add futures
                print("선물 1 contract 추가...")
                self.gateio.create_market_order(
                    symbol=f"{self.symbol}/USDT:USDT",
                    side='sell',
                    amount=1  # 1 IP
                )
            
            time.sleep(2)
            
            # Check balance
            balance = self.position_balancer.check_position_balance(self.symbol)
            if balance:
                print(f"  차이: {balance.gap_percentage:.2f}%")
                
                if not balance.is_balanced and balance.needs_rebalancing:
                    # Rebalance
                    print("  리밸런싱 실행...")
                    success = self.position_balancer.rebalance_position(self.symbol)
                    if success:
                        print(f"  {Fore.GREEN}✓ 리밸런싱 성공{Style.RESET_ALL}")
                    else:
                        print(f"  {Fore.RED}✗ 리밸런싱 실패{Style.RESET_ALL}")
                    
                    time.sleep(2)
        
        # Final state
        print(f"\n{Fore.YELLOW}최종 상태 확인...{Style.RESET_ALL}")
        self.check_current_state()
        
        return True
    
    def run_all_tests(self):
        """모든 테스트 실행"""
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"포지션 밸런싱 종합 테스트 시작")
        print(f"시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}{Style.RESET_ALL}\n")
        
        # Initial state
        print(f"{Fore.YELLOW}초기 상태 확인...{Style.RESET_ALL}")
        initial_spot, initial_futures, initial_balance = self.check_current_state()
        
        if initial_spot < 3 or initial_futures < 3:
            print(f"\n{Fore.YELLOW}테스트를 위한 충분한 포지션이 없습니다.{Style.RESET_ALL}")
            print(f"먼저 헤지 포지션을 생성하세요. (최소 3 IP 필요)")
            return
        
        tests = [
            ("현물 매도 불균형", self.test_1_create_imbalance_spot),
            ("리밸런싱", self.test_3_automatic_rebalancing),
            ("선물 청산 불균형", self.test_2_create_imbalance_futures),
            ("리밸런싱", self.test_3_automatic_rebalancing),
            ("부분 청산", self.test_4_partial_close_with_balance),
            # ("스트레스 테스트", self.test_5_stress_test),
        ]
        
        results = []
        for test_name, test_func in tests:
            try:
                print(f"\n{Fore.CYAN}>>> {test_name}{Style.RESET_ALL}")
                success = test_func()
                results.append((test_name, success))
                
                # Wait between tests
                print(f"\n{Fore.YELLOW}다음 테스트까지 5초 대기...{Style.RESET_ALL}")
                time.sleep(5)
                
            except Exception as e:
                print(f"\n{Fore.RED}테스트 중 오류: {e}{Style.RESET_ALL}")
                logger.exception(f"Test error in {test_name}")
                results.append((test_name, False))
        
        # Summary
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"테스트 결과 요약")
        print(f"{'='*60}{Style.RESET_ALL}\n")
        
        for test_name, success in results:
            status = f"{Fore.GREEN}✓ 성공{Style.RESET_ALL}" if success else f"{Fore.RED}✗ 실패{Style.RESET_ALL}"
            print(f"  {test_name}: {status}")
        
        # Final state
        print(f"\n{Fore.YELLOW}최종 상태:{Style.RESET_ALL}")
        final_spot, final_futures, final_balance = self.check_current_state()
        
        print(f"\n{Fore.GREEN}{'='*60}")
        print(f"테스트 완료!")
        print(f"{'='*60}{Style.RESET_ALL}\n")

def main():
    """Main test function"""
    test = PositionBalanceTest()
    
    print(f"\n{Fore.YELLOW}경고: 실제 거래가 실행됩니다!{Style.RESET_ALL}")
    print(f"테스트 코인: IP")
    print(f"필요 조건: 최소 3 IP 헤지 포지션")
    print(f"테스트 내용:")
    print(f"  1. 불균형 생성 (현물/선물 일부 매도)")
    print(f"  2. 자동 리밸런싱")
    print(f"  3. 부분 청산 후 균형 조정")
    
    response = input(f"\n계속하시겠습니까? (yes/no): ")
    if response.lower() != 'yes':
        print(f"{Fore.RED}테스트 취소{Style.RESET_ALL}")
        return
    
    test.run_all_tests()

if __name__ == "__main__":
    main()