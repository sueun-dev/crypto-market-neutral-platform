"""Kimchi premium calculator for exit strategy decisions."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class KimchiPremiumCalculator:
    def __init__(self, exchange_manager, korean_manager):
        self.exchange_manager = exchange_manager
        self.korean_manager = korean_manager

    def get_overseas_price(self, coin: str, exchange: str) -> Optional[float]:
        """Gets the current price from an overseas exchange where we hold shorts.

        Args:
            coin: Target coin symbol.
            exchange: Exchange identifier.

        Returns:
            Latest perp last price in USDT, or None on failure.
        """
        try:
            ex = self.exchange_manager.exchanges[exchange]["perp"]
            symbol = self.exchange_manager.resolve_symbol(exchange, "perp", coin)
            if not symbol:
                raise RuntimeError(f"No perp symbol template for {exchange}")
            ticker = ex.fetch_ticker(symbol)
            return ticker["last"]  # Current price in USDT
        except Exception as e:
            logger.warning("⚠️ Failed to get %s price: %s", exchange, e)
            return None

    def get_usdt_krw_price(self) -> Optional[float]:
        """Gets the current USDT/KRW price from connected Korean exchanges."""
        try:
            # Try Bithumb first
            for exchange_name in ["bithumb", "upbit"]:
                exchange = self.korean_manager.exchanges.get(exchange_name)
                if exchange:
                    ticker = exchange.fetch_ticker("USDT/KRW")
                    if ticker and ticker.get("last"):
                        return ticker["last"]
        except Exception:
            pass

        # Unable to fetch rate
        logger.error("❌ Failed to fetch USDT/KRW rate from Korean exchanges")
        return None

    def get_korean_bid_price(self, coin: str, exchange: str) -> Optional[float]:
        """Gets the best bid price from a Korean exchange."""
        try:
            ex = self.korean_manager.exchanges.get(exchange)
            if not ex:
                return None

            orderbook = ex.fetch_order_book(f"{coin}/KRW")
            if orderbook and orderbook.get("bids"):
                # Get best bid price (즉시 매도 가능한 가격)
                best_bid = orderbook["bids"][0][0]
                return best_bid
        except Exception as e:
            logger.warning("⚠️ Failed to get %s bid price: %s", exchange, e)
            return None
        return None

    def calculate_kimchi_premium(
        self, coin: str, korean_exchange: str, overseas_exchange: str
    ) -> Tuple[Optional[float], Dict[str, Any]]:
        """Calculates the real-time kimchi premium.

        Args:
            coin: Target coin symbol.
            korean_exchange: Korean exchange identifier.
            overseas_exchange: Overseas exchange identifier.

        Returns:
            Tuple of (premium percentage or None, price details dictionary).
        """
        import concurrent.futures

        details: Dict[str, Any] = {
            "korean_exchange": korean_exchange,
            "overseas_exchange": overseas_exchange,
            "timestamp": datetime.now().isoformat(),
        }

        # 병렬로 가격 정보 가져오기 (3배 빠름)
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            # 3개의 API 호출을 동시에 실행
            overseas_future = executor.submit(self.get_overseas_price, coin, overseas_exchange)
            usdt_future = executor.submit(self.get_usdt_krw_price)
            korean_future = executor.submit(self.get_korean_bid_price, coin, korean_exchange)

            # 결과 수집
            overseas_price = overseas_future.result()
            usdt_krw = usdt_future.result()
            korean_bid = korean_future.result()

        if not overseas_price:
            return None, details
        details["overseas_price_usdt"] = overseas_price

        if not usdt_krw:
            return None, details
        details["usdt_krw_rate"] = usdt_krw

        # Convert overseas price to KRW
        overseas_price_krw = overseas_price * usdt_krw
        details["overseas_price_krw"] = overseas_price_krw

        if not korean_bid:
            return None, details
        details["korean_bid_price"] = korean_bid

        # Calculate premium
        # Premium = (Korean Price - Overseas Price) / Overseas Price
        premium = ((korean_bid - overseas_price_krw) / overseas_price_krw) * 100
        details["kimchi_premium"] = premium

        return premium, details

    def monitor_premium(self, coin: str, korean_exchanges: list, overseas_positions: Dict, threshold: float = 3.0):
        """Monitors kimchi premium across exchanges and prints opportunities.

        Args:
            coin: Coin symbol.
            korean_exchanges: List of Korean exchanges to check.
            overseas_positions: Dict of overseas positions.
            threshold: Premium threshold to trigger action.
        """
        logger.info("\n📊 김치 프리미엄 모니터링 시작")
        logger.info("목표 프리미엄: %s%% 이상", threshold)
        logger.info("=" * 60)

        results = []

        for korean_ex in korean_exchanges:
            for overseas_ex, position in overseas_positions.items():
                if position.get("side") != "short":
                    continue

                premium, details = self.calculate_kimchi_premium(coin, korean_ex, overseas_ex)

                if premium is not None:
                    status = "🔥 SELL" if premium >= threshold else "⏳ WAIT"

                    logger.info("\n%s vs %s:", korean_ex.upper(), overseas_ex.upper())
                    logger.info("  한국 매도가: ₩%s", f"{details['korean_bid_price']:,.0f}")
                    logger.info(
                        "  해외 가격: $%.2f (₩%s)",
                        details["overseas_price_usdt"],
                        f"{details['overseas_price_krw']:,.0f}",
                    )
                    logger.info("  김치 프리미엄: %.2f%% %s", premium, status)

                    results.append(
                        {
                            "korean_exchange": korean_ex,
                            "overseas_exchange": overseas_ex,
                            "premium": premium,
                            "details": details,
                            "should_sell": premium >= threshold,
                        }
                    )

        return results

    def get_best_opportunity(self, results: list) -> Optional[Dict]:
        """Returns the best kimchi premium opportunity from a result list."""
        if not results:
            return None

        # Filter opportunities above threshold
        good_opportunities = [r for r in results if r["should_sell"]]

        if not good_opportunities:
            return None

        # Sort by premium descending
        good_opportunities.sort(key=lambda x: x["premium"], reverse=True)

        return good_opportunities[0]
