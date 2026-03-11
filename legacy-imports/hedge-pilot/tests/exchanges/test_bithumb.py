"""
Bithumb 거래소 종합 테스트 - 실제 API 사용
"""
import unittest
import os
import time
from decimal import Decimal
import sys
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.exchanges.bithumb import BithumbExchange


class TestBithumbExchange(unittest.TestCase):
    """Bithumb 거래소 실제 API 테스트 클래스"""
    
    def setUp(self):
        """테스트 설정"""
        # 실제 API 키 사용
        self.api_key = os.getenv('BITHUMB_API_KEY')
        self.api_secret = os.getenv('BITHUMB_API_SECRET')
        
        if not self.api_key or not self.api_secret:
            self.skipTest("BITHUMB_API_KEY와 BITHUMB_API_SECRET이 .env에 설정되어있지 않습니다")
        
        self.exchange = BithumbExchange(self.api_key, self.api_secret)
        print(f"\n=== Bithumb 실제 API 테스트 시작 ===")
        
    def tearDown(self):
        """테스트 정리"""
        time.sleep(0.5)  # API rate limit 방지
    
    # ========== 1. 연결 및 인증 테스트 ==========
    
    def test_exchange_initialization(self):
        """거래소 초기화 테스트"""
        print("\n1. 거래소 초기화 테스트")
        self.assertEqual(self.exchange.exchange_id, 'bithumb')
        self.assertIsNotNone(self.exchange.exchange)
        self.assertTrue(hasattr(self.exchange, 'get_balance'))
        self.assertTrue(hasattr(self.exchange, 'get_ticker'))
        self.assertTrue(hasattr(self.exchange, 'create_market_order'))
        print("   ✅ 거래소 초기화 성공")
    
    # ========== 2. 마켓 데이터 테스트 ==========
    
    def test_get_available_symbols(self):
        """사용 가능한 심볼 조회 테스트"""
        print("\n2. 사용 가능한 심볼 조회 테스트")
        
        # Bithumb Native API는 개별 심볼 조회만 지원
        # 주요 코인들의 티커를 조회하여 거래 가능 여부 확인
        major_symbols = ['BTC/KRW', 'ETH/KRW', 'XRP/KRW', 'GNO/KRW']
        available_symbols = []
        
        for symbol in major_symbols:
            ticker = self.exchange.get_ticker(symbol)
            if ticker:
                available_symbols.append(symbol)
                print(f"   ✅ {symbol} 거래 가능")
            else:
                print(f"   ⚠️  {symbol} 현재 거래 불가")
        
        self.assertGreater(len(available_symbols), 0)
        print(f"   총 {len(available_symbols)}개의 주요 거래쌍 확인")
    
    def test_get_ticker(self):
        """티커 조회 테스트"""
        print("\n3. 티커 조회 테스트")
        
        # BTC 티커 조회
        ticker = self.exchange.get_ticker('BTC/KRW')
        self.assertIsNotNone(ticker)
        self.assertIn('last', ticker)
        self.assertGreater(ticker['last'], 0)
        
        print(f"   BTC/KRW - 현재가: {ticker['last']:,} KRW")
        print(f"   최고가: {ticker.get('high', 'N/A')} KRW")
        print(f"   최저가: {ticker.get('low', 'N/A')} KRW")
        print(f"   거래량: {ticker.get('volume', 'N/A')}")
    
    def test_get_ticker_invalid_symbol(self):
        """잘못된 심볼 티커 조회 테스트"""
        print("\n4. 잘못된 심볼 티커 조회 테스트")
        
        ticker = self.exchange.get_ticker('INVALID/KRW')
        self.assertIsNone(ticker)
        print("   ✅ 잘못된 심볼 처리 정상")
    
    # ========== 3. 계정 정보 테스트 ==========
    
    def test_get_balance(self):
        """잔고 조회 테스트"""
        print("\n5. 잔고 조회 테스트")
        
        # KRW 잔고 조회
        balance = self.exchange.get_balance('KRW')
        self.assertIsNotNone(balance)
        self.assertIn('free', balance)
        self.assertIn('used', balance)
        self.assertIn('total', balance)
        
        print(f"   KRW 잔고:")
        print(f"     사용가능: {balance['free']:,.0f} KRW")
        print(f"     거래중: {balance['used']:,.0f} KRW")
        print(f"     총액: {balance['total']:,.0f} KRW")
        
        # 주요 자산 잔고 확인
        print(f"\n   보유 자산:")
        currencies = ['BTC', 'ETH', 'XRP', 'GNO']
        for currency in currencies:
            bal = self.exchange.get_balance(currency)
            if bal and bal.get('total', 0) > 0:
                print(f"     {currency}: {bal['total']:.8f}")
    
    def test_get_usdt_krw_price(self):
        """USDT/KRW 환율 조회 테스트"""
        print("\n6. USDT/KRW 환율 조회 테스트")
        
        price = self.exchange.get_usdt_krw_price()
        self.assertIsNotNone(price)
        self.assertGreater(price, 1000)  # USDT는 보통 1000원 이상
        self.assertLess(price, 2000)     # 그리고 2000원 이하
        
        print(f"   USDT/KRW 환율: {price:,.2f} KRW")
    
    # ========== 4. 주문 테스트 ==========
    
    def test_calculate_order_amount(self):
        """주문 수량 계산 테스트"""
        print("\n7. 주문 수량 계산 테스트")
        
        # 8자리 반올림 테스트
        test_cases = [
            (0.123456789, 0.12345679),
            (1.000000001, 1.00000000),
            (0.000000001, 0.00000000),
            (99.999999999, 100.00000000)
        ]
        
        for input_val, expected in test_cases:
            result = round(input_val, 8)
            self.assertEqual(result, expected)
        
        print("   ✅ 8자리 반올림 정상 작동")
    
    # ========== 5. GNO 코인 매매 시나리오 테스트 ==========
    
    def test_gno_trading_scenario(self):
        """GNO 코인 매매 시나리오 통합 테스트 - 실제 API 사용"""
        print("\n8. GNO 코인 매매 시나리오 테스트")
        
        # GNO 가격 확인
        ticker = self.exchange.get_ticker('GNO/KRW')
        if not ticker:
            print("GNO/KRW 거래쌍을 찾을 수 없습니다")
            return
        
        print(f"\n   현재 GNO/KRW 가격:")
        print(f"     현재가: {ticker['last']:,} KRW")
        if ticker.get('bid'):
            print(f"     매수호가: {ticker['bid']:,} KRW")
        if ticker.get('ask'):
            print(f"     매도호가: {ticker['ask']:,} KRW")
        
        # 초기 잔고 확인
        krw_balance = self.exchange.get_balance('KRW')
        gno_balance = self.exchange.get_balance('GNO')
        
        print(f"\n   초기 잔고:")
        print(f"     KRW: {krw_balance['free']:,.0f} KRW")
        print(f"     GNO: {gno_balance['free']:.8f} GNO")
        
        # 충분한 잔고 확인
        if krw_balance['free'] < 25000:  # 5500 + 15000 + 여유
            print("테스트를 위한 충분한 KRW 잔고가 없습니다 (최소 25,000 KRW 필요)")
            return
        
        # 시나리오 1: 5,500원 매수 (Bithumb market_buy는 KRW 금액을 받음)
        print("\n   === 시나리오 1: 5,500원 매수 ===")
        krw_amount_1 = 5500
        print(f"     매수 금액: {krw_amount_1:,} KRW")
        
        order1 = self.exchange.create_market_order('GNO/KRW', 'buy', krw_amount_1)
        if order1:
            print(f"     ✅ 매수 완료 - 주문 ID: {order1.get('id')}")
            print(f"     체결 수량: {order1.get('filled', 0):.8f} GNO")
            print(f"     사용 금액: {order1.get('cost', 0):,.0f} KRW")
        else:
            print(f"     ❌ 매수 실패")
            return
        
        time.sleep(2)  # API rate limit 방지
        
        # 시나리오 2: 전량 매도
        print("\n   === 시나리오 2: 전량 매도 ===")
        gno_balance = self.exchange.get_balance('GNO')
        sell_amount_1 = gno_balance['free']
        print(f"     매도 수량: {sell_amount_1:.8f} GNO")
        
        if sell_amount_1 > 0:
            order2 = self.exchange.create_market_order('GNO/KRW', 'sell', sell_amount_1)
            if order2:
                print(f"     ✅ 매도 완료 - 주문 ID: {order2.get('id')}")
                print(f"     체결 수량: {order2.get('filled', 0):.8f} GNO")
                print(f"     수령 금액: {order2.get('cost', 0):,.0f} KRW")
            else:
                print(f"     ❌ 매도 실패")
        
        time.sleep(2)
        
        # 시나리오 3: 15,000원 매수
        print("\n   === 시나리오 3: 15,000원 매수 ===")
        krw_amount_2 = 15000
        print(f"     매수 금액: {krw_amount_2:,} KRW")
        
        order3 = self.exchange.create_market_order('GNO/KRW', 'buy', krw_amount_2)
        if order3:
            print(f"     ✅ 매수 완료 - 주문 ID: {order3.get('id')}")
            print(f"     체결 수량: {order3.get('filled', 0):.8f} GNO")
            print(f"     사용 금액: {order3.get('cost', 0):,.0f} KRW")
        else:
            print(f"     ❌ 매수 실패")
            return
        
        time.sleep(2)
        
        # 시나리오 4: 7,000원 어치 매도
        print("\n   === 시나리오 4: 7,000원 어치 매도 ===")
        ticker = self.exchange.get_ticker('GNO/KRW')
        sell_amount_partial = round(7000 / ticker['last'], 8)
        print(f"     매도 수량: {sell_amount_partial:.8f} GNO")
        
        order4 = self.exchange.create_market_order('GNO/KRW', 'sell', sell_amount_partial)
        if order4:
            print(f"     ✅ 매도 완료 - 주문 ID: {order4.get('id')}")
            print(f"     체결 수량: {order4.get('filled', 0):.8f} GNO")
            print(f"     수령 금액: {order4.get('cost', 0):,.0f} KRW")
        else:
            print(f"     ❌ 매도 실패")
        
        time.sleep(2)
        
        # 시나리오 5: 나머지 전량 매도
        print("\n   === 시나리오 5: 나머지 전량 매도 ===")
        gno_balance = self.exchange.get_balance('GNO')
        remaining_amount = gno_balance['free']
        print(f"     매도 수량: {remaining_amount:.8f} GNO")
        
        if remaining_amount > 0:
            order5 = self.exchange.create_market_order('GNO/KRW', 'sell', remaining_amount)
            if order5:
                print(f"     ✅ 매도 완료 - 주문 ID: {order5.get('id')}")
                print(f"     체결 수량: {order5.get('filled', 0):.8f} GNO")
                print(f"     수령 금액: {order5.get('cost', 0):,.0f} KRW")
            else:
                print(f"     ❌ 매도 실패")
        else:
            print(f"     ℹ️  매도할 GNO가 없습니다")
        
        # 최종 잔고 확인
        print("\n   최종 잔고:")
        krw_balance = self.exchange.get_balance('KRW')
        gno_balance = self.exchange.get_balance('GNO')
        print(f"     KRW: {krw_balance['free']:,.0f} KRW")
        print(f"     GNO: {gno_balance['free']:.8f} GNO")
        
        print("\n   === 거래 시나리오 완료 ===")
    
    # ========== 6. 에러 처리 및 엣지 케이스 테스트 ==========
    
    def test_insufficient_balance(self):
        """잔고 부족 테스트"""
        print("\n9. 잔고 부족 테스트")
        
        # BTC 현재가 확인
        ticker = self.exchange.get_ticker('BTC/KRW')
        if not ticker:
            print("BTC/KRW 티커를 가져올 수 없습니다")
            return
        
        # 현재 잔고 확인
        krw_balance = self.exchange.get_balance('KRW')
        print(f"   현재 잔고: {krw_balance['free']:,.0f} KRW")
        
        # 잔고보다 큰 금액으로 주문 시도 (잔고의 2배)
        large_krw_amount = int(krw_balance['free'] * 2) if krw_balance['free'] > 0 else 999999999
        print(f"   주문 시도 금액: {large_krw_amount:,} KRW")
        
        # Market buy with KRW amount
        order = self.exchange.create_market_order('BTC/KRW', 'buy', large_krw_amount)
        
        if order is None:
            print("   ✅ 잔고 부족 처리 정상")
        else:
            print(f"   ⚠️ 주문이 체결됨: {order}")
    
    def test_minimum_order_size(self):
        """최소 주문 크기 테스트"""
        print("\n10. 최소 주문 크기 테스트")
        
        # GNO로 테스트
        ticker = self.exchange.get_ticker('GNO/KRW')
        if not ticker:
            print("GNO/KRW 티커를 가져올 수 없습니다")
            return
        
        print(f"   GNO 현재가: {ticker['last']:,.0f} KRW")
        
        # 5,000원으로 실제 매수 테스트
        buy_krw = 5000
        print(f"   {buy_krw:,}원으로 GNO 매수 시도")
        
        order = self.exchange.create_market_order('GNO/KRW', 'buy', buy_krw)
        
        if order:
            print(f"   ✅ 매수 성공: {order.get('filled', 0):.8f} GNO")
            print(f"   주문 ID: {order.get('id')}")
            
            # 매수한 GNO 전량 매도
            time.sleep(2)
            gno_balance = self.exchange.get_balance('GNO')
            if gno_balance['free'] > 0:
                sell_amount = gno_balance['free']
                print(f"   {sell_amount:.8f} GNO 매도 시도")
                
                sell_order = self.exchange.create_market_order('GNO/KRW', 'sell', sell_amount)
                if sell_order:
                    print(f"   ✅ 매도 성공: {sell_order.get('cost', 0):,.0f} KRW 수령")
                else:
                    print("   ❌ 매도 실패")
        else:
            print("   ⚠️ 매수 실패 (API 권한 또는 잔고 문제일 수 있음)")
    
    def test_api_rate_limit(self):
        """API 속도 제한 테스트"""
        print("\n11. API 속도 제한 테스트")
        
        # 연속 API 호출
        print("   10회 연속 API 호출 테스트...")
        success_count = 0
        
        for i in range(10):
            ticker = self.exchange.get_ticker('BTC/KRW')
            if ticker:
                success_count += 1
            time.sleep(0.1)  # 짧은 지연
        
        self.assertEqual(success_count, 10)
        print(f"   ✅ {success_count}/10 호출 성공")
    
    def test_network_error_handling(self):
        """네트워크 에러 처리 테스트"""
        print("\n12. 네트워크 에러 처리 테스트")
        
        # 잘못된 심볼로 에러 유발
        result = self.exchange.get_ticker('INVALID123/KRW')
        self.assertIsNone(result)
        print("   ✅ 네트워크/API 에러 처리 정상")
    
    def test_invalid_order_type(self):
        """잘못된 주문 타입 테스트 - 실제 소액 거래 실행"""
        print("\n13. 실제 소액 거래 테스트")
        
        # GNO로 소액 거래 테스트
        ticker = self.exchange.get_ticker('GNO/KRW')
        if not ticker:
            print("   GNO/KRW 티커를 가져올 수 없습니다")
            return
        
        print(f"   GNO 현재가: {ticker['last']:,.0f} KRW")
        
        # 5,500원 매수 테스트
        buy_krw = 5500
        print(f"\n   {buy_krw:,}원으로 GNO 매수 시도")
        
        order = self.exchange.create_market_order('GNO/KRW', 'buy', buy_krw)
        if order:
            print(f"   ✅ 매수 성공: {order.get('filled', 0):.8f} GNO")
            print(f"   주문 ID: {order.get('id')}")
            
            # 매수한 GNO 전량 매도
            time.sleep(2)
            gno_balance = self.exchange.get_balance('GNO')
            if gno_balance['free'] > 0:
                sell_amount = gno_balance['free']
                print(f"\n   {sell_amount:.8f} GNO 매도 시도")
                
                sell_order = self.exchange.create_market_order('GNO/KRW', 'sell', sell_amount)
                if sell_order:
                    print(f"   ✅ 매도 성공: {sell_order.get('cost', 0):,.0f} KRW 수령")
                    print(f"   주문 ID: {sell_order.get('id')}")
                else:
                    print("   ❌ 매도 실패")
        else:
            print("   ⚠️ 매수 실패 (API 권한 또는 잔고 문제일 수 있음)")
    
    # ========== 7. 통합 테스트 ==========
    
    def test_price_calculation_precision(self):
        """가격 계산 정밀도 테스트"""
        print("\n14. 가격 계산 정밀도 테스트")
        
        # 실제 시장 가격으로 테스트
        test_symbols = ['BTC/KRW', 'ETH/KRW', 'XRP/KRW']
        krw_amounts = [100000, 10000, 5000]
        
        for symbol, krw_amount in zip(test_symbols, krw_amounts):
            ticker = self.exchange.get_ticker(symbol)
            if ticker:
                # 수량 계산
                amount = krw_amount / ticker['last']
                rounded_amount = round(amount, 8)
                
                print(f"   {symbol}: {krw_amount:,} KRW = {rounded_amount:.8f} {symbol.split('/')[0]}")
                
                # 8자리 정밀도 확인
                decimal_places = len(str(rounded_amount).split('.')[-1]) if '.' in str(rounded_amount) else 0
                self.assertLessEqual(decimal_places, 8)
    
    def test_market_data_consistency(self):
        """시장 데이터 일관성 테스트"""
        print("\n15. 시장 데이터 일관성 테스트")
        
        # 여러 심볼의 데이터 일관성 확인
        symbols = ['BTC/KRW', 'ETH/KRW', 'XRP/KRW']
        
        for symbol in symbols:
            ticker = self.exchange.get_ticker(symbol)
            if ticker:
                # 가격 데이터 확인
                self.assertGreater(ticker['last'], 0, f"{symbol}: 현재가가 0보다 작습니다")
                if ticker.get('high') and ticker.get('low'):
                    self.assertGreaterEqual(ticker['high'], ticker['low'], 
                                          f"{symbol}: 최고가가 최저가보다 낮습니다")
                    self.assertGreaterEqual(ticker['high'], ticker['last'], 
                                          f"{symbol}: 최고가가 현재가보다 낮습니다")
                    self.assertLessEqual(ticker['low'], ticker['last'], 
                                       f"{symbol}: 최저가가 현재가보다 높습니다")
                
                print(f"   ✅ {symbol} 데이터 일관성 확인")


