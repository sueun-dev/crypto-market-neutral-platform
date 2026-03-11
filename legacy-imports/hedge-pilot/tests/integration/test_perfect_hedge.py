#!/usr/bin/env python3
"""
완벽한 헤지 테스트 - Gate.io 계약수에 맞춘 주문
"""

import sys
import os
import time
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import settings
from src.exchanges.bithumb import BithumbExchange
from src.exchanges.gateio import GateIOExchange
from src.managers.position_manager import PositionManager
from src.core.order_executor import OrderExecutor
from src.core.position_balancer import PositionBalancer
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def test_perfect_hedge():
    """완벽한 헤지 테스트"""
    
    print("\n" + "="*60)
    print("완벽한 헤지 테스트 - Gate.io 계약수 기준")
    print("="*60 + "\n")
    
    # Initialize exchanges
    print("거래소 초기화 중...")
    
    bithumb = BithumbExchange(
        os.getenv('BITHUMB_API_KEY'),
        os.getenv('BITHUMB_API_SECRET')
    )
    
    gateio_creds = {
        'apiKey': os.getenv('GATEIO_API_KEY'),
        'secret': os.getenv('GATEIO_API_SECRET')
    }
    gateio = GateIOExchange(gateio_creds)
    
    # Initialize managers
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
    target_usd = 50.0  # 대략 $50 목표
    
    print(f"\n테스트 설정:")
    print(f"  심볼: {symbol}")
    print(f"  목표 금액: ${target_usd:.2f} (유동적)")
    print("-" * 40)
    
    # 1. Check current prices
    print("\n[1] 현재 가격 확인")
    bithumb_ticker = bithumb.get_ticker(f"{symbol}/KRW")
    gateio_ticker = gateio.get_ticker(f"{symbol}/USDT:USDT")
    
    if bithumb_ticker and gateio_ticker:
        print(f"  빗썸 {symbol}/KRW: {bithumb_ticker['last']:,.0f} KRW")
        print(f"  Gate.io {symbol}/USDT: ${gateio_ticker['last']:.4f}")
    
    # 2. Check contract info
    print("\n[2] Gate.io 계약 정보")
    markets = gateio.get_markets()
    ip_market = markets.get(f"{symbol}/USDT:USDT")
    if ip_market:
        print(f"  계약 크기: {ip_market['contract_size']} {symbol}")
        print(f"  1 contract = {ip_market['contract_size']} {symbol}")
    
    # 3. Check initial balances
    print("\n[3] 초기 잔고 확인")
    
    # Bithumb
    bithumb_ip = bithumb.get_balance(symbol)
    bithumb_krw = bithumb.get_balance('KRW')
    if bithumb_ip:
        print(f"  빗썸 {symbol}: {bithumb_ip['free']:.6f}")
    if bithumb_krw:
        print(f"  빗썸 KRW: {bithumb_krw['free']:,.0f}")
    
    # Gate.io
    gateio_usdt = gateio.get_balance('USDT')
    if gateio_usdt:
        print(f"  Gate.io USDT: ${gateio_usdt['free']:.2f}")
    
    # Check existing positions
    gateio_positions = gateio.get_positions()
    for pos in gateio_positions:
        if symbol in pos.get('symbol', ''):
            print(f"  기존 Gate.io 포지션: {pos['contracts']} contracts")
    
    # 4. Execute hedge position
    print(f"\n[4] 헤지 포지션 실행 (목표: ~${target_usd})")
    print("-" * 40)
    
    success = order_executor.execute_hedge_position(symbol, target_usd)
    
    if success:
        print("\n✓ 헤지 포지션 실행 성공!")
        
        # Wait for exchanges to process
        print("\n거래소 처리 대기 중...")
        time.sleep(5)
        
        # 5. Check position balance
        print("\n[5] 포지션 균형 확인")
        print("-" * 40)
        
        balance = position_balancer.check_position_balance(symbol)
        
        if balance:
            print(f"  현물 수량: {balance.spot_quantity:.6f} {symbol}")
            print(f"  선물 수량: {balance.futures_quantity:.6f} {symbol}")
            print(f"  수량 차이: {balance.quantity_gap:.6f} {symbol}")
            print(f"  차이 비율: {balance.gap_percentage:.2f}%")
            
            if balance.is_balanced:
                print("\n✓ 완벽한 헤지 달성! (1% 이내)")
            else:
                print(f"\n⚠ 헤지 불균형: {balance.gap_percentage:.2f}%")
        
        # 6. Check actual positions
        print("\n[6] 실제 포지션 상세")
        print("-" * 40)
        
        # Bithumb balance
        new_bithumb_ip = bithumb.get_balance(symbol)
        if new_bithumb_ip and bithumb_ip:
            bought = new_bithumb_ip['free'] - bithumb_ip['free']
            print(f"  빗썸 매수량: {bought:.6f} {symbol}")
        
        # Gate.io positions
        new_positions = gateio.get_positions()
        for pos in new_positions:
            if symbol in pos.get('symbol', ''):
                print(f"  Gate.io 숏: {abs(pos['contracts'])} contracts")
                print(f"  Gate.io 가치: ${abs(pos['notional']):.2f}")
        
        # 7. Final summary
        print("\n[7] 최종 요약")
        print("="*40)
        position = position_manager.get_position(symbol)
        if position:
            print(f"  포지션 가치: ${position.value_usd:.2f}")
            print(f"  Long (빗썸): ${position.long_value:.2f}")
            print(f"  Short (Gate.io): ${position.short_value:.2f}")
        
    else:
        print("\n✗ 헤지 포지션 실행 실패")
    
    print("\n" + "="*60)
    print("테스트 완료")
    print("="*60)

def cleanup_test_position():
    """테스트 포지션 청산"""
    print("\n테스트 포지션 청산 중...")
    
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
    
    symbol = "IP"
    
    # Clean up Bithumb
    ip_balance = bithumb.get_balance(symbol)
    if ip_balance and ip_balance['free'] > 0:
        print(f"빗썸 {symbol} 매도: {ip_balance['free']:.6f}")
        bithumb.create_market_order(
            symbol=f"{symbol}/KRW",
            side='sell',
            amount=ip_balance['free']
        )
    
    # Clean up Gate.io
    positions = gateio.get_positions()
    for pos in positions:
        if symbol in pos.get('symbol', ''):
            contracts = abs(pos['contracts'])
            print(f"Gate.io 포지션 청산: {contracts} contracts")
            gateio.create_market_order(
                symbol=f"{symbol}/USDT:USDT",
                side='buy',  # Buy to close short
                amount=contracts * pos.get('contract_size', 1),
                params={'reduce_only': True}
            )
    
    print("청산 완료")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'cleanup':
        cleanup_test_position()
    else:
        print("\n경고: 실제 거래가 실행됩니다!")
        print("테스트 코인: IP")
        print("목표 금액: ~$50 (유동적)")
        
        response = input("\n계속하시겠습니까? (yes/no): ")
        if response.lower() == 'yes':
            test_perfect_hedge()
            
            # Ask if cleanup needed
            response = input("\n포지션을 청산하시겠습니까? (yes/no): ")
            if response.lower() == 'yes':
                cleanup_test_position()
        else:
            print("테스트 취소")