#!/usr/bin/env python3
"""
Cross-exchange delta-neutral hedge testing
Tests all possible combinations with $30 USDT
"""
import sys
import time
from datetime import datetime
from itertools import permutations

# Use test config instead of regular config
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

from src.exchanges import ExchangeManager
from src.pricing import PriceAnalyzer
from src.trading import TradeExecutor
from src import utils

def test_specific_combination(spot_exchange: str, perp_exchange: str, coin: str = "BTC"):
    """Test a specific spot-perp exchange combination"""
    print(f"\n{'='*60}")
    print(f"Testing: {spot_exchange.upper()} (Spot) <-> {perp_exchange.upper()} (Perp) for {coin}")
    print(f"{'='*60}")

    try:
        # Initialize exchange manager
        exchange_manager = ExchangeManager()

        # Only initialize the two exchanges we're testing
        test_exchanges = {}
        for ex_name in [spot_exchange, perp_exchange]:
            if ex_name in config.EXCHANGES_CONFIG:
                api_config = config.EXCHANGES_CONFIG[ex_name]
                if api_config.get('apiKey') and api_config.get('secret'):
                    test_exchanges[ex_name] = api_config

        if len(test_exchanges) < 2:
            print(f"⚠️ Need both {spot_exchange} and {perp_exchange} configured")
            return False

        # Initialize only needed exchanges
        exchange_manager.exchanges = {}
        exchange_manager.symbols = {}

        for exchange_name, api_config in test_exchanges.items():
            exchange_manager._create_exchange_pair(exchange_name, api_config, use_public_api=False)

        # Load markets
        exchange_manager.load_markets_for_coin(coin)

        # Initialize analyzers
        price_analyzer = PriceAnalyzer(exchange_manager)
        trade_executor = TradeExecutor(exchange_manager)

        # Fetch current prices
        prices = price_analyzer.fetch_all_prices()

        if spot_exchange not in prices or perp_exchange not in prices:
            print(f"❌ Could not fetch prices for {spot_exchange} or {perp_exchange}")
            return False

        # Get specific prices
        spot_price = prices[spot_exchange]['spot_ask']
        perp_price = prices[perp_exchange]['perp_bid']
        spread = (perp_price - spot_price) / spot_price

        print(f"\n📊 Price Analysis:")
        print(f"   {spot_exchange.upper()} Spot Ask: ${spot_price:.2f}")
        print(f"   {perp_exchange.upper()} Perp Bid: ${perp_price:.2f}")
        print(f"   Spread: {utils.format_percentage(spread)}")

        # Check if spread meets threshold
        if spread < config.PRICE_DIFF_THRESHOLD:
            print(f"   ⏳ Below threshold ({utils.format_percentage(config.PRICE_DIFF_THRESHOLD)})")

            # Ask user if they want to proceed anyway
            response = input(f"\nExecute test trade anyway? (y/n): ").strip().lower()
            if response != 'y':
                print("   Skipping this combination")
                return False
        else:
            print(f"   ✅ Above threshold!")

        # Ask for confirmation before executing
        print(f"\n⚠️ Ready to execute hedge with ${config.ENTRY_AMOUNT}:")
        print(f"   1. Buy {coin} on {spot_exchange.upper()} spot")
        print(f"   2. Short {coin} on {perp_exchange.upper()} perp (1x leverage)")
        print(f"\n   💰 실제 거래가 실행됩니다! REAL API!")

        confirm = input("\n실제로 실행하시겠습니까? Execute real trade? (yes/n): ").strip().lower()
        if confirm != 'yes':
            print("   Trade cancelled - 거래 취소됨")
            return False

        # Execute the hedge
        print(f"\n🎯 Executing hedge...")
        success = trade_executor.execute_hedge(
            spot_exchange, perp_exchange, spot_price, perp_price, coin
        )

        if success:
            print(f"\n✅ Successfully hedged {spot_exchange} <-> {perp_exchange}")

            # Check positions
            positions = trade_executor.check_positions(coin)
            print(f"\n📋 Current Positions:")
            for ex_name, pos_data in positions.items():
                if pos_data['spot_balance'] > 0:
                    print(f"   {ex_name.upper()} Spot: {pos_data['spot_balance']:.6f} {coin}")
                if pos_data['perp_position']:
                    print(f"   {ex_name.upper()} Perp: {pos_data['perp_position']}")

            print(f"\n{'='*60}")
            print("✅ 테스트 완료! 거래소를 확인하세요.")
            print(f"{'='*60}")

            # Wait for user to verify
            input("\n거래소에서 포지션을 확인하신 후 Enter를 눌러 계속하세요...")

            return True
        else:
            print(f"\n❌ Hedge execution failed")
            return False

    except Exception as e:
        print(f"\n❌ Error testing {spot_exchange} <-> {perp_exchange}: {e}")
        return False