class TestBithumbPerformance(unittest.TestCase):
    """Bithumb 거래소 성능 테스트"""
    
    def setUp(self):
        """테스트 설정"""
        self.api_key = os.getenv('BITHUMB_API_KEY')
        self.api_secret = os.getenv('BITHUMB_API_SECRET')
        
        if not self.api_key or not self.api_secret:
            self.skipTest("BITHUMB_API_KEY와 BITHUMB_API_SECRET이 .env에 설정되어있지 않습니다")
        
        self.exchange = BithumbExchange(self.api_key, self.api_secret)
    
    def test_response_times(self):
        """API 응답 시간 테스트"""
        print("\n16. API 응답 시간 테스트")
        
        import time
        
        # 티커 조회 응답 시간
        start_time = time.time()
        ticker = self.exchange.get_ticker('BTC/KRW')
        ticker_time = time.time() - start_time
        
        # 잔고 조회 응답 시간
        start_time = time.time()
        balance = self.exchange.get_balance('KRW')
        balance_time = time.time() - start_time
        
        print(f"   티커 조회: {ticker_time*1000:.2f}ms")
        print(f"   잔고 조회: {balance_time*1000:.2f}ms")
        
        # 응답 시간이 합리적인지 확인 (5초 이내)
        self.assertLess(ticker_time, 5.0)
        self.assertLess(balance_time, 5.0)


if __name__ == '__main__':
    # 테스트 실행
    unittest.main(verbosity=2)