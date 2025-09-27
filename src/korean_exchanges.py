"""
Korean Exchange Manager - Bithumb and Upbit integration for exit strategy
"""
import ccxt
import time
from typing import Dict, Optional, List, Tuple
from datetime import datetime
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.constants import KOREAN_MIN_SELL_VALUE_KRW, EXIT_PRICE_LEVELS, MAX_RETRY_ATTEMPTS, RETRY_DELAY_SECONDS

class KoreanExchangeManager:
    def __init__(self):
        self.exchanges = {}
        self.initialize_exchanges()

    def initialize_exchanges(self):
        """Initialize Bithumb and Upbit connections in parallel"""
        import concurrent.futures

        def connect_bithumb():
            bithumb_key = os.getenv('BITHUMB_API_KEY', '')
            bithumb_secret = os.getenv('BITHUMB_SECRET_KEY', '')

            if bithumb_key and bithumb_secret:
                try:
                    exchange = ccxt.bithumb({
                        'apiKey': bithumb_key,
                        'secret': bithumb_secret,
                        'enableRateLimit': True,
                    })
                    exchange.load_markets()
                    print("✅ Bithumb connected")
                    return 'bithumb', exchange
                except Exception as e:
                    print(f"⚠️ Bithumb connection failed: {e}")
            else:
                print("❌ Bithumb API keys not found")
            return None, None

        def connect_upbit():
            upbit_key = os.getenv('UPBIT_API_KEY', '')
            upbit_secret = os.getenv('UPBIT_API_SECRET', '')

            if upbit_key and upbit_secret:
                try:
                    exchange = ccxt.upbit({
                        'apiKey': upbit_key,
                        'secret': upbit_secret,
                        'enableRateLimit': True,
                    })
                    exchange.load_markets()
                    print("✅ Upbit connected")
                    return 'upbit', exchange
                except Exception as e:
                    print(f"⚠️ Upbit connection failed: {e}")
            return None, None

        # 병렬로 연결
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(connect_bithumb),
                executor.submit(connect_upbit)
            ]

            for future in concurrent.futures.as_completed(futures):
                name, exchange = future.result()
                if name and exchange:
                    self.exchanges[name] = exchange

    def check_balance(self, exchange: str, coin: str) -> float:
        """Check coin balance on Korean exchange with retry mechanism"""
        if exchange not in self.exchanges:
            return 0.0

        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                balance = self.exchanges[exchange].fetch_balance()


                # 코인 잔고 가져오기 (free + used 모두 체크)
                coin_balance = balance.get(coin, {})
                free = float(coin_balance.get('free', 0.0))
                used = float(coin_balance.get('used', 0.0))
                total = float(coin_balance.get('total', 0.0))

                # total이 있으면 total 사용, 없으면 free 사용
                result = total if total > 0 else free
                return result
            except ccxt.NetworkError as e:
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    print(f"⚠️ {exchange.upper()} network error, retrying ({attempt + 1}/{MAX_RETRY_ATTEMPTS})...")
                    time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                else:
                    print(f"❌ {exchange.upper()} balance check failed after {MAX_RETRY_ATTEMPTS} attempts: {e}")
                    return 0.0
            except Exception as e:
                print(f"❌ {exchange.upper()} balance check error: {e}")
                return 0.0

    def place_limit_orders(self, coin: str, total_quantity: float,
                          target_prices: Dict, distribution: Dict[str, float]) -> Dict:
        """
        Place limit sell orders on Korean exchanges

        Args:
            coin: Coin symbol (e.g., 'BTC')
            total_quantity: Total quantity to sell
            target_prices: Target prices from position tracker
            distribution: {'bithumb': 0.5, 'upbit': 0.5} or {'bithumb': 1.0} etc.
        """
        orders = {}

        for exchange, allocation in distribution.items():
            if exchange not in self.exchanges or allocation == 0:
                continue

            sell_quantity = total_quantity * allocation
            balance = self.check_balance(exchange, coin)

            if balance < sell_quantity * 0.95:  # 95% threshold for safety
                print(f"⚠️ {exchange.upper()} insufficient balance: {balance:.6f} < {sell_quantity:.6f}")
                continue

            # Place multiple limit orders at different price levels
            price_levels = EXIT_PRICE_LEVELS

            exchange_orders = []
            for price_key, portion in price_levels:
                order_qty = sell_quantity * portion
                order_price = target_prices[price_key]

                # Check minimum sell value requirement (5,000 KRW)
                order_value_krw = order_qty * order_price
                if order_value_krw < KOREAN_MIN_SELL_VALUE_KRW:
                    print(f"⚠️ {exchange.upper()} 주문 금액이 최소 판매금액(₩{KOREAN_MIN_SELL_VALUE_KRW:,}) 미만: ₩{order_value_krw:,.0f}")
                    print(f"   수량 조정 필요: {order_qty:.6f} {coin} @ ₩{order_price:,.0f}")
                    continue

                try:
                    # Adjust for exchange-specific requirements
                    if exchange == 'bithumb':
                        symbol = f'{coin}/KRW'
                        # Bithumb requires price in KRW integer
                        order_price = int(order_price)
                    elif exchange == 'upbit':
                        symbol = f'{coin}/KRW'
                        # Upbit price formatting
                        if order_price >= 1000000:
                            order_price = int(order_price / 1000) * 1000
                        elif order_price >= 100000:
                            order_price = int(order_price / 100) * 100
                        elif order_price >= 10000:
                            order_price = int(order_price / 10) * 10
                        else:
                            order_price = int(order_price)

                    # Place limit sell order
                    order = self.exchanges[exchange].create_limit_sell_order(
                        symbol=symbol,
                        amount=order_qty,
                        price=order_price
                    )

                    exchange_orders.append({
                        'id': order['id'],
                        'price': order_price,
                        'quantity': order_qty,
                        'filled': 0,  # Initialize filled amount
                        'status': 'open',
                        'timestamp': datetime.now().isoformat()
                    })

                    print(f"✅ {exchange.upper()} 지정가 주문: {order_qty:.6f} {coin} @ ₩{order_price:,.0f}")

                except Exception as e:
                    print(f"⚠️ {exchange.upper()} order failed: {e}")

            if exchange_orders:
                orders[exchange] = exchange_orders

        return orders

    def check_order_status(self, exchange: str, order_id: str, symbol: str) -> Dict:
        """Check status of a specific order with retry mechanism"""
        if exchange not in self.exchanges:
            return {'status': 'error', 'filled': 0}

        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                order = self.exchanges[exchange].fetch_order(order_id, symbol)
                return {
                    'status': order['status'],  # 'open', 'closed', 'canceled'
                    'filled': order.get('filled', 0),
                    'remaining': order.get('remaining', 0),
                    'price': order.get('price', 0)
                }
            except ccxt.NetworkError as e:
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    print(f"⚠️ Order status network error, retrying ({attempt + 1}/{MAX_RETRY_ATTEMPTS})...")
                    time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                else:
                    print(f"❌ Order status check failed after {MAX_RETRY_ATTEMPTS} attempts: {e}")
                    return {'status': 'error', 'filled': 0}
            except Exception as e:
                print(f"❌ Order status check error: {e}")
                return {'status': 'error', 'filled': 0}

    def cancel_order(self, exchange: str, order_id: str, symbol: str) -> bool:
        """Cancel a specific order"""
        if exchange not in self.exchanges:
            return False

        try:
            self.exchanges[exchange].cancel_order(order_id, symbol)
            print(f"✅ {exchange.upper()} order {order_id} canceled")
            return True
        except Exception as e:
            print(f"⚠️ Cancel order failed: {e}")
            return False

    def get_current_price(self, exchange: str, coin: str) -> Optional[float]:
        """Get current price on Korean exchange with retry mechanism"""
        if exchange not in self.exchanges:
            return None

        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                ticker = self.exchanges[exchange].fetch_ticker(f'{coin}/KRW')
                return ticker['last']
            except ccxt.NetworkError as e:
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    print(f"⚠️ Price fetch network error, retrying ({attempt + 1}/{MAX_RETRY_ATTEMPTS})...")
                    time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                else:
                    print(f"❌ Price fetch failed after {MAX_RETRY_ATTEMPTS} attempts: {e}")
                    return None
            except Exception as e:
                print(f"❌ Price fetch error: {e}")
                return None

    def verify_exchange_health(self, exchange: str) -> bool:
        """Verify exchange is healthy and ready for trading"""
        if exchange not in self.exchanges:
            print(f"❌ {exchange.upper()} not connected")
            return False

        try:
            # Check if exchange is online
            self.exchanges[exchange].fetch_status()

            # Try to fetch ticker to verify market access
            ticker = self.exchanges[exchange].fetch_ticker('BTC/KRW')
            if ticker and ticker.get('last'):
                print(f"✅ {exchange.upper()} is healthy")
                return True
            else:
                print(f"⚠️ {exchange.upper()} market data unavailable")
                return False
        except Exception as e:
            print(f"❌ {exchange.upper()} health check failed: {e}")
            return False