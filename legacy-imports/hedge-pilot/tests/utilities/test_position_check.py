#!/usr/bin/env python3
"""
포지션 균형 체크 테스트
"""

import sys
import os
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.exchanges.bithumb import BithumbExchange
from src.exchanges.gateio import GateIOExchange
from src.managers.position_manager import PositionManager
from src.core.order_executor import OrderExecutor
from src.core.position_balancer import PositionBalancer

# Load environment variables
load_dotenv()

def check_current_positions():
    """현재 포지션 체크"""
    
    print("\n" + "="*60)
    print("현재 포지션 균형 체크")
    print("="*60 + "\n")
    
    # Initialize exchanges
    bithumb = BithumbExchange(
        os.getenv('BITHUMB_API_KEY'),
        os.getenv('BITHUMB_API_SECRET')
    )
    
    gateio_creds = {
        'apiKey': os.getenv('GATEIO_API_KEY'),
        'secret': os.getenv('GATEIO_API_SECRET')
    }
    gateio = GateIOExchange(gateio_creds)
    
    # Initialize position balancer
    position_manager = PositionManager()
    order_executor = OrderExecutor(
        korean_exchange=bithumb,
        futures_exchange=gateio
    )
    position_balancer = PositionBalancer(
        position_manager=position_manager,
        order_executor=order_executor,
        korean_exchange=bithumb,
        futures_exchange=gateio
    )
    
    symbol = "IP"
    
    # 1. Check Bithumb balance
    print(f"[1] 빗썸 {symbol} 잔고")
    ip_balance = bithumb.get_balance(symbol)
    if ip_balance:
        print(f"  보유량: {ip_balance['free']:.6f} {symbol}")
    
    # 2. Check Gate.io positions
    print(f"\n[2] Gate.io 선물 포지션")
    positions = gateio.get_positions()
    for pos in positions:
        if symbol in pos.get('symbol', ''):
            print(f"  심볼: {pos['symbol']}")
            print(f"  방향: {pos['side']}")
            print(f"  계약수: {pos['contracts']}")
            print(f"  가치: ${abs(pos.get('notional', 0)):.2f}")
    
    # 3. Check position balance
    print(f"\n[3] 포지션 균형 체크")
    balance = position_balancer.check_position_balance(symbol)
    
    if balance:
        print(f"  현물 수량: {balance.spot_quantity:.6f} {symbol}")
        print(f"  선물 수량: {balance.futures_quantity:.6f} {symbol}")
        print(f"  수량 차이: {balance.quantity_gap:.6f} {symbol}")
        print(f"  차이 비율: {balance.gap_percentage:.2f}%")
        
        if balance.is_balanced:
            print(f"\n✅ 완벽한 헤지! (차이 1% 이내)")
        else:
            print(f"\n⚠️ 헤지 불균형: {balance.gap_percentage:.2f}%")
            
        print(f"\n[참고] USD 가치")
        print(f"  현물: ${balance.spot_value_usd:.2f}")
        print(f"  선물: ${balance.futures_value_usd:.2f}")
    else:
        print("  균형 체크 실패")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    check_current_positions()