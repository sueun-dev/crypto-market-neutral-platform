#!/usr/bin/env python3
"""
Test minimum order sizes for all exchanges
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.exchanges import ExchangeManager

def test_minimums(coin: str = "IP"):
    """Check minimum order sizes for a coin across exchanges"""

    print(f"\n{'='*60}")
    print(f"CHECKING MINIMUM ORDER SIZES FOR {coin}")
    print(f"{'='*60}\n")

    exchange_manager = ExchangeManager()
    exchange_manager.initialize_exchanges(use_public_api=True)

    try:
        symbols = exchange_manager.load_markets_for_coin(coin)

        for exchange_name in symbols.keys():
            print(f"\n{exchange_name.upper()}:")

            # Get market info
            spot_market = symbols[exchange_name].get('spot_market', {})
            perp_market = symbols[exchange_name].get('perp_market', {})

            # Spot minimums
            spot_limits = spot_market.get('limits', {}) if spot_market else {}
            spot_amount = spot_limits.get('amount', {})
            spot_cost = spot_limits.get('cost', {})

            print(f"  SPOT ({symbols[exchange_name]['spot']}):")
            print(f"    Min amount: {spot_amount.get('min', 'N/A')} {coin}")
            print(f"    Min cost: ${spot_cost.get('min', 'N/A')} USDT")

            # Perp minimums
            perp_limits = perp_market.get('limits', {}) if perp_market else {}
            perp_amount = perp_limits.get('amount', {})
            perp_cost = perp_limits.get('cost', {})

            print(f"  PERP ({symbols[exchange_name]['perp']}):")
            print(f"    Min amount: {perp_amount.get('min', 'N/A')} {coin}")
            print(f"    Min cost: ${perp_cost.get('min', 'N/A')} USDT")

            # Calculate minimum USDT needed at current price
            ex = exchange_manager.get_exchange(exchange_name)
            if ex:
                try:
                    ticker = ex['spot'].fetch_ticker(symbols[exchange_name]['spot'])
                    price = ticker.get('last', 0)

                    if price and spot_amount.get('min'):
                        min_usdt_spot = float(spot_amount.get('min')) * price
                        print(f"    → Min USDT for spot: ${min_usdt_spot:.2f}")

                    if price and perp_amount.get('min'):
                        min_usdt_perp = float(perp_amount.get('min')) * price
                        print(f"    → Min USDT for perp: ${min_usdt_perp:.2f}")
                except:
                    pass

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    coin = input("Enter coin to check [IP]: ").strip().upper() or "IP"
    test_minimums(coin)