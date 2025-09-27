import sys
import time
from datetime import datetime
from src.exchanges import ExchangeManager
from src.pricing import PriceAnalyzer
from src.trading import TradeExecutor
from config import (
    ENTRY_AMOUNT,
    MAX_ENTRIES,
    PRICE_DIFF_THRESHOLD,
    SLEEP_SEC,
    EXCHANGES_CONFIG
)
from src import utils

def main():
    """Main execution function"""

    # Mode selection
    print("\n" + "="*60)
    print("헤지 모드 선택")
    print("="*60)
    print("1. 자동 모드 - 모든 거래소에서 최적 조합 찾기")
    print("2. 수동 모드 - 특정 거래소 선택")

    mode = input("\n모드 선택 (1 or 2) [1]: ").strip() or "1"

    spot_exchange_filter = None
    perp_exchange_filter = None

    if mode == "2":
        print("\n사용 가능한 거래소: gateio, bybit, okx")
        print("Enter를 누르면 모든 거래소 검색")

        spot_input = input("현물 거래소 지정 (예: gateio): ").strip().lower()
        perp_input = input("선물 거래소 지정 (예: bybit): ").strip().lower()

        if spot_input in ['gateio', 'bybit', 'okx']:
            spot_exchange_filter = spot_input
            print(f"현물: {spot_input.upper()}로 제한")
        else:
            print("현물: 모든 거래소에서 검색")

        if perp_input in ['gateio', 'bybit', 'okx']:
            perp_exchange_filter = perp_input
            print(f"선물: {perp_input.upper()}로 제한")
        else:
            print("선물: 모든 거래소에서 검색")

    # Interactive coin selection
    coin = input("\n어떤 심볼을 분석할까요? [BTC]: ").strip().upper() or "BTC"
    print(f"\n선택된 코인: {coin}")

    # Validate API keys
    api_status = utils.validate_api_keys(EXCHANGES_CONFIG)
    active_exchanges = [ex for ex, status in api_status.items() if status]

    if not active_exchanges:
        print("❌ No exchanges configured")
        print("\nPlease set API keys in .env file:")
        for exchange in EXCHANGES_CONFIG.keys():
            print(f"  • {exchange.upper()}_API_KEY")
            print(f"  • {exchange.upper()}_API_SECRET")
            if exchange == 'okx':
                print(f"  • {exchange.upper()}_API_PASSWORD")
        sys.exit(1)

    print("Configuration")
    print(f"Coin: {coin}")
    print(f"Active Exchanges: {', '.join([ex.upper() for ex in active_exchanges])}")
    print(f"Entry Amount: ${ENTRY_AMOUNT}")
    print(f"Max Entries: {MAX_ENTRIES}")
    print(f"Spread Threshold: {utils.format_percentage(PRICE_DIFF_THRESHOLD)}")

    exchange_manager = ExchangeManager()
    exchange_manager.initialize_exchanges()

    print(f"Loading {coin} markets...")
    exchange_manager.load_markets_for_coin(coin)

    price_analyzer = PriceAnalyzer(exchange_manager)
    trade_executor = TradeExecutor(exchange_manager)

    # Check funding rates before starting
    print("\n📊 펀딩비 체크 중...")
    print("="*50)

    prices = price_analyzer.fetch_all_prices()
    has_negative_funding = False

    for exchange_name, price_data in prices.items():
        if 'funding_rate' in price_data:
            funding_rate = price_data['funding_rate']
            status = "✅" if funding_rate >= 0 else "❌"
            print(f"{exchange_name.upper():10} 펀딩비: {funding_rate:+.4%} {status}")
            if funding_rate < 0:
                has_negative_funding = True
        elif 'perp_bid' in price_data:
            print(f"{exchange_name.upper():10} 펀딩비: 데이터 없음 ⚠️")

    print("="*50)

    if has_negative_funding:
        print("\n⚠️ 경고: 음수 펀딩비가 있는 거래소가 있습니다.")
        print("숏 포지션에서 펀딩비를 지불해야 할 수 있습니다.")

    proceed = input("\n계속 진행하시겠습니까? (y/n) [y]: ").strip().lower() or "y"
    if proceed != 'y':
        print("\n프로그램을 종료합니다.")
        sys.exit(0)

    print("\n✅ System ready. Monitoring prices...\n")

    entry_count = 0
    try:
        while entry_count < MAX_ENTRIES:

            spot_ex, perp_ex, spot_price, perp_price, spread = price_analyzer.find_best_hedge_opportunity(
                spot_filter=spot_exchange_filter,
                perp_filter=perp_exchange_filter
            )

            if not spot_ex or not perp_ex:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] No price data available")
                time.sleep(SLEEP_SEC)
                continue

            print(f"\n📊 Best Opportunity:")
            print(f"  Buy:  {spot_ex.upper()} @ {utils.format_price(spot_price)}")
            print(f"  Sell: {perp_ex.upper()} @ {utils.format_price(perp_price)}")
            print(f"  Spread: {utils.format_percentage(spread)}")

            # Show market condition
            if spread > 0:
                print(f"  Status: 콘탱고 상황입니다 ✅")
            elif spread < 0:
                print(f"  Status: 백워데이션 상황입니다 ⚠️")
            else:
                print(f"  Status: 중립 상황입니다")

            # Show funding rate for the selected perp exchange
            prices = price_analyzer.fetch_all_prices()
            if perp_ex in prices and 'funding_rate' in prices[perp_ex]:
                funding_rate = prices[perp_ex]['funding_rate']
                funding_status = "✅" if funding_rate >= 0 else "⚠️"
                print(f"  Funding: {funding_rate:+.4%} {funding_status}")

            if spread >= PRICE_DIFF_THRESHOLD:
                print(f"  ✅ READY TO ENTER")
            else:
                print(f"  ⏳ Waiting (need {utils.format_percentage(PRICE_DIFF_THRESHOLD)})")

            if spread >= PRICE_DIFF_THRESHOLD:
                print(f"\n🎯 Opportunity detected! Executing hedge...")
                success = trade_executor.execute_hedge(
                    spot_ex, perp_ex, spot_price, perp_price, coin,
                    entry_amount=ENTRY_AMOUNT
                )

                if success:
                    entry_count += 1
                    print(f"Entry count: {entry_count}/{MAX_ENTRIES}")
                    print(f"\n⏳ Waiting {SLEEP_SEC} seconds before next check...")
                else:
                    print(f"\n⚠️ Trade failed. Retrying in {SLEEP_SEC} seconds...")

            time.sleep(SLEEP_SEC)

        print(f"\n✅ Maximum entries ({MAX_ENTRIES}) reached. Bot stopped.")

    except KeyboardInterrupt:
        print(f"\n\n⛔ Bot stopped by user")
        print(f"Total entries executed: {entry_count}")

    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()