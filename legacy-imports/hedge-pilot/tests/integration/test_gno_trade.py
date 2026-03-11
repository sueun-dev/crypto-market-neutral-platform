#!/usr/bin/env python3
"""
GNO 실제 거래 테스트
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


def main():
    # API 키 확인
    api_key = os.getenv('BITHUMB_API_KEY')
    api_secret = os.getenv('BITHUMB_API_SECRET')
    
    if not api_key or not api_secret:
        print("❌ API 키가 설정되지 않았습니다")
        return
    
    try:
        # 거래소 초기화
        exchange = BithumbExchange(api_key, api_secret)
        print("✅ 거래소 초기화 성공")
        
        # KRW 잔고 확인
        krw_balance = exchange.get_balance('KRW')
        print(f"\n💰 KRW 잔고: {krw_balance['free']:,.0f} KRW")
        
        if krw_balance['free'] < 5500:
            print("❌ 거래를 위한 충분한 KRW가 없습니다")
            return
        
        # GNO 가격 확인
        ticker = exchange.get_ticker('GNO/KRW')
        if not ticker:
            print("❌ GNO 가격을 가져올 수 없습니다")
            return
        
        print(f"\n📊 GNO 현재가: {ticker['last']:,.0f} KRW")
        if ticker.get('bid'):
            print(f"   매수호가: {ticker['bid']:,.0f} KRW")
        if ticker.get('ask'):
            print(f"   매도호가: {ticker['ask']:,.0f} KRW")
        
        # 5,500원으로 GNO 매수
        print("\n" + "="*50)
        print("🛒 5,500원으로 GNO 매수 시도")
        
        buy_order = exchange.create_market_order('GNO/KRW', 'buy', 5500)
        
        if buy_order:
            print(f"✅ 매수 성공!")
            print(f"   주문 ID: {buy_order.get('id')}")
            print(f"   체결 수량: {buy_order.get('filled', 0):.8f} GNO")
            print(f"   사용 금액: {buy_order.get('cost', 0):,.0f} KRW")
            
            # 잔고 확인
            time.sleep(2)
            gno_balance = exchange.get_balance('GNO')
            print(f"\n📈 GNO 잔고: {gno_balance['free']:.8f} GNO")
            
            # 전량 매도
            if gno_balance['free'] > 0.00001:  # 최소 수량 체크
                print("\n" + "="*50)
                print(f"💸 {gno_balance['free']:.8f} GNO 전량 매도 시도")
                
                sell_order = exchange.create_market_order('GNO/KRW', 'sell', gno_balance['free'])
                
                if sell_order:
                    print(f"✅ 매도 성공!")
                    print(f"   주문 ID: {sell_order.get('id')}")
                    print(f"   체결 수량: {sell_order.get('filled', 0):.8f} GNO")
                    print(f"   수령 금액: {sell_order.get('cost', 0):,.0f} KRW")
                else:
                    print("❌ 매도 실패")
            
            # 최종 잔고 확인
            time.sleep(2)
            krw_balance_final = exchange.get_balance('KRW')
            gno_balance_final = exchange.get_balance('GNO')
            
            print("\n" + "="*50)
            print("📊 최종 잔고:")
            print(f"   KRW: {krw_balance_final['free']:,.0f} KRW")
            print(f"   GNO: {gno_balance_final['free']:.8f} GNO")
            
        else:
            print("❌ 매수 실패")
            
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()