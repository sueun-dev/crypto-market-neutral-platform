#!/usr/bin/env python3
"""
Real IP Integration Test
실제 IP 코인을 사용한 통합 테스트
"""

import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.exchanges.bithumb import BithumbExchange
from src.exchanges.gateio import GateIOExchange
from src.core.hedge_bot import HedgeBot
from src.core.premium_calculator import PremiumCalculator
from src.core.order_executor import OrderExecutor
from src.core.position_balancer import PositionBalancer
from src.managers.position_manager import PositionManager
import time

def test_real_ip_integration():
    """실제 IP를 사용한 통합 테스트"""
    print("\n" + "="*60)
    print("실제 IP 통합 테스트")
    print("="*60)
    
    # 1. 거래소 초기화 (실제 API 키 사용)
    print("\n[1] 거래소 초기화")
    try:
        bithumb = BithumbExchange(
            api_key=os.getenv('BITHUMB_API_KEY', 'dummy_key'),
            api_secret=os.getenv('BITHUMB_API_SECRET', 'dummy_secret')
        )
        
        gateio = GateIOExchange({
            'apiKey': os.getenv('GATEIO_API_KEY', 'dummy_key'),
            'secret': os.getenv('GATEIO_API_SECRET', 'dummy_secret'),
            'settle': 'usdt'
        })
        print("✓ 거래소 초기화 성공")
    except Exception as e:
        print(f"✗ 거래소 초기화 실패: {e}")
        return False
    
    # 2. IP 가격 조회
    print("\n[2] IP 가격 조회")
    try:
        # Bithumb IP 가격
        bithumb_ticker = bithumb.get_ticker("IP/KRW")
        if bithumb_ticker:
            print(f"  Bithumb IP/KRW: {bithumb_ticker.get('last', 'N/A'):,} KRW")
        else:
            print("  Bithumb IP 가격 조회 실패")
        
        # Gate.io IP 가격
        gateio_ticker = gateio.get_ticker("IP/USDT:USDT")
        if gateio_ticker:
            print(f"  Gate.io IP/USDT: ${gateio_ticker.get('last', 'N/A')}")
        else:
            print("  Gate.io IP 가격 조회 실패")
    except Exception as e:
        print(f"✗ 가격 조회 실패: {e}")
    
    # 3. 프리미엄 계산
    print("\n[3] 프리미엄 계산")
    try:
        calculator = PremiumCalculator(bithumb, gateio)
        premium = calculator.calculate("IP")
        if premium is not None:
            print(f"  IP 김치 프리미엄: {premium:.2f}%")
        else:
            print("  프리미엄 계산 실패")
    except Exception as e:
        print(f"✗ 프리미엄 계산 실패: {e}")
    
    # 4. 포지션 매니저 테스트
    print("\n[4] 포지션 매니저 테스트")
    try:
        manager = PositionManager()
        
        # 기존 포지션 조회
        existing_value = manager.get_existing_positions("IP", bithumb, gateio)
        print(f"  기존 IP 포지션 가치: ${existing_value:.2f}")
        
        # 포지션 업데이트 테스트
        manager.update_position("IP", 10.0)
        position = manager.get_position("IP")
        print(f"  업데이트 후 포지션: ${position.value_usd:.2f}")
        print(f"  Long value: ${position.long_value:.2f}")
        print(f"  Short value: ${position.short_value:.2f}")
    except Exception as e:
        print(f"✗ 포지션 매니저 테스트 실패: {e}")
    
    # 5. 포지션 밸런서 테스트
    print("\n[5] 포지션 밸런서 테스트")
    try:
        order_executor = OrderExecutor(bithumb, gateio)
        balancer = PositionBalancer(manager, order_executor, bithumb, gateio)
        
        # IP 포지션 균형 확인
        balance = balancer.check_position_balance("IP")
        if balance:
            print(f"  현물 수량: {balance.spot_quantity:.6f} IP")
            print(f"  선물 수량: {balance.futures_quantity:.6f} IP")
            print(f"  수량 차이: {balance.quantity_gap:.6f} IP")
            print(f"  차이 비율: {balance.gap_percentage:.2f}%")
            print(f"  균형 상태: {'✓ 균형' if balance.is_balanced else '✗ 불균형'}")
        else:
            print("  포지션 균형 확인 실패")
    except Exception as e:
        print(f"✗ 포지션 밸런서 테스트 실패: {e}")
    
    # 6. HedgeBot 초기화 테스트
    print("\n[6] HedgeBot 초기화 테스트")
    try:
        bot = HedgeBot(bithumb, gateio)
        print("✓ HedgeBot 초기화 성공")
        
        # None 입력 테스트
        try:
            bot_fail = HedgeBot(None, None)
            print("✗ None 검증 실패 - 에러가 발생해야 함")
        except ValueError as e:
            print(f"✓ None 검증 성공: {e}")
        
        # IP 심볼 추가
        result = bot.add_symbol("IP")
        if result:
            print("✓ IP 심볼 추가 성공")
        else:
            print("✗ IP 심볼 추가 실패")
            
    except Exception as e:
        print(f"✗ HedgeBot 테스트 실패: {e}")
    
    # 7. 전체 사이클 테스트 (Mock 모드)
    print("\n[7] 전체 사이클 테스트")
    try:
        # Mock 거래소로 안전하게 테스트
        from unittest.mock import Mock
        
        mock_bithumb = Mock()
        mock_bithumb.exchange_id = 'bithumb'
        mock_bithumb.get_ticker = Mock(return_value={'last': 10000, 'bid': 9990, 'ask': 10010})
        mock_bithumb.get_balance = Mock(return_value={'free': 0, 'used': 0, 'total': 0})
        mock_bithumb.create_market_order = Mock(return_value={'id': 'test', 'status': 'closed'})
        
        mock_gateio = Mock()
        mock_gateio.exchange_id = 'gateio'
        mock_gateio.get_ticker = Mock(return_value={'last': 7.5, 'bid': 7.49, 'ask': 7.51})
        mock_gateio.get_positions = Mock(return_value=[])
        mock_gateio.create_market_order = Mock(return_value={'id': 'test', 'status': 'filled'})
        mock_gateio.get_markets = Mock(return_value={'IP/USDT:USDT': {'contract_size': 1}})
        
        mock_bot = HedgeBot(mock_bithumb, mock_gateio)
        mock_bot.add_symbol("IP")
        
        # 10 사이클 실행
        for i in range(10):
            mock_bot.process_symbol("IP")
        
        print(f"✓ 10 사이클 실행 완료")
        
    except Exception as e:
        print(f"✗ 사이클 테스트 실패: {e}")
    
    print("\n" + "="*60)
    print("테스트 완료")
    print("="*60)
    
    return True

if __name__ == "__main__":
    success = test_real_ip_integration()
    sys.exit(0 if success else 1)