def test_all_combinations(coin: str = "BTC"):
    """Test all possible exchange combinations"""

    # Check which exchanges are configured
    configured_exchanges = []
    for exchange_name in ['gateio', 'bybit', 'okx']:
        api_config = config.EXCHANGES_CONFIG.get(exchange_name, {})
        if api_config.get('apiKey') and api_config.get('secret'):
            configured_exchanges.append(exchange_name)

    if len(configured_exchanges) < 2:
        print("❌ Need at least 2 exchanges configured")
        return

    print(f"\n🔍 Configured exchanges: {', '.join([ex.upper() for ex in configured_exchanges])}")

    # Generate all possible spot-perp combinations
    combinations = list(permutations(configured_exchanges, 2))

    print(f"\n📋 Testing {len(combinations)} possible combinations:")
    for i, (spot_ex, perp_ex) in enumerate(combinations, 1):
        print(f"   {i}. {spot_ex.upper()} (spot) <-> {perp_ex.upper()} (perp)")

    # Test each combination
    results = []
    for i, (spot_ex, perp_ex) in enumerate(combinations, 1):
        print(f"\n{'='*60}")
        print(f"테스트 {i}/{len(combinations)}")
        print(f"{'='*60}")

        success = test_specific_combination(spot_ex, perp_ex, coin)
        results.append({
            'spot': spot_ex,
            'perp': perp_ex,
            'success': success
        })

        if i < len(combinations):
            print(f"\n{'='*60}")
            next_spot, next_perp = combinations[i]
            print(f"다음 테스트: {next_spot.upper()} (현물) <-> {next_perp.upper()} (선물)")
            continue_test = input("계속하시겠습니까? (yes/n): ").strip().lower()
            if continue_test != 'yes':
                print("테스트 중단")
                break

    # Summary
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print(f"{'='*60}")

    for result in results:
        status = "✅" if result['success'] else "❌"
        print(f"{status} {result['spot'].upper()} <-> {result['perp'].upper()}")

    successful = sum(1 for r in results if r['success'])
    print(f"\nTotal: {successful}/{len(results)} successful")

def main():
    """Main test execution"""
    print("="*60)
    print("CROSS-EXCHANGE DELTA-NEUTRAL HEDGE TEST")
    print(f"Test Amount: ${config.ENTRY_AMOUNT}")
    print(f"Leverage: {config.FUTURES_LEVERAGE}x (forced)")
    print("="*60)

    # Ask for coin selection
    coin = input("\n어떤 코인을 테스트할까요? [BTC]: ").strip().upper() or "BTC"

    # Ask for test mode
    print("\n테스트 모드 선택:")
    print("1. 특정 조합 테스트")
    print("2. 모든 조합 테스트")

    mode = input("\n선택 (1 or 2): ").strip()

    if mode == "1":
        # Manual combination selection
        print("\n사용 가능한 거래소: gateio, bybit, okx")
        spot_ex = input("현물 거래소 선택: ").strip().lower()
        perp_ex = input("선물 거래소 선택: ").strip().lower()

        if spot_ex not in ['gateio', 'bybit', 'okx'] or perp_ex not in ['gateio', 'bybit', 'okx']:
            print("❌ Invalid exchange selection")
            return

        if spot_ex == perp_ex:
            print("⚠️ Warning: Same exchange for spot and perp (not optimal for arbitrage)")

        test_specific_combination(spot_ex, perp_ex, coin)

    elif mode == "2":
        # Test all combinations
        confirm = input("\n⚠️ This will test ALL exchange combinations. Continue? (y/n): ").strip().lower()
        if confirm == 'y':
            test_all_combinations(coin)
    else:
        print("❌ Invalid selection")

if __name__ == "__main__":
    main()