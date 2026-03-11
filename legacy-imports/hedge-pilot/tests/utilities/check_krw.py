#!/usr/bin/env python3
"""
Bithumb KRW 잔고 확인 스크립트
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
        
        # KRW 잔고 확인 - 디버그 모드
        print("\n📊 KRW 잔고 상세 조회")
        print("-" * 50)
        
        # Debug print 활성화를 위해 수정
        exchange._private_api_call('/info/balance', {'currency': 'KRW'})
        
        balance = exchange.get_balance('KRW')
        print(f"\nKRW 잔고:")
        print(f"  총액: {balance['total']:,.0f} KRW")
        print(f"  사용가능: {balance['free']:,.0f} KRW")
        print(f"  거래중: {balance['used']:,.0f} KRW")
        
        # BTC로도 테스트
        print("\n" + "-" * 50)
        btc_data = exchange._private_api_call('/info/balance', {'currency': 'BTC'})
        if btc_data:
            print(f"\nRaw BTC balance data:")
            for key, value in btc_data.items():
                if 'krw' in key.lower():
                    print(f"  {key}: {value}")
                    
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()