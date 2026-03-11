#!/usr/bin/env python3
"""
Bithumb 잔고 확인 스크립트
"""
import os
import sys
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
        print("❌ BITHUMB_API_KEY와 BITHUMB_API_SECRET이 .env 파일에 설정되어있지 않습니다")
        return
    
    try:
        # 거래소 초기화
        exchange = BithumbExchange(api_key, api_secret)
        print("✅ 거래소 초기화 성공")
        
        # 모든 통화 잔고 확인
        print("\n📊 전체 잔고 조회")
        print("-" * 50)
        
        # 주요 통화 목록
        currencies = ['KRW', 'BTC', 'ETH', 'XRP', 'GNO', 'USDT']
        
        total_krw_value = 0
        
        for currency in currencies:
            balance = exchange.get_balance(currency)
            if balance and balance['total'] > 0:
                print(f"\n{currency}:")
                print(f"  총액: {balance['total']:,.8f}")
                print(f"  사용가능: {balance['free']:,.8f}")
                print(f"  거래중: {balance['used']:,.8f}")
                
                # KRW 환산 (예상)
                if currency != 'KRW':
                    ticker = exchange.get_ticker(f"{currency}/KRW")
                    if ticker:
                        krw_value = balance['total'] * ticker['last']
                        total_krw_value += krw_value
                        print(f"  KRW 환산: {krw_value:,.0f} KRW")
                else:
                    total_krw_value += balance['total']
        
        print("\n" + "=" * 50)
        print(f"💰 총 자산 가치 (KRW): {total_krw_value:,.0f} KRW")
        
        # 거래 가능 확인
        print("\n" + "=" * 50)
        krw_balance = exchange.get_balance('KRW')
        if krw_balance['free'] >= 1000:
            print(f"✅ 거래 가능 (사용가능 KRW: {krw_balance['free']:,.0f})")
        else:
            print(f"❌ 거래 불가 (사용가능 KRW: {krw_balance['free']:,.0f} < 1000)")
            
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()