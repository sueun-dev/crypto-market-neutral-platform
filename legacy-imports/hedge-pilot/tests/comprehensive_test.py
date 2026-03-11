#!/usr/bin/env python3
"""
Comprehensive Test Suite for Redflag Hedge Bot
Based on TEST_DOCUMENTATION.md
"""

import sys
import os
import asyncio
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.exchanges.bithumb import BithumbExchange
from src.exchanges.gateio import GateIOExchange
from src.core.hedge_bot import HedgeBot
from src.core.order_executor import OrderExecutor
from src.core.position_balancer import PositionBalancer
from src.core.premium_calculator import PremiumCalculator
from src.managers.position_manager import PositionManager
from src.managers.timer_manager import TimerManager
from src.config.settings import settings

class ComprehensiveTestSuite:
    """Complete test suite as specified in TEST_DOCUMENTATION.md"""
    
    def __init__(self):
        self.test_results = []
        self.failed_tests = []
        self.passed_tests = []
        self.symbol = "IP"  # Test with IP as in documentation
        
    def initialize_exchanges(self) -> Tuple[BithumbExchange, GateIOExchange]:
        """Initialize both exchanges"""
        try:
            bithumb = BithumbExchange(
                api_key=os.getenv('BITHUMB_API_KEY'),
                api_secret=os.getenv('BITHUMB_API_SECRET')
            )
            
            gateio = GateIOExchange({
                'apiKey': os.getenv('GATEIO_API_KEY'),
                'secret': os.getenv('GATEIO_API_SECRET'),
                'settle': 'usdt'
            })
            
            print("✓ Exchanges initialized successfully")
            return bithumb, gateio
        except Exception as e:
            print(f"✗ Failed to initialize exchanges: {e}")
            return None, None
    
    def test_hedge_bot_init(self, bithumb, gateio):
        """Test 1.1: HedgeBot initialization"""
        test_name = "HedgeBot.__init__"
        try:
            bot = HedgeBot(bithumb, gateio)
            
            # Test normal initialization
            assert bot.korean_exchange == bithumb
            assert bot.futures_exchange == gateio
            assert len(bot.symbols) == 0
            assert isinstance(bot.position_manager, PositionManager)
            assert isinstance(bot.timer_manager, TimerManager)
            
            self.record_result(test_name, True, "Normal initialization successful")
            
            # Test None exchange (should fail)
            try:
                bot_fail = HedgeBot(None, None)
                self.record_result(f"{test_name}_none", False, "Should have raised error for None exchanges")
            except:
                self.record_result(f"{test_name}_none", True, "Correctly rejected None exchanges")
                
        except Exception as e:
            self.record_result(test_name, False, str(e))
    
    def test_add_symbol(self, bithumb, gateio):
        """Test 1.2: Adding symbols to HedgeBot"""
        test_name = "HedgeBot.add_symbol"
        try:
            bot = HedgeBot(bithumb, gateio)
            
            # Test valid symbol
            result = bot.add_symbol(self.symbol)
            assert result == True
            assert self.symbol in bot.symbols
            
            self.record_result(test_name, True, f"Successfully added {self.symbol}")
            
            # Test invalid symbol
            result_invalid = bot.add_symbol("FAKECOIN")
            if not result_invalid:
                self.record_result(f"{test_name}_invalid", True, "Correctly rejected invalid symbol")
            else:
                self.record_result(f"{test_name}_invalid", False, "Should have rejected FAKECOIN")
                
        except Exception as e:
            self.record_result(test_name, False, str(e))
    
    def test_premium_calculation(self, bithumb, gateio):
        """Test 4.1: Premium calculation"""
        test_name = "PremiumCalculator.calculate"
        try:
            calculator = PremiumCalculator(bithumb, gateio)
            
            # Test normal premium calculation
            premium = calculator.calculate(self.symbol)
            
            if premium is not None:
                # Check reasonable range
                if -10 < premium < 100:
                    self.record_result(test_name, True, f"Premium calculated: {premium:.2f}%")
                else:
                    self.record_result(test_name, False, f"Premium out of range: {premium:.2f}%")
            else:
                self.record_result(test_name, False, "Failed to calculate premium")
                
        except Exception as e:
            self.record_result(test_name, False, str(e))
    
    def test_order_executor(self, bithumb, gateio):
        """Test 2.1: Order execution"""
        test_name = "OrderExecutor.execute_hedge_position"
        try:
            executor = OrderExecutor(bithumb, gateio)
            
            # Test small hedge position ($10)
            success = executor.execute_hedge_position(self.symbol, 10.0)
            
            if success:
                self.record_result(test_name, True, "Successfully executed $10 hedge position")
                
                # Wait for settlement
                time.sleep(3)
                
                # Test close position
                close_success = executor.close_position_percentage(self.symbol, 100, 10.0)
                if close_success:
                    self.record_result(f"{test_name}_close", True, "Successfully closed position")
                else:
                    self.record_result(f"{test_name}_close", False, "Failed to close position")
            else:
                self.record_result(test_name, False, "Failed to execute hedge position")
                
        except Exception as e:
            self.record_result(test_name, False, str(e))
    
    def test_position_balancer(self, bithumb, gateio):
        """Test 3.1: Position balance checking"""
        test_name = "PositionBalancer.check_position_balance"
        try:
            position_manager = PositionManager()
            order_executor = OrderExecutor(bithumb, gateio)
            balancer = PositionBalancer(position_manager, order_executor, bithumb, gateio)
            
            # Check current balance
            balance = balancer.check_position_balance(self.symbol)
            
            if balance:
                gap_pct = balance.gap_percentage
                self.record_result(test_name, True, 
                    f"Balance checked - Gap: {gap_pct:.2f}%, Balanced: {balance.is_balanced}")
            else:
                self.record_result(test_name, False, "Failed to check balance")
                
        except Exception as e:
            self.record_result(test_name, False, str(e))
    
    def test_position_manager(self, bithumb, gateio):
        """Test 5.1: Position management"""
        test_name = "PositionManager.get_existing_positions"
        try:
            manager = PositionManager()
            
            # Get existing positions
            value = manager.get_existing_positions(self.symbol, bithumb, gateio)
            
            self.record_result(test_name, True, f"Existing position value: ${value:.2f}")
            
            # Test update
            manager.update_position(self.symbol, 10.0)
            position = manager.get_position(self.symbol)
            
            if position and position.value_usd >= 10.0:
                self.record_result(f"{test_name}_update", True, "Position updated successfully")
            else:
                self.record_result(f"{test_name}_update", False, "Failed to update position")
                
        except Exception as e:
            self.record_result(test_name, False, str(e))
    
    def test_timer_manager(self):
        """Test 6.1: Timer management"""
        test_name = "TimerManager.check_profit_taking"
        try:
            timer = TimerManager()
            timer.initialize_symbol(self.symbol)
            
            # Test first reach (should execute immediately)
            result = timer.check_profit_taking(self.symbol, 10.5, settings.PROFIT_STAGES)
            
            if result == (10, 10):
                self.record_result(test_name, True, "Timer triggered correctly at 10% premium")
            else:
                self.record_result(test_name, False, f"Unexpected timer result: {result}")
                
            # Test cooldown
            result2 = timer.check_profit_taking(self.symbol, 10.5, settings.PROFIT_STAGES)
            if result2 is None:
                self.record_result(f"{test_name}_cooldown", True, "Cooldown working correctly")
            else:
                self.record_result(f"{test_name}_cooldown", False, "Cooldown not working")
                
        except Exception as e:
            self.record_result(test_name, False, str(e))
    
    def test_exchange_apis(self, bithumb, gateio):
        """Test 7.1 & 7.2: Exchange API functionality"""
        test_name = "Exchange_APIs"
        
        # Test Bithumb
        try:
            # Get ticker
            ticker = bithumb.get_ticker(f"{self.symbol}/KRW")
            if ticker and 'last' in ticker:
                self.record_result(f"{test_name}_bithumb_ticker", True, 
                    f"Bithumb ticker: {ticker['last']:,.0f} KRW")
            
            # Get balance
            balance = bithumb.get_balance(self.symbol)
            if balance:
                self.record_result(f"{test_name}_bithumb_balance", True, 
                    f"Bithumb balance: {balance.get('free', 0):.6f} {self.symbol}")
                    
        except Exception as e:
            self.record_result(f"{test_name}_bithumb", False, str(e))
        
        # Test Gate.io
        try:
            # Get ticker
            ticker = gateio.get_ticker(f"{self.symbol}/USDT:USDT")
            if ticker and 'last' in ticker:
                self.record_result(f"{test_name}_gateio_ticker", True, 
                    f"Gate.io ticker: ${ticker['last']:.4f}")
            
            # Get positions
            positions = gateio.get_positions()
            self.record_result(f"{test_name}_gateio_positions", True, 
                f"Gate.io positions retrieved: {len(positions)} active")
                
        except Exception as e:
            self.record_result(f"{test_name}_gateio", False, str(e))
    
    def test_integration_scenario(self, bithumb, gateio):
        """Integration test: Complete hedge lifecycle"""
        test_name = "Integration_Complete_Lifecycle"
        try:
            bot = HedgeBot(bithumb, gateio)
            
            # Add symbol
            bot.add_symbol(self.symbol)
            
            # Process symbol (will check premium and potentially build position)
            bot.process_symbol(self.symbol)
            
            # Run one cycle
            result = bot.run_cycle()
            
            if result:
                self.record_result(test_name, True, "Complete lifecycle executed successfully")
            else:
                self.record_result(test_name, False, "Lifecycle execution failed")
                
        except Exception as e:
            self.record_result(test_name, False, str(e))
    
    def record_result(self, test_name: str, passed: bool, message: str):
        """Record test result"""
        result = {
            'test': test_name,
            'passed': passed,
            'message': message,
            'timestamp': datetime.now()
        }
        self.test_results.append(result)
        
        if passed:
            self.passed_tests.append(test_name)
            print(f"✓ {test_name}: {message}")
        else:
            self.failed_tests.append(test_name)
            print(f"✗ {test_name}: {message}")
    
    def run_all_tests(self):
        """Run all tests in sequence"""
        print("\n" + "=" * 60)
        print("COMPREHENSIVE TEST SUITE EXECUTION")
        print("Based on TEST_DOCUMENTATION.md")
        print("=" * 60 + "\n")
        
        # Initialize exchanges
        bithumb, gateio = self.initialize_exchanges()
        if not bithumb or not gateio:
            print("Cannot proceed without exchanges")
            return False
        
        # Run test phases
        print("\n[Phase 1: Basic Functionality]")
        print("-" * 40)
        self.test_exchange_apis(bithumb, gateio)
        self.test_premium_calculation(bithumb, gateio)
        
        print("\n[Phase 2: Core Functionality]")
        print("-" * 40)
        self.test_hedge_bot_init(bithumb, gateio)
        self.test_add_symbol(bithumb, gateio)
        self.test_order_executor(bithumb, gateio)
        self.test_position_balancer(bithumb, gateio)
        
        print("\n[Phase 3: Advanced Functionality]")
        print("-" * 40)
        self.test_position_manager(bithumb, gateio)
        self.test_timer_manager()
        
        print("\n[Phase 4: Integration Tests]")
        print("-" * 40)
        self.test_integration_scenario(bithumb, gateio)
        
        # Generate report
        self.generate_report()
        
        return len(self.failed_tests) == 0
    
    def generate_report(self):
        """Generate comprehensive test report"""
        print("\n" + "=" * 60)
        print("TEST EXECUTION REPORT")
        print("=" * 60)
        
        total_tests = len(self.test_results)
        passed = len(self.passed_tests)
        failed = len(self.failed_tests)
        
        print(f"\nTotal Tests: {total_tests}")
        print(f"Passed: {passed} ({passed/total_tests*100:.1f}%)")
        print(f"Failed: {failed} ({failed/total_tests*100:.1f}%)")
        
        if self.failed_tests:
            print("\n[Failed Tests]")
            for test in self.failed_tests:
                result = next(r for r in self.test_results if r['test'] == test)
                print(f"  ✗ {test}: {result['message']}")
        
        if self.passed_tests:
            print("\n[Passed Tests]")
            for test in self.passed_tests:
                print(f"  ✓ {test}")
        
        # Analysis of issues
        print("\n[Analysis]")
        print("-" * 40)
        
        # Check for logical errors
        logical_errors = []
        
        # Check position balance issues
        balance_tests = [r for r in self.test_results if 'balance' in r['test'].lower()]
        if any(not r['passed'] for r in balance_tests):
            logical_errors.append("Position balancing logic may have issues")
        
        # Check order execution issues
        order_tests = [r for r in self.test_results if 'order' in r['test'].lower() or 'executor' in r['test'].lower()]
        if any(not r['passed'] for r in order_tests):
            logical_errors.append("Order execution flow needs review")
        
        # Check API issues
        api_tests = [r for r in self.test_results if 'api' in r['test'].lower() or 'exchange' in r['test'].lower()]
        if any(not r['passed'] for r in api_tests):
            logical_errors.append("Exchange API integration issues detected")
        
        if logical_errors:
            print("\n[Identified Issues]")
            for i, error in enumerate(logical_errors, 1):
                print(f"  {i}. {error}")
        else:
            print("\n✓ No major logical errors detected")
        
        print("\n" + "=" * 60)
        print("END OF REPORT")
        print("=" * 60)

def main():
    """Main execution"""
    suite = ComprehensiveTestSuite()
    success = suite.run_all_tests()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()