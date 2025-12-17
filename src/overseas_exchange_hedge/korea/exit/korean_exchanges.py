"""Korean exchange manager for Bithumb and Upbit integration."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from typing import Any, Dict, Optional, cast

import ccxt

from ...common.constants import (
    EXIT_PRICE_LEVELS,
    KOREAN_MIN_SELL_VALUE_KRW,
    KOREAN_PRICE_TICK_SIZES,
    MAX_RETRY_ATTEMPTS,
    RETRY_DELAY_SECONDS,
)

logger = logging.getLogger(__name__)


class KoreanExchangeManager:
    def __init__(self):
        self.exchanges = {}
        self.initialize_exchanges()

    def initialize_exchanges(self):
        """Initializes Bithumb and Upbit connections in parallel."""
        import concurrent.futures

        def connect_bithumb():
            bithumb_key = os.getenv("BITHUMB_API_KEY", "")
            bithumb_secret = os.getenv("BITHUMB_API_SECRET") or os.getenv("BITHUMB_SECRET_KEY", "")

            if bithumb_key and bithumb_secret:
                try:
                    params: Dict[str, Any] = {
                        "apiKey": bithumb_key,
                        "secret": bithumb_secret,
                        "enableRateLimit": True,
                    }
                    exchange = cast(ccxt.Exchange, ccxt.bithumb(cast(Any, params)))
                    exchange.load_markets()
                    logger.info("✅ Bithumb connected")
                    return "bithumb", exchange
                except Exception as e:
                    logger.warning("⚠️ Bithumb connection failed: %s", e)
            else:
                logger.error("❌ Bithumb API keys not found")
            return None, None

        def connect_upbit():
            upbit_key = os.getenv("UPBIT_API_KEY") or os.getenv("UPBIT_ACCESS_KEY", "")
            upbit_secret = os.getenv("UPBIT_API_SECRET") or os.getenv("UPBIT_SECRET_KEY", "")

            if upbit_key and upbit_secret:
                try:
                    params: Dict[str, Any] = {
                        "apiKey": upbit_key,
                        "secret": upbit_secret,
                        "enableRateLimit": True,
                    }
                    exchange = cast(ccxt.Exchange, ccxt.upbit(cast(Any, params)))
                    exchange.load_markets()
                    logger.info("✅ Upbit connected")
                    return "upbit", exchange
                except Exception as e:
                    logger.warning("⚠️ Upbit connection failed: %s", e)
            return None, None

        # 병렬로 연결
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(connect_bithumb), executor.submit(connect_upbit)]

            for future in concurrent.futures.as_completed(futures):
                name, exchange = future.result()
                if name and exchange:
                    self.exchanges[name] = exchange

    def check_balance(self, exchange: str, coin: str) -> float:
        """Checks coin balance on a Korean exchange with retry logic.

        Args:
            exchange: Exchange identifier.
            coin: Coin symbol.

        Returns:
            Available total balance for the coin.
        """
        if exchange not in self.exchanges:
            return 0.0

        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                balance = self.exchanges[exchange].fetch_balance()

                # 코인 잔고 가져오기 (free + used 모두 체크)
                coin_balance = balance.get(coin, {})
                free = float(coin_balance.get("free", 0.0))
                total = float(coin_balance.get("total", 0.0))

                # total이 있으면 total 사용, 없으면 free 사용
                result = total if total > 0 else free
                return result
            except ccxt.NetworkError as e:
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    logger.warning(
                        "⚠️ %s network error, retrying (%s/%s)...",
                        exchange.upper(),
                        attempt + 1,
                        MAX_RETRY_ATTEMPTS,
                    )
                    time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                else:
                    logger.error(
                        "❌ %s balance check failed after %s attempts: %s",
                        exchange.upper(),
                        MAX_RETRY_ATTEMPTS,
                        e,
                    )
                    return 0.0
            except Exception as e:
                logger.error("❌ %s balance check error: %s", exchange.upper(), e)
                return 0.0

        return 0.0

    def place_limit_orders(
        self,
        coin: str,
        total_quantity: float,
        target_prices: Dict[str, float],
        distribution: Dict[str, float],
    ) -> Dict:
        """Places limit sell orders on Korean exchanges.

        Args:
            coin: Coin symbol (e.g., "BTC").
            total_quantity: Total quantity to sell.
            target_prices: Target prices keyed by level.
            distribution: Portion per exchange (e.g., {"bithumb": 0.5}).

        Returns:
            Mapping of exchange to list of created orders.
        """
        orders = {}

        for exchange, allocation in distribution.items():
            if exchange not in self.exchanges or allocation == 0:
                continue

            sell_quantity = total_quantity * allocation
            balance = self.check_balance(exchange, coin)

            if balance < sell_quantity * 0.95:  # 95% threshold for safety
                logger.warning("⚠️ %s insufficient balance: %.6f < %.6f", exchange.upper(), balance, sell_quantity)
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
                    logger.warning(
                        "⚠️ %s 주문 금액이 최소 판매금액(₩%s) 미만: ₩%s",
                        exchange.upper(),
                        f"{KOREAN_MIN_SELL_VALUE_KRW:,}",
                        f"{order_value_krw:,.0f}",
                    )
                    logger.info("   수량 조정 필요: %.6f %s @ ₩%s", order_qty, coin, f"{order_price:,.0f}")
                    continue

                try:
                    # Adjust for exchange-specific requirements
                    symbol = f"{coin}/KRW"
                    order_price = self._normalize_price(exchange, order_price)
                    if order_price <= 0:
                        logger.warning(
                            "⚠️ %s price adjustment resulted in non-positive value; skipping order", exchange.upper()
                        )
                        continue

                    # Place limit sell order
                    order = self.exchanges[exchange].create_limit_sell_order(
                        symbol=symbol, amount=order_qty, price=order_price
                    )

                    exchange_orders.append(
                        {
                            "id": order["id"],
                            "price": order_price,
                            "quantity": order_qty,
                            "filled": 0,  # Initialize filled amount
                            "status": "open",
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

                    logger.info(
                        "✅ %s 지정가 주문: %.6f %s @ ₩%s", exchange.upper(), order_qty, coin, f"{order_price:,.0f}"
                    )

                except Exception as e:
                    logger.warning("⚠️ %s order failed: %s", exchange.upper(), e)

            if exchange_orders:
                orders[exchange] = exchange_orders

        return orders

    def check_order_status(self, exchange: str, order_id: str, symbol: str) -> Dict:
        """Checks the status of an order with retry logic."""
        if exchange not in self.exchanges:
            return {"status": "error", "filled": 0}

        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                order = self.exchanges[exchange].fetch_order(order_id, symbol)
                return {
                    "status": order["status"],  # 'open', 'closed', 'canceled'
                    "filled": order.get("filled", 0),
                    "remaining": order.get("remaining", 0),
                    "price": order.get("price", 0),
                }
            except ccxt.NetworkError as e:
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    logger.warning(
                        "⚠️ Order status network error, retrying (%s/%s)...",
                        attempt + 1,
                        MAX_RETRY_ATTEMPTS,
                    )
                    time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                else:
                    logger.error("❌ Order status check failed after %s attempts: %s", MAX_RETRY_ATTEMPTS, e)
                    return {"status": "error", "filled": 0}
            except Exception as e:
                logger.error("❌ Order status check error: %s", e)
                return {"status": "error", "filled": 0}

        return {"status": "error", "filled": 0}

    def cancel_order(self, exchange: str, order_id: str, symbol: str) -> bool:
        """Cancels a specific order."""
        if exchange not in self.exchanges:
            return False

        try:
            self.exchanges[exchange].cancel_order(order_id, symbol)
            logger.info("✅ %s order %s canceled", exchange.upper(), order_id)
            return True
        except Exception as e:
            logger.warning("⚠️ Cancel order failed: %s", e)
            return False

    def get_current_price(self, exchange: str, coin: str) -> Optional[float]:
        """Gets the current price on a Korean exchange with retry logic."""
        if exchange not in self.exchanges:
            return None

        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                ticker = self.exchanges[exchange].fetch_ticker(f"{coin}/KRW")
                return ticker["last"]
            except ccxt.NetworkError as e:
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    logger.warning(
                        "⚠️ Price fetch network error, retrying (%s/%s)...",
                        attempt + 1,
                        MAX_RETRY_ATTEMPTS,
                    )
                    time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                else:
                    logger.error("❌ Price fetch failed after %s attempts: %s", MAX_RETRY_ATTEMPTS, e)
                    return None
            except Exception as e:
                logger.error("❌ Price fetch error: %s", e)
                return None
        return None

    def get_usdt_krw_rate(self) -> Optional[float]:
        """Fetches the current USDT/KRW rate from connected Korean exchanges."""
        if not self.exchanges:
            logger.error("❌ No Korean exchanges connected for USDT/KRW rate")
            return None

        rates = []
        for name, exchange in self.exchanges.items():
            for attempt in range(MAX_RETRY_ATTEMPTS):
                try:
                    ticker = exchange.fetch_ticker("USDT/KRW")
                    price = ticker.get("last")
                    if price:
                        rates.append(float(price))
                        break
                except ccxt.NetworkError as e:
                    if attempt < MAX_RETRY_ATTEMPTS - 1:
                        logger.warning(
                            "⚠️ %s USDT/KRW network error, retrying (%s/%s)...",
                            name.upper(),
                            attempt + 1,
                            MAX_RETRY_ATTEMPTS,
                        )
                        time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                    else:
                        logger.error(
                            "❌ %s USDT/KRW fetch failed after %s attempts: %s", name.upper(), MAX_RETRY_ATTEMPTS, e
                        )
                except Exception as e:
                    logger.error("❌ %s USDT/KRW fetch error: %s", name.upper(), e)
                    break

        if rates:
            return sum(rates) / len(rates)

        logger.error("❌ Unable to fetch USDT/KRW rate from connected exchanges")
        return None

    def _normalize_price(self, exchange: str, price: float) -> float:
        """Clamps price to the exchange's allowed tick size."""
        tick_size = self._get_tick_size(exchange, price)
        if tick_size <= 0:
            return price

        price_dec = Decimal(str(price))
        tick_dec = Decimal(str(tick_size))
        steps = (price_dec / tick_dec).to_integral_value(rounding=ROUND_DOWN)
        normalized = steps * tick_dec
        if normalized <= 0:
            normalized = tick_dec
        return float(normalized)

    def _get_tick_size(self, exchange: str, price: float) -> float:
        """Returns the tick size for the given exchange/price."""
        table = KOREAN_PRICE_TICK_SIZES.get(exchange)
        if not table:
            return 1.0
        for threshold, tick in table:
            if price >= threshold:
                return float(tick)
        # fallback to smallest tick
        return float(table[-1][1])
