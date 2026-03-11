#!/usr/bin/env python3
"""
GateIO 선물 거래소 자동 테스트 - GNO 1배 숏포지션
"""
import os
import sys
import time
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# 프로젝트 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.exchanges.gateio import GateIOExchange


def main():
    # API 키 확인
    api_key = os.getenv('GATEIO_API_KEY')
    api_secret = os.getenv('GATEIO_API_SECRET')
    
    if not api_key or not api_secret:
        print("❌ GATEIO_API_KEY와 GATEIO_API_SECRET이 .env에 설정되어있지 않습니다")
        return
    
    try:
        # 거래소 초기화
        exchange = GateIOExchange({
            'apiKey': api_key,
            'secret': api_secret
        })
        print("✅ 거래소 초기화 성공")
        
        # 1. USDT 잔고 확인
        print("\n" + "="*50)
        print("1. USDT 잔고 확인")
        print("="*50)
        
        usdt_balance = exchange.get_balance('USDT')
        if usdt_balance:
            print(f"총 USDT: {usdt_balance['total']:.2f} USDT")
            print(f"사용가능: {usdt_balance['free']:.2f} USDT")
            print(f"사용중: {usdt_balance['used']:.2f} USDT")
        else:
            print("❌ USDT 잔고 조회 실패")
            return
        
        if usdt_balance['free'] < 20:
            print("❌ 테스트를 위한 충분한 USDT가 없습니다 (최소 $20 필요)")
            return
        
        # 2. 기존 포지션 확인
        print("\n" + "="*50)
        print("2. 기존 포지션 확인")
        print("="*50)
        
        positions = exchange.get_positions()
        if positions:
            print(f"총 {len(positions)}개의 포지션:")
            for pos in positions:
                print(f"  {pos['symbol']}: {pos['side']} {pos['contracts']} contracts (${pos['notional']:.2f})")
                if pos['symbol'] == 'GNO/USDT:USDT':
                    print(f"    ⚠️ 기존 GNO 포지션 발견! 테스트 중단")
                    return
        else:
            print("현재 열린 포지션 없음")
        
        # 3. GNO 선물 정보 확인
        print("\n" + "="*50)
        print("3. GNO/USDT 선물 정보 확인")
        print("="*50)
        
        ticker = exchange.get_ticker('GNO/USDT:USDT')
        if not ticker:
            print("❌ GNO/USDT:USDT 티커를 가져올 수 없습니다")
            return
        
        print(f"현재가: ${ticker['last']:.2f}")
        print(f"매수호가: ${ticker['bid']:.2f}")
        print(f"매도호가: ${ticker['ask']:.2f}")
        
        # 계약 정보 확인
        markets = exchange.get_markets()
        gno_market = markets.get('GNO/USDT:USDT')
        if gno_market:
            print(f"계약 이름: {gno_market['name']}")
            print(f"계약 크기: {gno_market['contract_size']} GNO per contract")
        else:
            print("❌ GNO 시장 정보를 찾을 수 없습니다")
            return
        
        # 4. 레버리지 설정 (1배)
        print("\n" + "="*50)
        print("4. 레버리지 1배 설정")
        print("="*50)
        
        if exchange.set_leverage('GNO/USDT:USDT', 1):
            print("✅ 레버리지 1배 설정 완료")
        else:
            print("⚠️ 레버리지 설정 실패 (Gate.io는 포지션별 자동 설정)")
        
        # 5. 테스트 숏포지션 열기
        print("\n" + "="*50)
        print("5. 테스트 숏포지션 열기 (자동)")
        print("="*50)
        
        # 최소 계약 수로 테스트
        contracts = 10  # 10 contracts = 0.1 GNO
        contract_size = gno_market['contract_size']
        gno_amount = contracts * contract_size
        gno_price = ticker['ask']
        usd_value = gno_amount * gno_price
        
        print(f"계약 수: {contracts} contracts")
        print(f"GNO 수량: {gno_amount:.4f} GNO")
        print(f"예상 금액: ${usd_value:.2f}")
        
        # 숏포지션 열기
        print("\n🔄 숏포지션 열기...")
        order = exchange.create_market_order('GNO/USDT:USDT', 'sell', gno_amount)
        
        if order:
            print(f"✅ 숏포지션 성공!")
            print(f"  주문 ID: {order['id']}")
            print(f"  체결 수량: {order.get('filled', 0)} contracts")
        else:
            print("❌ 숏포지션 실패")
            return
        
        # 6. 포지션 확인
        time.sleep(3)
        print("\n" + "="*50)
        print("6. 새로운 포지션 확인")
        print("="*50)
        
        positions = exchange.get_positions()
        gno_position = None
        for pos in positions:
            if pos['symbol'] == 'GNO/USDT:USDT':
                gno_position = pos
                break
        
        if gno_position:
            print(f"✅ GNO 숏포지션 확인:")
            print(f"  Side: {gno_position['side']}")
            print(f"  Contracts: {gno_position['contracts']}")
            print(f"  Notional: ${gno_position['notional']:.2f}")
            print(f"  Entry Price: ${gno_position['entry_price']:.2f}")
            print(f"  Mark Price: ${gno_position['mark_price']:.2f}")
            
            # Side가 'short'인지 확인
            if gno_position['side'] != 'short':
                print(f"❌ 오류: 포지션이 숏이 아닙니다! ({gno_position['side']})")
                return
        else:
            print("⚠️ 포지션을 찾을 수 없습니다")
            return
        
        # 7. 포지션 닫기
        time.sleep(2)
        print("\n" + "="*50)
        print("7. 숏포지션 닫기 (자동)")
        print("="*50)
        
        print("🔄 숏포지션 닫기...")
        # reduce_only 플래그로 포지션 닫기
        close_order = exchange.create_market_order(
            'GNO/USDT:USDT', 
            'buy',  # 숏을 닫으려면 buy
            gno_amount,  # 같은 수량
            {'reduce_only': True}
        )
        
        if close_order:
            print(f"✅ 포지션 닫기 성공!")
            print(f"  주문 ID: {close_order['id']}")
        else:
            print("❌ 포지션 닫기 실패")
            return
        
        # 8. 최종 상태 확인
        time.sleep(3)
        print("\n" + "="*50)
        print("8. 최종 상태 확인")
        print("="*50)
        
        positions = exchange.get_positions()
        gno_position = None
        for pos in positions:
            if pos['symbol'] == 'GNO/USDT:USDT':
                gno_position = pos
                break
        
        if gno_position:
            print(f"⚠️ GNO 포지션이 여전히 열려있습니다:")
            print(f"  Contracts: {gno_position['contracts']}")
            print(f"  Notional: ${gno_position['notional']:.2f}")
        else:
            print("✅ GNO 포지션이 정상적으로 닫혔습니다")
        
        usdt_balance_final = exchange.get_balance('USDT')
        print(f"\n최종 USDT 잔고: {usdt_balance_final['free']:.2f} USDT")
        
        # 손익 계산
        pnl = usdt_balance_final['total'] - usdt_balance['total']
        print(f"거래 손익: ${pnl:.2f}")
        
        print("\n" + "="*50)
        print("✅ 테스트 완료! GateIO 1배 숏포지션 정상 작동")
        print("="*50)
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()