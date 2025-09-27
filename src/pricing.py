"""
Pricing module - handles price fetching and arbitrage analysis
"""
from typing import Dict, Tuple, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from .exchanges import ExchangeManager
from config import PRICE_DIFF_THRESHOLD, EXCHANGE_FEES

class PriceAnalyzer:
    def __init__(self, exchange_manager: ExchangeManager):
        self.exchange_manager = exchange_manager
        self.exchanges = exchange_manager.exchanges
        self.symbols = exchange_manager.symbols

    def fetch_funding_rate(self, exchange_name: str, symbol: str) -> Optional[float]:
        """Fetch current funding rate for perpetual contract"""
        try:
            exchange = self.exchanges[exchange_name]['perp']
            # Different exchanges have different methods for funding rate
            if exchange_name == 'bybit':
                # Bybit uses fetchFundingRate
                funding = exchange.fetch_funding_rate(symbol)
                return funding['fundingRate'] if funding else None
            elif exchange_name == 'gateio':
                # GateIO uses fetchFundingRate
                funding = exchange.fetch_funding_rate(symbol)
                return funding['fundingRate'] if funding else None
            elif exchange_name == 'okx':
                # OKX uses fetchFundingRate
                funding = exchange.fetch_funding_rate(symbol)
                return funding['fundingRate'] if funding else None
            else:
                return None
        except Exception as e:
            print(f"⚠️ {exchange_name.upper()} funding rate fetch failed: {e}")
            return None

    def fetch_all_prices(self) -> Dict[str, Dict[str, float]]:
        """Fetch current prices and funding rates from all exchanges in parallel"""
        prices = {}

        def fetch_exchange_prices(exchange_name: str) -> Tuple[str, Optional[Dict]]:
            """Fetch available spot and/or perp prices for one exchange"""
            try:
                result = {}

                # Check what markets are available for this exchange
                has_spot = 'spot' in self.symbols[exchange_name]
                has_perp = 'perp' in self.symbols[exchange_name]

                with ThreadPoolExecutor(max_workers=2) as executor:
                    futures = []

                    # Only fetch if market exists
                    if has_spot:
                        spot_future = executor.submit(
                            self.exchanges[exchange_name]['spot'].fetch_order_book,
                            self.symbols[exchange_name]['spot']
                        )
                        futures.append(('spot', spot_future))

                    if has_perp:
                        perp_future = executor.submit(
                            self.exchanges[exchange_name]['perp'].fetch_order_book,
                            self.symbols[exchange_name]['perp']
                        )
                        futures.append(('perp', perp_future))

                    # Collect results
                    for market_type, future in futures:
                        try:
                            ob = future.result(timeout=5)
                            if market_type == 'spot' and ob and ob.get('asks') and ob.get('bids'):
                                result['spot_bid'] = ob['bids'][0][0]
                                result['spot_ask'] = ob['asks'][0][0]
                                result['spot_bid_volume'] = ob['bids'][0][1]
                                result['spot_ask_volume'] = ob['asks'][0][1]
                            elif market_type == 'perp' and ob and ob.get('asks') and ob.get('bids'):
                                result['perp_bid'] = ob['bids'][0][0]
                                result['perp_ask'] = ob['asks'][0][0]
                                result['perp_bid_volume'] = ob['bids'][0][1]
                                result['perp_ask_volume'] = ob['asks'][0][1]
                                # Fetch funding rate for perp
                                if 'perp' in self.symbols[exchange_name]:
                                    funding_rate = self.fetch_funding_rate(
                                        exchange_name,
                                        self.symbols[exchange_name]['perp']
                                    )
                                    if funding_rate is not None:
                                        result['funding_rate'] = funding_rate
                        except:
                            pass

                # Return data if we got any prices
                if result:
                    result['timestamp'] = datetime.now()
                    return exchange_name, result

                return exchange_name, None
            except Exception as e:
                print(f"⚠️ {exchange_name.upper()} price fetch failed: {e}")
                return exchange_name, None

        # Fetch all exchanges in parallel
        with ThreadPoolExecutor(max_workers=len(self.symbols)) as executor:
            futures = [executor.submit(fetch_exchange_prices, ex) for ex in self.symbols.keys()]

            for future in as_completed(futures):
                exchange_name, price_data = future.result()
                if price_data:
                    prices[exchange_name] = price_data

        return prices

    def find_best_hedge_opportunity(self, spot_filter: Optional[str] = None, perp_filter: Optional[str] = None) -> Tuple[Optional[str], Optional[str], Optional[float], Optional[float], Optional[float]]:
        """Find optimal hedge opportunity across exchanges

        Args:
            spot_filter: If specified, only consider this exchange for spot
            perp_filter: If specified, only consider this exchange for perp
        """
        prices = self.fetch_all_prices()

        if not prices:
            return None, None, None, None, None

        # Find cheapest spot (lowest ask price for buying)
        best_spot_exchange = None
        best_spot_price = float('inf')

        for exchange_name, price_data in prices.items():
            # Check if this exchange has spot prices
            if 'spot_ask' in price_data:
                # Apply filter if specified
                if spot_filter and exchange_name != spot_filter:
                    continue
                if price_data['spot_ask'] < best_spot_price:
                    best_spot_price = price_data['spot_ask']
                    best_spot_exchange = exchange_name

        # Find most expensive perpetual (highest bid price for shorting)
        best_perp_exchange = None
        best_perp_price = 0

        for exchange_name, price_data in prices.items():
            # Check if this exchange has perp prices
            if 'perp_bid' in price_data:
                # Apply filter if specified
                if perp_filter and exchange_name != perp_filter:
                    continue
                # No automatic filtering of negative funding rates
                # User already confirmed they want to proceed
                if price_data['perp_bid'] > best_perp_price:
                    best_perp_price = price_data['perp_bid']
                    best_perp_exchange = exchange_name

        # Calculate spread with safety check
        if best_spot_exchange and best_perp_exchange and best_spot_price > 0:
            spread = (best_perp_price - best_spot_price) / best_spot_price
            return best_spot_exchange, best_perp_exchange, best_spot_price, best_perp_price, spread

        return None, None, None, None, None

    def analyze_opportunities(self) -> Dict:
        """Analyze all arbitrage opportunities"""
        prices = self.fetch_all_prices()

        if not prices:
            return {'status': 'error', 'message': 'No price data available'}

        # Find best opportunity
        spot_ex, perp_ex, spot_price, perp_price, spread = self.find_best_hedge_opportunity()

        analysis = {
            'timestamp': datetime.now().isoformat(),
            'prices': {},
            'best_opportunity': None,
            'all_spreads': []
        }

        # Add price data
        for exchange_name, price_data in prices.items():
            analysis['prices'][exchange_name] = {
                'spot': {
                    'bid': price_data['spot_bid'],
                    'ask': price_data['spot_ask'],
                    'spread': price_data['spot_ask'] - price_data['spot_bid']
                },
                'perp': {
                    'bid': price_data['perp_bid'],
                    'ask': price_data['perp_ask'],
                    'spread': price_data['perp_ask'] - price_data['perp_bid']
                }
            }

        # Calculate all possible spreads
        for spot_exchange, spot_data in prices.items():
            for perp_exchange, perp_data in prices.items():
                spread_pct = (perp_data['perp_bid'] - spot_data['spot_ask']) / spot_data['spot_ask']
                analysis['all_spreads'].append({
                    'spot_exchange': spot_exchange,
                    'perp_exchange': perp_exchange,
                    'spot_price': spot_data['spot_ask'],
                    'perp_price': perp_data['perp_bid'],
                    'spread_pct': spread_pct,
                    'meets_threshold': spread_pct >= PRICE_DIFF_THRESHOLD
                })

        # Sort by spread
        analysis['all_spreads'].sort(key=lambda x: x['spread_pct'], reverse=True)

        # Best opportunity
        if spot_ex and perp_ex:
            analysis['best_opportunity'] = {
                'spot_exchange': spot_ex,
                'perp_exchange': perp_ex,
                'spot_price': spot_price,
                'perp_price': perp_price,
                'spread_pct': spread,
                'meets_threshold': spread >= PRICE_DIFF_THRESHOLD,
                'estimated_profit': self.calculate_locked_spread(
                    spot_price, perp_price, spot_ex, perp_ex
                )
            }

        return analysis

    def calculate_locked_spread(self, spot_price: float, perp_price: float,
                                spot_exchange: str, perp_exchange: str) -> float:
        """Calculate the locked-in spread profit after fees"""
        # Get fees
        spot_fee = EXCHANGE_FEES[spot_exchange]['spot']['taker']
        perp_fee = EXCHANGE_FEES[perp_exchange]['futures']['taker']

        # Initial spread (contango)
        gross_spread = perp_price - spot_price

        # Total fees on entry
        total_fees = (spot_price * spot_fee) + (perp_price * perp_fee)

        # Net locked spread after fees
        net_spread = gross_spread - total_fees

        return net_spread