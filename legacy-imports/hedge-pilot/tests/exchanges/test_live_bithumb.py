#!/usr/bin/env python3
"""
Bithumb 실제 API 테스트 실행 스크립트
실제 거래를 수행하므로 주의하여 실행하세요!
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


def test_basic_functionality():
    """기본 기능 테스트"""
    print("\n" + "="*70)
    print("Bithumb 실제 API 테스트 시작")
    print("="*70)
    
    # API 키 확인
    api_key = os.getenv('BITHUMB_API_KEY')
    api_secret = os.getenv('BITHUMB_API_SECRET')
    
    if not api_key or not api_secret:
        print("❌ BITHUMB_API_KEY와 BITHUMB_API_SECRET이 .env 파일에 설정되어있지 않습니다")
        return False
    
    print("✅ API 키 로드 완료")
    
    try:
        # 거래소 초기화
        exchange = BithumbExchange(api_key, api_secret)
        print("✅ 거래소 초기화 성공")
        
        # 1. 시장 정보 로드 (Bithumb native API는 load_markets 지원하지 않음)
        print("\n1. 시장 정보 로드 중...")
        # Bithumb native API는 개별 심볼 조회만 가능
        test_symbols = ['BTC/KRW', 'ETH/KRW', 'GNO/KRW']
        available_count = 0
        for symbol in test_symbols:
            ticker = exchange.get_ticker(symbol)
            if ticker:
                available_count += 1
        print(f"   {available_count}개의 주요 거래쌍 확인")
        
        # 2. BTC 티커 조회
        print("\n2. BTC/KRW 티커 조회...")
        ticker = exchange.get_ticker('BTC/KRW')
        if ticker:
            print(f"   현재가: {ticker['last']:,} KRW")
            print(f"   매도호가: {ticker['ask']:,} KRW")
            print(f"   매수호가: {ticker['bid']:,} KRW")
        
        # 3. 잔고 조회
        print("\n3. 계정 잔고 조회...")
        krw_balance = exchange.get_balance('KRW')
        if krw_balance:
            print(f"   KRW 잔고: {krw_balance['total']:,.0f} KRW")
            print(f"   사용가능: {krw_balance['free']:,.0f} KRW")
        
        # 4. USDT 환율 조회
        print("\n4. USDT/KRW 환율 조회...")
        usdt_price = exchange.get_usdt_krw_price()
        if usdt_price:
            print(f"   USDT/KRW: {usdt_price:,.2f} KRW")
        
        print("\n✅ 기본 기능 테스트 완료")
        return True
        
    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        return False


def test_gno_trading_scenario():
    """GNO 코인 매매 시나리오 테스트"""
    print("\n" + "="*70)
    print("GNO 코인 매매 시나리오 테스트")
    print("⚠️  실제 거래가 실행됩니다! 계속하시겠습니까? (y/n)")
    print("="*70)
    
    response = input("> ").strip().lower()
    if response != 'y':
        print("테스트 취소됨")
        return False
    
    api_key = os.getenv('BITHUMB_API_KEY')
    api_secret = os.getenv('BITHUMB_API_SECRET')
    
    if not api_key or not api_secret:
        print("❌ API 키가 설정되지 않았습니다")
        return False
    
    try:
        exchange = BithumbExchange(api_key, api_secret)
        
        # GNO 가격 확인
        ticker = exchange.get_ticker('GNO/KRW')
        if not ticker:
            print("❌ GNO/KRW 거래쌍을 찾을 수 없습니다")
            return False
        
        print(f"\n현재 GNO 가격:")
        print(f"  현재가: {ticker['last']:,} KRW")
        print(f"  매도호가: {ticker['ask']:,} KRW")
        print(f"  매수호가: {ticker['bid']:,} KRW")
        
        # 초기 잔고 확인
        krw_balance = exchange.get_balance('KRW')
        gno_balance = exchange.get_balance('GNO')
        
        print(f"\n초기 잔고:")
        print(f"  KRW: {krw_balance['free']:,.0f} KRW")
        print(f"  GNO: {gno_balance['free']:.8f} GNO")
        
        if krw_balance['free'] < 25000:
            print("❌ 테스트를 위한 충분한 KRW 잔고가 없습니다 (최소 25,000 KRW 필요)")
            return False
        
        # 시나리오 1: 5,500원 매수
        print("\n=== 시나리오 1: 5,500원 매수 ===")
        krw_amount_1 = 5500
        print(f"매수 금액: {krw_amount_1:,} KRW")
        
        order1 = exchange.create_market_order('GNO/KRW', 'buy', krw_amount_1)
        if order1:
            print(f"✅ 매수 완료 - 주문 ID: {order1.get('id')}")
            print(f"   체결 수량: {order1.get('filled', 0):.8f} GNO")
            print(f"   사용 금액: {order1.get('cost', 0):,.0f} KRW")
        else:
            print("❌ 매수 실패")
            return False
        
        time.sleep(2)
        
        # 시나리오 2: 전량 매도
        print("\n=== 시나리오 2: 전량 매도 ===")
        gno_balance = exchange.get_balance('GNO')
        sell_amount = gno_balance['free']
        print(f"매도 수량: {sell_amount:.8f} GNO")
        
        if sell_amount > 0:
            order2 = exchange.create_market_order('GNO/KRW', 'sell', sell_amount)
            if order2:
                print(f"✅ 매도 완료 - 주문 ID: {order2.get('id')}")
                print(f"   체결 수량: {order2.get('filled', 0):.8f} GNO")
                print(f"   수령 금액: {order2.get('cost', 0):,.0f} KRW")
            else:
                print("❌ 매도 실패")
        
        time.sleep(2)
        
        # 시나리오 3: 15,000원 매수
        print("\n=== 시나리오 3: 15,000원 매수 ===")
        krw_amount_2 = 15000
        print(f"매수 금액: {krw_amount_2:,} KRW")
        
        order3 = exchange.create_market_order('GNO/KRW', 'buy', krw_amount_2)
        if order3:
            print(f"✅ 매수 완료 - 주문 ID: {order3.get('id')}")
            print(f"   체결 수량: {order3.get('filled', 0):.8f} GNO")
            print(f"   사용 금액: {order3.get('cost', 0):,.0f} KRW")
        else:
            print("❌ 매수 실패")
            return False
        
        time.sleep(2)
        
        # 시나리오 4: 7,000원 어치 매도
        print("\n=== 시나리오 4: 7,000원 어치 매도 ===")
        ticker = exchange.get_ticker('GNO/KRW')
        sell_amount_partial = round(7000 / ticker['bid'], 8)
        print(f"매도 수량: {sell_amount_partial:.8f} GNO")
        
        order4 = exchange.create_market_order('GNO/KRW', 'sell', sell_amount_partial)
        if order4:
            print(f"✅ 매도 완료 - 주문 ID: {order4.get('id')}")
            print(f"   체결 수량: {order4.get('filled', 0):.8f} GNO")
            print(f"   수령 금액: {order4.get('cost', 0):,.0f} KRW")
        else:
            print("❌ 매도 실패")
        
        time.sleep(2)
        
        # 시나리오 5: 나머지 전량 매도
        print("\n=== 시나리오 5: 나머지 전량 매도 ===")
        gno_balance = exchange.get_balance('GNO')
        remaining = gno_balance['free']
        print(f"매도 수량: {remaining:.8f} GNO")
        
        if remaining > 0:
            order5 = exchange.create_market_order('GNO/KRW', 'sell', remaining)
            if order5:
                print(f"✅ 매도 완료 - 주문 ID: {order5.get('id')}")
                print(f"   체결 수량: {order5.get('filled', 0):.8f} GNO")
                print(f"   수령 금액: {order5.get('cost', 0):,.0f} KRW")
            else:
                print("❌ 매도 실패")
        else:
            print("ℹ️  매도할 GNO가 없습니다")
        
        # 최종 잔고 확인
        print("\n최종 잔고:")
        krw_balance = exchange.get_balance('KRW')
        gno_balance = exchange.get_balance('GNO')
        print(f"  KRW: {krw_balance['free']:,.0f} KRW")
        print(f"  GNO: {gno_balance['free']:.8f} GNO")
        
        print("\n✅ GNO 매매 시나리오 완료")
        return True
        
    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """메인 함수"""
    print("Bithumb 실제 API 테스트")
    print("=" * 70)
    print("1. 기본 기능 테스트 (읽기 전용)")
    print("2. GNO 코인 매매 시나리오 (실제 거래)")
    print("3. 전체 테스트 실행")
    print("0. 종료")
    print("=" * 70)
    
    choice = input("선택> ").strip()
    
    if choice == '1':
        test_basic_functionality()
    elif choice == '2':
        test_gno_trading_scenario()
    elif choice == '3':
        test_basic_functionality()
        print("\n계속하시겠습니까? (y/n)")
        if input("> ").strip().lower() == 'y':
            test_gno_trading_scenario()
    elif choice == '0':
        print("종료합니다")
    else:
        print("잘못된 선택입니다")


if __name__ == '__main__':
    main()