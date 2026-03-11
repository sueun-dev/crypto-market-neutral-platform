#!/usr/bin/env python3
"""
Upbit 거래소 DOGE 코인 테스트
"""
import os
import sys
import time
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# 프로젝트 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.exchanges.upbit import UpbitExchange


def main():
    # API 키 확인
    api_key = os.getenv('UPBIT_API_KEY')
    api_secret = os.getenv('UPBIT_API_SECRET')
    
    if not api_key or not api_secret:
        print("❌ UPBIT_API_KEY와 UPBIT_API_SECRET이 .env에 설정되어있지 않습니다")
        return
    
    try:
        # 거래소 초기화
        exchange = UpbitExchange(api_key, api_secret)
        print("✅ Upbit 거래소 초기화 성공")
        
        # 1. KRW 잔고 확인
        print("\n" + "="*50)
        print("1. KRW 잔고 확인")
        print("="*50)
        
        krw_balance = exchange.get_balance('KRW')
        if krw_balance:
            print(f"총 KRW: {krw_balance['total']:,.0f} KRW")
            print(f"사용가능: {krw_balance['free']:,.0f} KRW")
            print(f"거래중: {krw_balance['used']:,.0f} KRW")
        else:
            print("❌ KRW 잔고 조회 실패")
            return
        
        # 2. DOGE 가격 확인
        print("\n" + "="*50)
        print("2. DOGE/KRW 가격 확인")
        print("="*50)
        
        ticker = exchange.get_ticker('DOGE/KRW')
        if not ticker:
            print("❌ DOGE/KRW 가격을 가져올 수 없습니다")
            return
        
        print(f"현재가: {ticker['last']:,.2f} KRW")
        print(f"고가: {ticker['high']:,.2f} KRW")
        print(f"저가: {ticker['low']:,.2f} KRW")
        print(f"거래량: {ticker['volume']:,.2f} DOGE")
        
        # 3. DOGE 잔고 확인
        print("\n" + "="*50)
        print("3. DOGE 잔고 확인")
        print("="*50)
        
        doge_balance = exchange.get_balance('DOGE')
        if doge_balance:
            print(f"총 DOGE: {doge_balance['total']:.8f} DOGE")
            print(f"사용가능: {doge_balance['free']:.8f} DOGE")
            print(f"거래중: {doge_balance['used']:.8f} DOGE")
        else:
            print("DOGE 잔고: 0 DOGE")
        
        # 4. USDT 가격 확인 (프리미엄 계산용)
        print("\n" + "="*50)
        print("4. USDT/KRW 환율 확인")
        print("="*50)
        
        usdt_price = exchange.get_usdt_krw_price()
        if usdt_price:
            print(f"USDT/KRW: {usdt_price:,.0f} KRW")
        else:
            print("❌ USDT/KRW 환율 조회 실패")
        
        # 5. 테스트 거래 시나리오
        print("\n" + "="*50)
        print("5. DOGE 매매 시나리오 테스트")
        print("="*50)
        
        if krw_balance['free'] < 10000:
            print("❌ 테스트를 위한 충분한 KRW가 없습니다 (최소 10,000 KRW 필요)")
            return
        
        # 시나리오 1: 5,000원 매수
        print("\n=== 시나리오 1: 5,000원 매수 ===")
        krw_amount_1 = 5000
        print(f"매수 금액: {krw_amount_1:,} KRW")
        print(f"예상 수량: {krw_amount_1 / ticker['last']:.2f} DOGE")
        
        buy_order_1 = exchange.create_market_order('DOGE/KRW', 'buy', krw_amount_1)
        
        if buy_order_1:
            print(f"✅ 매수 성공!")
            print(f"  주문 ID: {buy_order_1.get('id')}")
            print(f"  체결 수량: {buy_order_1.get('filled', 0):.8f} DOGE")
        else:
            print("❌ 매수 실패")
            return
        
        # 잔고 확인
        time.sleep(2)
        doge_balance = exchange.get_balance('DOGE')
        print(f"\n현재 DOGE 보유량: {doge_balance['free']:.8f} DOGE")
        
        # 시나리오 2: 전량 매도
        print("\n=== 시나리오 2: 전량 매도 ===")
        sell_amount = doge_balance['free']
        
        if sell_amount > 0:
            print(f"매도 수량: {sell_amount:.8f} DOGE")
            
            sell_order = exchange.create_market_order('DOGE/KRW', 'sell', sell_amount)
            
            if sell_order:
                print(f"✅ 매도 성공!")
                print(f"  주문 ID: {sell_order.get('id')}")
                print(f"  체결 수량: {sell_order.get('filled', 0):.8f} DOGE")
            else:
                print("❌ 매도 실패")
        else:
            print("매도할 DOGE가 없습니다")
        
        # 시나리오 3: 10,000원 매수
        time.sleep(2)
        print("\n=== 시나리오 3: 10,000원 매수 ===")
        krw_amount_2 = 10000
        print(f"매수 금액: {krw_amount_2:,} KRW")
        
        # 최신 가격 확인
        ticker = exchange.get_ticker('DOGE/KRW')
        print(f"현재가: {ticker['last']:,.2f} KRW")
        print(f"예상 수량: {krw_amount_2 / ticker['last']:.2f} DOGE")
        
        buy_order_2 = exchange.create_market_order('DOGE/KRW', 'buy', krw_amount_2)
        
        if buy_order_2:
            print(f"✅ 매수 성공!")
            print(f"  주문 ID: {buy_order_2.get('id')}")
            print(f"  체결 수량: {buy_order_2.get('filled', 0):.8f} DOGE")
        else:
            print("❌ 매수 실패")
            return
        
        # 잔고 확인
        time.sleep(2)
        doge_balance = exchange.get_balance('DOGE')
        print(f"\n현재 DOGE 보유량: {doge_balance['free']:.8f} DOGE")
        
        # 시나리오 4: 50% 매도
        print("\n=== 시나리오 4: 50% 매도 ===")
        sell_amount_partial = doge_balance['free'] * 0.5
        
        if sell_amount_partial > 0:
            print(f"매도 수량: {sell_amount_partial:.8f} DOGE")
            
            sell_order_2 = exchange.create_market_order('DOGE/KRW', 'sell', sell_amount_partial)
            
            if sell_order_2:
                print(f"✅ 매도 성공!")
                print(f"  주문 ID: {sell_order_2.get('id')}")
                print(f"  체결 수량: {sell_order_2.get('filled', 0):.8f} DOGE")
            else:
                print("❌ 매도 실패")
        
        # 시나리오 5: 나머지 전량 매도
        time.sleep(2)
        print("\n=== 시나리오 5: 나머지 전량 매도 ===")
        doge_balance = exchange.get_balance('DOGE')
        remaining = doge_balance['free']
        
        if remaining > 0:
            print(f"매도 수량: {remaining:.8f} DOGE")
            
            sell_order_3 = exchange.create_market_order('DOGE/KRW', 'sell', remaining)
            
            if sell_order_3:
                print(f"✅ 매도 성공!")
                print(f"  주문 ID: {sell_order_3.get('id')}")
                print(f"  체결 수량: {sell_order_3.get('filled', 0):.8f} DOGE")
            else:
                print("❌ 매도 실패")
        else:
            print("매도할 DOGE가 없습니다")
        
        # 최종 잔고 확인
        time.sleep(2)
        print("\n" + "="*50)
        print("6. 최종 잔고 확인")
        print("="*50)
        
        krw_balance_final = exchange.get_balance('KRW')
        doge_balance_final = exchange.get_balance('DOGE')
        
        print(f"KRW: {krw_balance_final['free']:,.0f} KRW")
        print(f"DOGE: {doge_balance_final['free']:.8f} DOGE")
        
        # 손익 계산
        krw_diff = krw_balance_final['total'] - krw_balance['total']
        print(f"\nKRW 변동: {krw_diff:+,.0f} KRW")
        
        print("\n" + "="*50)
        print("✅ Upbit DOGE 테스트 완료!")
        print("="*50)
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()