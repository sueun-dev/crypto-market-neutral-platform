#!/usr/bin/env python3
"""
Position Verification Test
Verify current positions on Bithumb and Gate.io
Expected: Bithumb 2.995 XRP, Gate.io 3 XRP short
"""

import sys
import os
import asyncio
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.exchanges.bithumb import BithumbExchange
from src.exchanges.gateio import GateIOExchange
from src.config.settings import settings

async def verify_positions():
    """Verify current positions on both exchanges"""
    print("\n" + "=" * 60)
    print("🔍 Position Verification Test")
    print("=" * 60)
    
    # Initialize exchanges
    try:
        print("Initializing exchanges...")
        bithumb = BithumbExchange(
            api_key=os.getenv('BITHUMB_API_KEY'),
            api_secret=os.getenv('BITHUMB_API_SECRET')
        )
        
        gateio = GateIOExchange({
            'apiKey': os.getenv('GATEIO_API_KEY'),
            'secret': os.getenv('GATEIO_API_SECRET'),
            'settle': 'usdt'
        })
        
        print("✓ Exchanges initialized")
    except Exception as e:
        print(f"✗ Failed to initialize exchanges: {e}")
        return False
    
    test_passed = True
    results = []
    
    # Check Bithumb XRP balance
    try:
        print("\nChecking Bithumb XRP balance...")
        bithumb_balance = bithumb.get_balance("XRP")
        
        if bithumb_balance:
            xrp_quantity = bithumb_balance.get('free', 0) + bithumb_balance.get('used', 0)
            expected_xrp = 2.995
            
            # Check if within reasonable range (±0.01 for rounding)
            if abs(xrp_quantity - expected_xrp) < 0.01:
                status = "✓ PASS"
            else:
                status = "✗ FAIL"
                test_passed = False
            
            results.append({
                'exchange': 'Bithumb',
                'symbol': 'XRP',
                'type': 'Spot',
                'quantity': f"{xrp_quantity:.3f}",
                'expected': f"{expected_xrp:.3f}",
                'status': status
            })
            
            print(f"Bithumb XRP: {xrp_quantity:.3f} (Expected: {expected_xrp:.3f}) - {status}")
        else:
            print("✗ Failed to get Bithumb balance")
            results.append({
                'exchange': 'Bithumb',
                'symbol': 'XRP',
                'type': 'Spot',
                'quantity': 'N/A',
                'expected': '2.995',
                'status': '✗ ERROR'
            })
            test_passed = False
            
    except Exception as e:
        print(f"✗ Error checking Bithumb: {e}")
        results.append({
            'exchange': 'Bithumb',
            'symbol': 'XRP',
            'type': 'Spot',
            'quantity': 'ERROR',
            'expected': '2.995',
            'status': '✗ ERROR'
        })
        test_passed = False
    
    # Check Gate.io XRP futures position
    try:
        print("\nChecking Gate.io XRP futures positions...")
        positions = gateio.get_positions()
        
        xrp_position = None
        if positions:
            for pos in positions:
                if pos.get('symbol') == 'XRP/USDT:USDT':
                    xrp_position = pos
                    break
        
        if xrp_position:
            xrp_contracts = abs(xrp_position.get('contracts', 0))
            expected_contracts = 3
            side = xrp_position.get('side', 'unknown')
            
            # Check position
            if xrp_contracts == expected_contracts and side == 'short':
                status = "✓ PASS"
            else:
                status = "✗ FAIL"
                test_passed = False
            
            results.append({
                'exchange': 'Gate.io',
                'symbol': 'XRP',
                'type': f'Futures ({side})',
                'quantity': str(xrp_contracts),
                'expected': f'{expected_contracts} (short)',
                'status': status
            })
            
            print(f"Gate.io XRP: {xrp_contracts} contracts ({side}) (Expected: {expected_contracts} short) - {status}")
        else:
            print("⚠ No XRP position found on Gate.io")
            results.append({
                'exchange': 'Gate.io',
                'symbol': 'XRP',
                'type': 'Futures',
                'quantity': '0',
                'expected': '3 (short)',
                'status': '⚠ NO POSITION'
            })
            test_passed = False
            
    except Exception as e:
        print(f"✗ Error checking Gate.io: {e}")
        results.append({
            'exchange': 'Gate.io',
            'symbol': 'XRP',
            'type': 'Futures',
            'quantity': 'ERROR',
            'expected': '3 (short)',
            'status': '✗ ERROR'
        })
        test_passed = False
    
    # Print results table
    print("\n" + "=" * 60)
    print("Test Results:")
    print("-" * 60)
    print(f"{'Exchange':<15} {'Symbol':<10} {'Type':<20} {'Quantity':<15} {'Expected':<15} {'Status':<10}")
    print("-" * 60)
    for result in results:
        print(f"{result['exchange']:<15} {result['symbol']:<10} {result['type']:<20} {result['quantity']:<15} {result['expected']:<15} {result['status']:<10}")
    
    # Summary
    print("=" * 60)
    if test_passed:
        print("✓ POSITION VERIFICATION PASSED")
        print("All positions match expected values")
    else:
        print("✗ POSITION VERIFICATION FAILED")
        print("Positions do not match expected values")
    
    return test_passed

if __name__ == "__main__":
    result = asyncio.run(verify_positions())
    sys.exit(0 if result else 1)