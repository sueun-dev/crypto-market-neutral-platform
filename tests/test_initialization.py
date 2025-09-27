#!/usr/bin/env python3
"""
Test initialization and setup of the hedge bot
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.exchanges import ExchangeManager
from src.pricing import PriceAnalyzer
from src.trading import TradeExecutor
from config import EXCHANGES_CONFIG, ENTRY_AMOUNT, MAX_ENTRIES, PRICE_DIFF_THRESHOLD
from src import utils

def test_api_validation():
    """Test API key validation"""
    print("\n=== Testing API Key Validation ===")

    api_status = utils.validate_api_keys(EXCHANGES_CONFIG)
    print(f"API Status: {api_status}")

    active_exchanges = [ex for ex, status in api_status.items() if status]

    if active_exchanges:
        print(f"✅ Active exchanges: {', '.join([ex.upper() for ex in active_exchanges])}")
    else:
        print("⚠️ No exchanges configured with API keys")

    return active_exchanges

def test_exchange_initialization(use_public=True):
    """Test exchange manager initialization"""
    print("\n=== Testing Exchange Initialization ===")

    try:
        exchange_manager = ExchangeManager()
        exchanges = exchange_manager.initialize_exchanges(use_public_api=use_public)

        print(f"✅ Initialized {len(exchanges)} exchanges:")
        for name in exchanges.keys():
            print(f"   - {name.upper()}")

        return exchange_manager
    except Exception as e:
        print(f"❌ Failed to initialize exchanges: {e}")
        return None

def test_market_loading(exchange_manager, coin="BTC"):
    """Test market loading for a specific coin"""
    print(f"\n=== Testing Market Loading for {coin} ===")

    try:
        symbols = exchange_manager.load_markets_for_coin(coin)

        print(f"✅ Loaded markets for {coin}:")
        for exchange, syms in symbols.items():
            print(f"   {exchange.upper()}:")
            print(f"      Spot: {syms['spot']}")
            print(f"      Perp: {syms['perp']}")

        return True
    except Exception as e:
        print(f"❌ Failed to load markets: {e}")
        return False

def test_price_fetching(exchange_manager):
    """Test price fetching"""
    print("\n=== Testing Price Fetching ===")

    try:
        price_analyzer = PriceAnalyzer(exchange_manager)
        prices = price_analyzer.fetch_all_prices()

        if prices:
            print("✅ Successfully fetched prices:")
            for exchange, data in prices.items():
                print(f"   {exchange.upper()}:")
                print(f"      Spot: Bid ${data['spot_bid']:.2f}, Ask ${data['spot_ask']:.2f}")
                print(f"      Perp: Bid ${data['perp_bid']:.2f}, Ask ${data['perp_ask']:.2f}")
        else:
            print("⚠️ No price data received")

        return price_analyzer
    except Exception as e:
        print(f"❌ Failed to fetch prices: {e}")
        return None

def test_best_opportunity(price_analyzer):
    """Test finding best hedge opportunity"""
    print("\n=== Testing Best Opportunity Detection ===")

    try:
        spot_ex, perp_ex, spot_price, perp_price, spread = price_analyzer.find_best_hedge_opportunity()

        if spot_ex and perp_ex:
            print(f"✅ Found best opportunity:")
            print(f"   Buy Spot: {spot_ex.upper()} @ ${spot_price:.2f}")
            print(f"   Sell Perp: {perp_ex.upper()} @ ${perp_price:.2f}")
            print(f"   Spread: {utils.format_percentage(spread)}")

            if spread >= PRICE_DIFF_THRESHOLD:
                print(f"   ✅ READY TO ENTER (threshold: {utils.format_percentage(PRICE_DIFF_THRESHOLD)})")
            else:
                print(f"   ⏳ Below threshold (need: {utils.format_percentage(PRICE_DIFF_THRESHOLD)})")
        else:
            print("⚠️ Could not find hedge opportunity")

        return spot_ex, perp_ex
    except Exception as e:
        print(f"❌ Failed to find opportunity: {e}")
        return None, None

def test_configuration():
    """Test configuration display"""
    print("\n=== Configuration ===")
    print(f"Entry Amount: ${ENTRY_AMOUNT}")
    print(f"Max Entries: {MAX_ENTRIES}")
    print(f"Spread Threshold: {utils.format_percentage(PRICE_DIFF_THRESHOLD)}")

def main():
    """Run all initialization tests"""
    print("=" * 60)
    print("HEDGE BOT INITIALIZATION TEST")
    print("=" * 60)

    # Test configuration
    test_configuration()

    # Test API validation
    active_exchanges = test_api_validation()

    # Test exchange initialization (using public API for testing)
    exchange_manager = test_exchange_initialization(use_public=True)

    if not exchange_manager:
        print("\n❌ Cannot proceed without exchange manager")
        return

    # Test with BTC by default
    coin = "BTC"
    print(f"\n테스트 코인: {coin}")

    # Test market loading
    if not test_market_loading(exchange_manager, coin):
        print("\n❌ Cannot proceed without markets")
        return

    # Test price fetching
    price_analyzer = test_price_fetching(exchange_manager)

    if not price_analyzer:
        print("\n❌ Cannot proceed without price analyzer")
        return

    # Test opportunity detection
    test_best_opportunity(price_analyzer)

    print("\n" + "=" * 60)
    print("✅ All initialization tests completed!")
    print("=" * 60)

if __name__ == "__main__":
    main()