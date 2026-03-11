#!/usr/bin/env python3
"""
통합 테스트: Bithumb + GateIO 헤징 포지션
GNO 코인으로 실제 헤징 포지션 테스트
"""
import os
import sys
import time
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# 프로젝트 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.exchanges.bithumb import BithumbExchange
from src.exchanges.gateio import GateIOExchange
from src.core.order_executor import OrderExecutor


def main():
    print("=" * 70)
    print("통합 테스트: Bithumb(현물) + GateIO(선물) GNO 헤징")
    print("=" * 70)
    
    # API 키 확인
    bithumb_key = os.getenv('BITHUMB_API_KEY')
    bithumb_secret = os.getenv('BITHUMB_API_SECRET')
    gateio_key = os.getenv('GATEIO_API_KEY')
    gateio_secret = os.getenv('GATEIO_API_SECRET')
    
    if not all([bithumb_key, bithumb_secret, gateio_key, gateio_secret]):
        print("❌ API 키가 설정되지 않았습니다")
        return
    
    try:
        # 거래소 초기화
        print("\n1. 거래소 초기화")
        korean_exchange = BithumbExchange(bithumb_key, bithumb_secret)
        futures_exchange = GateIOExchange({
            'apiKey': gateio_key,
            'secret': gateio_secret
        })
        print("✅ Bithumb 초기화 완료")
        print("✅ GateIO 초기화 완료")
        
        # OrderExecutor 생성
        executor = OrderExecutor(korean_exchange, futures_exchange)
        
        # 잔고 확인
        print("\n2. 초기 잔고 확인")
        krw_balance = korean_exchange.get_balance('KRW')
        usdt_balance = futures_exchange.get_balance('USDT')
        
        print(f"Bithumb KRW: {krw_balance['free']:,.0f} KRW")
        print(f"GateIO USDT: {usdt_balance['free']:.2f} USDT")
        
        if krw_balance['free'] < 20000:
            print("❌ KRW 잔고 부족 (최소 20,000 KRW 필요)")
            return
        
        if usdt_balance['free'] < 15:
            print("❌ USDT 잔고 부족 (최소 $15 필요)")
            return
        
        # 기존 포지션 확인
        print("\n3. 기존 포지션 확인")
        gno_balance = korean_exchange.get_balance('GNO')
        print(f"Bithumb GNO: {gno_balance['free']:.8f} GNO")
        
        positions = futures_exchange.get_positions()
        gno_position = None
        for pos in positions:
            if pos['symbol'] == 'GNO/USDT:USDT':
                gno_position = pos
                print(f"⚠️ 기존 GNO 선물 포지션: {pos['side']} {pos['contracts']} contracts")
                break
        
        if gno_position:
            print("기존 GNO 포지션이 있습니다. 테스트 중단")
            return
        
        # 가격 확인
        print("\n4. 현재 가격 확인")
        krw_ticker = korean_exchange.get_ticker('GNO/KRW')
        usdt_ticker = futures_exchange.get_ticker('GNO/USDT:USDT')
        usdt_krw = korean_exchange.get_ticker('USDT/KRW')
        
        print(f"GNO/KRW: {krw_ticker['last']:,.0f} KRW")
        print(f"GNO/USDT: ${usdt_ticker['last']:.2f}")
        print(f"USDT/KRW: {usdt_krw['last']:,.0f} KRW")
        
        # 프리미엄 계산
        futures_price_krw = usdt_ticker['last'] * usdt_krw['last']
        premium = ((krw_ticker['last'] - futures_price_krw) / futures_price_krw) * 100
        print(f"\n김치 프리미엄: {premium:.2f}%")
        
        # 헤징 포지션 열기
        print("\n5. 헤징 포지션 열기")
        print("-" * 50)
        
        # 작은 금액으로 테스트 (약 $10)
        test_amount_usd = 10
        print(f"테스트 금액: ${test_amount_usd}")
        
        success = executor.execute_hedge_position('GNO', test_amount_usd)
        
        if success:
            print("✅ 헤징 포지션 열기 성공!")
        else:
            print("❌ 헤징 포지션 열기 실패")
            return
        
        # 포지션 확인
        time.sleep(3)
        print("\n6. 포지션 확인")
        
        # 현물 확인
        gno_balance_after = korean_exchange.get_balance('GNO')
        gno_bought = gno_balance_after['free'] - gno_balance['free']
        print(f"Bithumb GNO 매수량: {gno_bought:.8f} GNO")
        
        # 선물 확인
        positions = futures_exchange.get_positions()
        gno_position = None
        for pos in positions:
            if pos['symbol'] == 'GNO/USDT:USDT':
                gno_position = pos
                break
        
        if gno_position:
            print(f"GateIO 숏포지션: {gno_position['contracts']} contracts (${gno_position['notional']:.2f})")
            if gno_position['side'] != 'short':
                print(f"❌ 오류: 포지션이 숏이 아닙니다! ({gno_position['side']})")
        else:
            print("⚠️ 선물 포지션을 찾을 수 없습니다")
        
        # 10초 대기
        print("\n10초 대기...")
        for i in range(10, 0, -1):
            print(f"{i}...", end=' ', flush=True)
            time.sleep(1)
        print()
        
        # 포지션 닫기
        print("\n7. 헤징 포지션 닫기 (50%)")
        print("-" * 50)
        
        if gno_position:
            position_value = gno_position['notional']
            success = executor.close_position_percentage('GNO', 50, position_value)
            
            if success:
                print("✅ 50% 포지션 닫기 성공!")
            else:
                print("❌ 포지션 닫기 실패")
        
        # 최종 상태 확인
        time.sleep(3)
        print("\n8. 최종 상태 확인")
        
        # 현물
        gno_balance_final = korean_exchange.get_balance('GNO')
        print(f"Bithumb GNO 최종: {gno_balance_final['free']:.8f} GNO")
        
        # 선물
        positions = futures_exchange.get_positions()
        gno_position_final = None
        for pos in positions:
            if pos['symbol'] == 'GNO/USDT:USDT':
                gno_position_final = pos
                break
        
        if gno_position_final:
            print(f"GateIO 남은 포지션: {gno_position_final['contracts']} contracts")
        else:
            print("GateIO 포지션 완전 청산됨")
        
        # 남은 포지션 청산
        if gno_position_final:
            print("\n9. 남은 포지션 청산")
            position_value = gno_position_final['notional']
            success = executor.close_position_percentage('GNO', 100, position_value)
            
            if success:
                print("✅ 남은 포지션 청산 성공!")
            else:
                print("❌ 남은 포지션 청산 실패")
        
        # 완전 청산 확인
        time.sleep(3)
        print("\n10. 완전 청산 확인")
        
        gno_balance_complete = korean_exchange.get_balance('GNO')
        print(f"Bithumb GNO: {gno_balance_complete['free']:.8f} GNO")
        
        positions = futures_exchange.get_positions()
        for pos in positions:
            if pos['symbol'] == 'GNO/USDT:USDT':
                print(f"⚠️ GateIO에 아직 포지션이 남아있습니다: {pos['contracts']} contracts")
                break
        else:
            print("✅ GateIO 포지션 완전 청산 확인")
        
        # 최종 잔고
        print("\n11. 최종 잔고")
        krw_balance_final = korean_exchange.get_balance('KRW')
        usdt_balance_final = futures_exchange.get_balance('USDT')
        
        print(f"Bithumb KRW: {krw_balance_final['free']:,.0f} KRW")
        print(f"GateIO USDT: {usdt_balance_final['free']:.2f} USDT")
        
        # 손익 계산
        krw_pnl = krw_balance_final['total'] - krw_balance['total']
        usdt_pnl = usdt_balance_final['total'] - usdt_balance['total']
        
        print(f"\n손익:")
        print(f"KRW: {krw_pnl:+,.0f} KRW")
        print(f"USDT: {usdt_pnl:+.2f} USDT")
        
        print("\n" + "=" * 70)
        print("✅ 통합 테스트 완료!")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()