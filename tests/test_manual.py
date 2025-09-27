#!/usr/bin/env python3
"""
Manual step-by-step cross-exchange hedge testing
완전 수동 단계별 테스트 - 실제 API 사용
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

from src.exchanges import ExchangeManager
from src.pricing import PriceAnalyzer
from src.trading import TradeExecutor
from src import utils

def manual_test():
    """Complete manual testing with step-by-step confirmation"""

    print("="*60)
    print("MANUAL CROSS-EXCHANGE HEDGE TEST")
    print("실제 API를 사용한 수동 테스트")
    print(f"테스트 금액: ${config.ENTRY_AMOUNT} USDT")
    print("="*60)

    # Step 1: Select coin
    print("\n[STEP 1] 코인 선택")
    coin = input("테스트할 코인 입력 [BTC]: ").strip().upper() or "BTC"
    print(f"선택된 코인: {coin}")

    # Step 2: Select exchanges
    print("\n[STEP 2] 거래소 선택")
    print("사용 가능: gateio, bybit, okx")

    spot_exchange = input("현물 매수할 거래소: ").strip().lower()
    perp_exchange = input("선물 숏 잡을 거래소: ").strip().lower()

    if spot_exchange not in ['gateio', 'bybit', 'okx'] or perp_exchange not in ['gateio', 'bybit', 'okx']:
        print("❌ 잘못된 거래소 이름")
        return

    print(f"\n선택 확인:")
    print(f"  현물: {spot_exchange.upper()}")
    print(f"  선물: {perp_exchange.upper()}")

    # Step 3: Initialize
    print("\n[STEP 3] 거래소 연결 중...")

    exchange_manager = ExchangeManager()

    # Connect only selected exchanges
    test_exchanges = {}
    for ex_name in [spot_exchange, perp_exchange]:
        if ex_name in config.EXCHANGES_CONFIG:
            api_config = config.EXCHANGES_CONFIG[ex_name]
            if api_config.get('apiKey') and api_config.get('secret'):
                test_exchanges[ex_name] = api_config
            else:
                print(f"❌ {ex_name.upper()} API 키가 없습니다")
                return

    exchange_manager.exchanges = {}
    exchange_manager.symbols = {}

    for exchange_name, api_config in test_exchanges.items():
        print(f"  연결 중: {exchange_name.upper()}...")
        exchange_manager._create_exchange_pair(exchange_name, api_config, use_public_api=False)
        print(f"  ✅ {exchange_name.upper()} 연결됨")

    # Step 4: Load markets
    print(f"\n[STEP 4] {coin} 마켓 로딩...")
    exchange_manager.load_markets_for_coin(coin)
    print("✅ 마켓 로드 완료")

    # Step 5: Check balances first
    print(f"\n[STEP 5] 잔고 확인...")
    for ex_name in [spot_exchange, perp_exchange]:
        try:
            spot_balance = exchange_manager.exchanges[ex_name]['spot'].fetch_balance()
            perp_balance = exchange_manager.exchanges[ex_name]['perp'].fetch_balance()

            print(f"\n{ex_name.upper()} 잔고:")
            print(f"  Spot USDT: ${spot_balance.get('USDT', {}).get('free', 0):.2f}")
            print(f"  Futures USDT: ${perp_balance.get('USDT', {}).get('free', 0):.2f}")
        except Exception as e:
            print(f"  {ex_name.upper()} 잔고 확인 실패: {e}")

    # Step 6: Check prices
    print(f"\n[STEP 6] 현재 가격 확인...")
    price_analyzer = PriceAnalyzer(exchange_manager)
    prices = price_analyzer.fetch_all_prices()

    if spot_exchange not in prices or perp_exchange not in prices:
        print(f"❌ 가격 데이터를 가져올 수 없습니다")
        return

    spot_price = prices[spot_exchange]['spot_ask']
    perp_price = prices[perp_exchange]['perp_bid']
    spread = (perp_price - spot_price) / spot_price

    print(f"\n현재 가격:")
    print(f"  {spot_exchange.upper()} 현물 매수가: ${spot_price:.2f}")
    print(f"  {perp_exchange.upper()} 선물 매도가: ${perp_price:.2f}")
    print(f"  스프레드: {utils.format_percentage(spread)}")

    # Step 7: Check minimum order size
    print(f"\n[STEP 7] 최소 주문 확인...")
    quantity = config.ENTRY_AMOUNT / spot_price
    print(f"  예상 주문 수량: {quantity:.6f} {coin}")
    print(f"  예상 주문 금액: ${config.ENTRY_AMOUNT}")

    # Final confirmation
    print(f"\n[STEP 8] 최종 확인")
    print("="*60)
    print(f"실행될 거래:")
    print(f"  1. {spot_exchange.upper()}에서 ${config.ENTRY_AMOUNT} 어치 {coin} 현물 매수")
    print(f"  2. {perp_exchange.upper()}에서 동일 수량 {coin} 선물 1x 숏")
    print(f"  예상 수량: {quantity:.6f} {coin}")
    print("="*60)

    print("\n⚠️  실제 거래가 실행됩니다! REAL MONEY!")
    confirm = input("정말로 실행하시겠습니까? Type 'EXECUTE' to confirm: ").strip()

    if confirm != 'EXECUTE':
        print("❌ 거래 취소됨")
        return

    # Step 9: Execute
    print("\n[STEP 9] 거래 실행 중...")
    trade_executor = TradeExecutor(exchange_manager)

    try:
        # Execute hedge with config entry amount
        success = trade_executor.execute_hedge(
            spot_exchange, perp_exchange, spot_price, perp_price, coin,
            entry_amount=config.ENTRY_AMOUNT
        )

        if success:
            print("\n✅ 거래 성공!")

            # Check positions
            print("\n포지션 확인 중...")
            positions = trade_executor.check_positions(coin)

            print(f"\n현재 포지션:")
            for ex_name, pos_data in positions.items():
                if pos_data['spot_balance'] > 0:
                    print(f"  {ex_name.upper()} 현물: {pos_data['spot_balance']:.6f} {coin}")
                if pos_data['perp_position']:
                    print(f"  {ex_name.upper()} 선물: {pos_data['perp_position']}")

            print("\n" + "="*60)
            print("✅ 테스트 완료!")
            print("거래소 웹/앱에서 직접 확인하세요:")
            print(f"  1. {spot_exchange.upper()} - 현물 잔고 확인")
            print(f"  2. {perp_exchange.upper()} - 선물 포지션 확인")
            print("="*60)

        else:
            print("\n❌ 거래 실패")

    except Exception as e:
        print(f"\n❌ 에러 발생: {e}")

    print("\n테스트 종료")

if __name__ == "__main__":
    manual_test()