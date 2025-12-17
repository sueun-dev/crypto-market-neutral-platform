"""Bybit Futures 거래소 클래스 (ccxt)."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import ccxt


class BybitExchange:
    """Bybit 선물 거래소 구현 (USDT Perpetual 기준)"""

    def __init__(self, api_credentials: Dict[str, str]):
        self.exchange_id = "bybit"
        self.api_key = api_credentials.get("apiKey")
        self.api_secret = api_credentials.get("secret")

        self.logger = logging.getLogger(f"{__name__}.{self.exchange_id}")

        # ccxt Bybit 설정 - USDT 선물 기본
        self.client = ccxt.bybit(
            {
                "apiKey": self.api_key,
                "secret": self.api_secret,
                "enableRateLimit": True,
                "options": {
                    "defaultType": "swap",
                    "defaultSubType": "linear",
                    "defaultSettle": "USDT",
                    "adjustForTimeDifference": True,
                },
            }
        )

        # 선물 마켓 정보 사전 로드
        self.markets: Dict[str, Dict] = {}
        self._load_markets()

    def _load_markets(self) -> None:
        """선물 마켓 정보 로드"""
        try:
            self.markets = self.client.load_markets()
            self.logger.info(f"Loaded {len(self.markets)} Bybit markets")
        except Exception as e:
            self.logger.error(f"Failed to load Bybit markets: {e}")
            self.markets = {}

    def get_balance(self, currency: str) -> Optional[Dict]:
        """특정 통화 잔고 조회"""
        try:
            balance = self.client.fetch_balance()

            # ccxt는 통화를 키로 제공
            wallet = balance.get(currency, {})
            free = float(wallet.get("free", 0) or 0)
            used = float(wallet.get("used", 0) or 0)
            total = float(wallet.get("total", free + used) or 0)

            return {"free": free, "used": used, "total": total}
        except Exception as e:
            self.logger.error(f"Failed to get balance for {currency}: {e}")
            return None

    def get_ticker(self, symbol: str) -> Optional[Dict]:
        """티커 조회"""
        try:
            ticker = self.client.fetch_ticker(symbol)
            return {
                "symbol": symbol,
                "last": float(ticker.get("last") or 0),
                "bid": float(ticker.get("bid")) if ticker.get("bid") is not None else None,
                "ask": float(ticker.get("ask")) if ticker.get("ask") is not None else None,
                "high": float(ticker.get("high") or 0),
                "low": float(ticker.get("low") or 0),
                "volume": float(ticker.get("baseVolume") or 0),
            }
        except Exception as e:
            self.logger.error(f"Failed to get ticker for {symbol}: {e}")
            return None

    def create_market_order(
        self, symbol: str, side: str, amount: float, params: Optional[Dict] = None
    ) -> Optional[Dict]:
        """시장가 주문 생성"""
        try:
            params = params.copy() if params else {}

            # reduce_only 키를 ccxt 형식에 맞게 매핑
            if "reduce_only" in params and "reduceOnly" not in params:
                params["reduceOnly"] = params.pop("reduce_only")

            # 수량 정밀도 반영
            precise_amount = float(self.client.amount_to_precision(symbol, amount))
            if precise_amount <= 0:
                self.logger.error(f"Order amount too small for {symbol}: {amount}")
                return None

            order = self.client.create_order(symbol, "market", side, precise_amount, None, params)

            self.logger.info(f"Market order placed: {symbol} {side} {precise_amount}")

            return {
                "id": order.get("id"),
                "symbol": symbol,
                "side": side,
                "amount": precise_amount,
                "status": order.get("status"),
                "filled": order.get("filled", 0),
            }
        except Exception as e:
            self.logger.error(f"Failed to create market order: {e}")
            return None

    def get_markets(self) -> Dict:
        """모든 마켓 정보 조회"""
        # ccxt가 제공하는 contractSize 키를 GateIO 형태로 매핑
        return {
            symbol: {"contract_size": market.get("contractSize") or market.get("contract_size") or 1}
            for symbol, market in self.markets.items()
            if market.get("swap") or market.get("future")
        }

    def set_leverage(self, symbol: str, leverage: int) -> bool:
        """레버리지 설정"""
        try:
            self.client.set_leverage(leverage, symbol)
            return True
        except Exception as e:
            self.logger.error(f"Failed to set leverage for {symbol}: {e}")
            return False

    def get_positions(self) -> List[Dict]:
        """현재 선물 포지션 조회"""
        try:
            positions = self.client.fetch_positions()
            result = []

            for pos in positions:
                contracts = abs(float(pos.get("contracts") or 0))
                if contracts == 0:
                    continue

                result.append(
                    {
                        "symbol": pos.get("symbol"),
                        "side": pos.get("side"),
                        "contracts": contracts,
                        "notional": abs(float(pos.get("notional") or 0)),
                        "mode": pos.get("marginMode"),
                        "mark_price": float(pos.get("markPrice") or 0),
                        "entry_price": float(pos.get("entryPrice") or 0),
                    }
                )

            return result
        except Exception as e:
            self.logger.error(f"Failed to get positions: {e}")
            return []

    @property
    def exchange(self):
        """ccxt 익스체인지 인스턴스 (호환성용)"""
        return self.client

    def fetch_positions(self, symbols=None):
        """ccxt 호환 메서드 (미사용)"""
        return self.get_positions()
