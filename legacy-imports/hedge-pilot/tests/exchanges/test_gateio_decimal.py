#!/usr/bin/env python3
"""
Gate.io 소수점 계약 테스트
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import settings
from src.exchanges.gateio import GateIOExchange
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_decimal_contracts():
    """소수점 계약 주문 테스트"""
    
    # Initialize Gate.io
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    gateio = GateIOExchange({
        'apiKey': os.getenv('GATEIO_API_KEY'),
        'secret': os.getenv('GATEIO_API_SECRET')
    })
    
    # Get IP market info
    markets = gateio.get_markets()
    ip_market = markets.get("IP/USDT:USDT")
    
    if ip_market:
        print(f"IP 시장 정보:")
        print(f"  계약 크기: {ip_market['contract_size']}")
        print(f"  계약 이름: {ip_market['name']}")
    
    # Get current price
    ticker = gateio.get_ticker("IP/USDT:USDT")
    if ticker:
        print(f"\n현재 가격:")
        print(f"  Last: ${ticker['last']}")
        print(f"  Bid: ${ticker['bid']}")
        print(f"  Ask: ${ticker['ask']}")
    
    # Test 1: 정수 계약 (should work)
    print("\n테스트 1: 정수 계약 (10 contracts)")
    try:
        # Direct call without from_order_executor flag
        order1 = gateio.create_market_order(
            symbol="IP/USDT:USDT",
            side="sell",
            amount=10 * ip_market['contract_size']  # 10 contracts worth of IP
        )
        if order1:
            print(f"  ✓ 성공: {order1}")
        else:
            print("  ✗ 실패")
    except Exception as e:
        print(f"  ✗ 오류: {e}")
    
    # Test 2: 소수점 계약 테스트를 위한 수정
    print("\n테스트 2: 소수점 계약 테스트 - string '10.5'")
    
    # Temporarily modify gateio.py to accept decimal
    import gate_api
    
    try:
        # Create futures order with decimal size as string
        order = gate_api.FuturesOrder(
            contract="IP_USDT",
            size="-10.5",  # Try decimal contracts as STRING (negative for short)
            price='0',  # Market order
            tif='ioc',  # Immediate or cancel
            reduce_only=False
        )
        
        response = gateio.futures_api.create_futures_order('usdt', order)
        print(f"  ✓ 소수점 계약 성공: size={response.size}")
        
    except gate_api.exceptions.GateApiException as ex:
        print(f"  ✗ Gate API 오류: {ex.label}, {ex.message}")
        if "integer" in str(ex.message).lower() or "decimal" in str(ex.message).lower():
            print("  → Gate.io는 정수 계약만 지원함!")
    except Exception as e:
        print(f"  ✗ 일반 오류: {e}")
    
    # Check current positions
    print("\n현재 포지션:")
    positions = gateio.get_positions()
    for pos in positions:
        if 'IP' in pos.get('symbol', ''):
            print(f"  Symbol: {pos['symbol']}")
            print(f"  Side: {pos['side']}")
            print(f"  Contracts: {pos['contracts']}")
            print(f"  Notional: ${pos['notional']}")

if __name__ == "__main__":
    print("Gate.io 소수점 계약 테스트")
    print("=" * 50)
    test_decimal_contracts()