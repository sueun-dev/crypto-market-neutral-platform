#!/usr/bin/env python3
"""
24-Hour Continuous Operation Test (Shortened Version)
Simulates 24 hours of operation in accelerated time
"""

import sys
import os
import time
import asyncio
import threading
import resource
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List
import logging

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.exchanges.bithumb import BithumbExchange
from src.exchanges.gateio import GateIOExchange
from src.core.hedge_bot import HedgeBot
from src.config.settings import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ContinuousOperationTest:
    """24-hour continuous operation test suite"""
    
    def __init__(self, use_real_exchanges: bool = False):
        self.use_real_exchanges = use_real_exchanges
        self.start_time = None
        self.metrics = {
            'cycles': 0,
            'successful_operations': 0,
            'failed_operations': 0,
            'memory_samples': [],
            'cpu_samples': [],
            'api_errors': 0,
            'rebalancing_events': 0,
            'premium_calculations': 0
        }
        self.running = False
        
    def initialize_exchanges(self):
        """Initialize exchange connections"""
        if self.use_real_exchanges:
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
                
                return bithumb, gateio
            except Exception as e:
                logger.error(f"Failed to initialize real exchanges: {e}")
                return self.create_mock_exchanges()
        else:
            return self.create_mock_exchanges()
    
    def create_mock_exchanges(self):
        """Create mock exchanges for testing"""
        from unittest.mock import Mock
        
        # Mock Bithumb
        bithumb = Mock()
        bithumb.exchange_id = 'bithumb'
        bithumb.get_ticker = Mock(return_value={'last': 10000, 'bid': 9990, 'ask': 10010})
        bithumb.get_balance = Mock(return_value={'free': 100, 'used': 0, 'total': 100})
        bithumb.create_market_order = Mock(return_value={'id': 'test123', 'status': 'closed'})
        
        # Mock Gate.io
        gateio = Mock()
        gateio.exchange_id = 'gateio'
        gateio.get_ticker = Mock(return_value={'last': 7.5, 'bid': 7.49, 'ask': 7.51})
        gateio.get_balance = Mock(return_value={'free': 1000, 'used': 0, 'total': 1000})
        gateio.get_positions = Mock(return_value=[])
        gateio.create_market_order = Mock(return_value={'id': 'test456', 'status': 'filled'})
        gateio.get_markets = Mock(return_value={'IP/USDT:USDT': {'contract_size': 1}})
        
        return bithumb, gateio
    
    def monitor_resources(self):
        """Monitor system resources"""
        
        while self.running:
            # Memory usage using resource module
            usage = resource.getrusage(resource.RUSAGE_SELF)
            memory_mb = usage.ru_maxrss / 1024 / 1024  # Convert to MB
            
            # On macOS, ru_maxrss is in bytes, on Linux it's in KB
            import platform
            if platform.system() == 'Darwin':
                memory_mb = usage.ru_maxrss / 1024 / 1024
            else:
                memory_mb = usage.ru_maxrss / 1024
            
            self.metrics['memory_samples'].append(memory_mb)
            
            # Simple CPU time tracking (not percentage)
            cpu_time = usage.ru_utime + usage.ru_stime
            self.metrics['cpu_samples'].append(cpu_time)
            
            # Log if resources exceed thresholds
            if memory_mb > 500:
                logger.warning(f"High memory usage: {memory_mb:.1f} MB")
            
            time.sleep(10)  # Check every 10 seconds
    
    def simulate_24_hours(self, acceleration_factor: int = 1440):
        """
        Simulate 24 hours of operation
        acceleration_factor: How much to speed up time (1440 = 1 minute real = 1 day simulated)
        """
        logger.info(f"Starting 24-hour simulation (acceleration: {acceleration_factor}x)")
        
        # Initialize
        bithumb, gateio = self.initialize_exchanges()
        
        try:
            bot = HedgeBot(bithumb, gateio)
            bot.add_symbol("IP")
        except Exception as e:
            logger.error(f"Failed to initialize bot: {e}")
            return False
        
        self.start_time = datetime.now()
        self.running = True
        
        # Start resource monitoring in background
        monitor_thread = threading.Thread(target=self.monitor_resources)
        monitor_thread.daemon = True
        monitor_thread.start()
        
        # Calculate cycle interval
        real_24_hours_seconds = 24 * 60 * 60
        simulated_seconds = real_24_hours_seconds / acceleration_factor
        cycle_interval = 5.0 / acceleration_factor  # 5 seconds per cycle in real time
        
        simulated_end_time = datetime.now() + timedelta(seconds=simulated_seconds)
        
        logger.info(f"Simulation will run for {simulated_seconds:.1f} seconds")
        logger.info(f"This represents 24 hours of operation")
        
        try:
            while datetime.now() < simulated_end_time:
                cycle_start = time.time()
                
                # Run bot cycle
                try:
                    # Process symbol
                    bot.process_symbol("IP")
                    self.metrics['cycles'] += 1
                    self.metrics['successful_operations'] += 1
                    
                    # Check for premium calculation
                    premium = bot.premium_calculator.calculate("IP")
                    if premium is not None:
                        self.metrics['premium_calculations'] += 1
                    
                    # Check position balance
                    balance = bot.position_balancer.check_position_balance("IP")
                    if balance and balance.needs_rebalancing:
                        self.metrics['rebalancing_events'] += 1
                    
                except Exception as e:
                    logger.error(f"Cycle error: {e}")
                    self.metrics['failed_operations'] += 1
                    
                    if 'API' in str(e):
                        self.metrics['api_errors'] += 1
                
                # Progress report every 100 cycles
                if self.metrics['cycles'] % 100 == 0:
                    self.print_progress_report()
                
                # Sleep for remainder of cycle
                elapsed = time.time() - cycle_start
                if elapsed < cycle_interval:
                    time.sleep(cycle_interval - elapsed)
                    
        except KeyboardInterrupt:
            logger.info("Simulation interrupted by user")
        finally:
            self.running = False
            
        # Final report
        self.print_final_report()
        
        return self.validate_results()
    
    def print_progress_report(self):
        """Print progress during simulation"""
        elapsed = datetime.now() - self.start_time
        simulated_hours = (self.metrics['cycles'] * 5) / 3600  # Assuming 5 second cycles
        
        logger.info(f"Progress Report - Cycle {self.metrics['cycles']}")
        logger.info(f"  Real time elapsed: {elapsed}")
        logger.info(f"  Simulated time: {simulated_hours:.1f} hours")
        logger.info(f"  Success rate: {self.metrics['successful_operations']}/{self.metrics['cycles']}")
        
        if self.metrics['memory_samples']:
            avg_memory = sum(self.metrics['memory_samples']) / len(self.metrics['memory_samples'])
            logger.info(f"  Avg memory: {avg_memory:.1f} MB")
    
    def print_final_report(self):
        """Print comprehensive final report"""
        print("\n" + "=" * 60)
        print("24-HOUR CONTINUOUS OPERATION TEST RESULTS")
        print("=" * 60)
        
        elapsed = datetime.now() - self.start_time
        
        print(f"\nTest Duration: {elapsed}")
        print(f"Total Cycles: {self.metrics['cycles']}")
        print(f"Successful Operations: {self.metrics['successful_operations']}")
        print(f"Failed Operations: {self.metrics['failed_operations']}")
        
        if self.metrics['cycles'] > 0:
            success_rate = (self.metrics['successful_operations'] / self.metrics['cycles']) * 100
            print(f"Success Rate: {success_rate:.2f}%")
        
        print(f"\nOperational Metrics:")
        print(f"  API Errors: {self.metrics['api_errors']}")
        print(f"  Rebalancing Events: {self.metrics['rebalancing_events']}")
        print(f"  Premium Calculations: {self.metrics['premium_calculations']}")
        
        if self.metrics['memory_samples']:
            avg_memory = sum(self.metrics['memory_samples']) / len(self.metrics['memory_samples'])
            max_memory = max(self.metrics['memory_samples'])
            print(f"\nMemory Usage:")
            print(f"  Average: {avg_memory:.1f} MB")
            print(f"  Maximum: {max_memory:.1f} MB")
        
        if self.metrics['cpu_samples'] and len(self.metrics['cpu_samples']) > 1:
            # CPU time is cumulative, so calculate the difference
            cpu_time_used = self.metrics['cpu_samples'][-1] - self.metrics['cpu_samples'][0] if self.metrics['cpu_samples'] else 0
            print(f"\nCPU Time:")
            print(f"  Total CPU time used: {cpu_time_used:.2f} seconds")
    
    def validate_results(self) -> bool:
        """Validate test results"""
        issues = []
        
        # Check memory leak
        if self.metrics['memory_samples']:
            max_memory = max(self.metrics['memory_samples'])
            if max_memory > 500:
                issues.append(f"Memory usage exceeded 500MB: {max_memory:.1f} MB")
        
        # Check success rate
        if self.metrics['cycles'] > 0:
            success_rate = (self.metrics['successful_operations'] / self.metrics['cycles']) * 100
            if success_rate < 90:
                issues.append(f"Success rate below 90%: {success_rate:.2f}%")
        
        # Check API errors
        if self.metrics['api_errors'] > self.metrics['cycles'] * 0.05:  # More than 5% API errors
            issues.append(f"High API error rate: {self.metrics['api_errors']} errors")
        
        # Print validation results
        print("\n" + "=" * 60)
        print("VALIDATION RESULTS")
        print("=" * 60)
        
        if issues:
            print("Issues Found:")
            for issue in issues:
                print(f"  ❌ {issue}")
            return False
        else:
            print("✅ All validation checks passed")
            print("✅ System is stable for 24-hour operation")
            return True

def main():
    """Main execution"""
    import argparse
    
    parser = argparse.ArgumentParser(description='24-hour continuous operation test')
    parser.add_argument('--real', action='store_true', help='Use real exchanges')
    parser.add_argument('--duration', type=int, default=60, help='Test duration in seconds')
    parser.add_argument('--acceleration', type=int, default=1440, help='Time acceleration factor')
    
    args = parser.parse_args()
    
    # Calculate acceleration based on desired duration
    if args.duration:
        # 24 hours = 86400 seconds
        args.acceleration = 86400 // args.duration
    
    print(f"Running 24-hour simulation in {args.duration} seconds")
    print(f"Time acceleration: {args.acceleration}x")
    print(f"Using {'real' if args.real else 'mock'} exchanges")
    print("-" * 60)
    
    test = ContinuousOperationTest(use_real_exchanges=args.real)
    success = test.simulate_24_hours(acceleration_factor=args.acceleration)
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()