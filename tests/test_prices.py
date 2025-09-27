#!/usr/bin/env python3
"""
Real-time price testing - NO ACTUAL TRADES
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
from datetime import datetime
from src.exchanges import ExchangeManager
from src.pricing import PriceAnalyzer
from config import ENTRY_AMOUNT, PRICE_DIFF_THRESHOLD
from src import utils

def test_prices():
    """Test real-time prices without executing trades"""

    # Interactive coin selection
    coin = input("\n어떤 심볼을 분석할까요? [BTC]: ").strip().upper() or "BTC"

    print(f"\n{'='*60}")
    print(f"PRICE MONITOR - TEST MODE (NO TRADES)")
    print(f"{'='*60}")
    print(f"Coin: {coin}")
    print(f"Test Amount: ${ENTRY_AMOUNT}")
    print(f"Spread Threshold: {utils.format_percentage(PRICE_DIFF_THRESHOLD)}")
    print(f"{'='*60}\n")

    # Initialize with public API (no credentials needed for price data)
    print("Connecting to exchanges (public API)...")
    exchange_manager = ExchangeManager()

    try:
        # Try with credentials first, fallback to public
        exchange_manager.initialize_exchanges(use_public_api=False)
    except:
        print("Using public API for price data...")
        exchange_manager.initialize_exchanges(use_public_api=True)

    print(f"\nLoading {coin} markets...")
    exchange_manager.load_markets_for_coin(coin)

    price_analyzer = PriceAnalyzer(exchange_manager)

    print(f"\n✅ Starting real-time price monitoring...\n")
    print("Press Ctrl+C to stop\n")

    try:
        while True:
            # Get current timestamp
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Fetch and analyze prices
            analysis = price_analyzer.analyze_opportunities(detailed=True)

            # Clear screen for better readability (optional)
            # print("\033[2J\033[H")  # Uncomment to clear screen

            print(f"\n{'='*80}")
            print(f"TIMESTAMP: {timestamp}")
            print(f"{'='*80}")

            # Show prices for all exchanges
            if analysis['prices']:
                print(f"\n📊 CURRENT PRICES:")
                print(f"{'Exchange':<10} {'Spot Bid':<12} {'Spot Ask':<12} {'Perp Bid':<12} {'Perp Ask':<12} {'Spreads':<20}")
                print("-" * 80)

                for exchange, data in analysis['prices'].items():
                    spot_spread = data['spot']['spread']
                    perp_spread = data['perp']['spread']
                    print(f"{exchange.upper():<10} "
                          f"{utils.format_price(data['spot']['bid']):<12} "
                          f"{utils.format_price(data['spot']['ask']):<12} "
                          f"{utils.format_price(data['perp']['bid']):<12} "
                          f"{utils.format_price(data['perp']['ask']):<12} "
                          f"S:{utils.format_price(spot_spread, 4)} P:{utils.format_price(perp_spread, 4)}")

            # Show best opportunity
            if analysis['best_opportunity']:
                opp = analysis['best_opportunity']
                print(f"\n🎯 BEST HEDGE OPPORTUNITY:")
                print(f"   Buy Spot:  {opp['spot_exchange'].upper()} @ {utils.format_price(opp['spot_price'])}")
                print(f"   Sell Perp: {opp['perp_exchange'].upper()} @ {utils.format_price(opp['perp_price'])}")
                print(f"   Spread:    {utils.format_percentage(opp['spread_pct'])}")
                print(f"   Net Profit: ${opp['estimated_profit']:.2f} per ${ENTRY_AMOUNT} traded")

                if opp['meets_threshold']:
                    print(f"\n   ✅ ENTRY CONDITIONS MET!")
                    print(f"   Expected quantity: {ENTRY_AMOUNT / opp['spot_price']:.6f} {coin}")
                else:
                    print(f"\n   ⏳ Waiting for {utils.format_percentage(PRICE_DIFF_THRESHOLD)} spread")

            # Show top 3 spreads
            if analysis['all_spreads']:
                print(f"\n📈 TOP SPREADS:")
                for i, spread in enumerate(analysis['all_spreads'][:3], 1):
                    emoji = "✅" if spread['meets_threshold'] else "⏳"
                    print(f"   {i}. {spread['spot_exchange'].upper()} → {spread['perp_exchange'].upper()}: "
                          f"{utils.format_percentage(spread['spread_pct'])} {emoji}")

            # Show Bithumb KRW price
            try:
                krw_price = price_analyzer.get_bithumb_krw_price()
                console.print(f"\n[bold]💱 Bithumb USDT/KRW:[/bold] [yellow]{krw_price:,.0f} KRW[/yellow]")
            except:
                pass

            time.sleep(5)  # Update every 5 seconds

    except KeyboardInterrupt:
        console.print(f"\n\n[bold red]⛔ Price monitoring stopped[/bold red]")

    except Exception as e:
        console.print(f"\n[bold red]❌ Error: {e}[/bold red]")

if __name__ == "__main__":
    test_prices()