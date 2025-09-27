"""
Exchange management module - handles connections and initialization
"""
import ccxt
from typing import Dict, Optional, Tuple
from config import EXCHANGES_CONFIG, SYMBOL_FORMATS, FUTURES_LEVERAGE

class ExchangeManager:
    def __init__(self):
        self.exchanges: Dict[str, Dict[str, ccxt.Exchange]] = {}
        self.symbols: Dict[str, Dict[str, str]] = {}

    def initialize_exchanges(self, use_public_api: bool = False) -> Dict[str, Dict[str, ccxt.Exchange]]:
        """Initialize all available exchanges in parallel"""
        import concurrent.futures

        def connect_exchange(exchange_name, config, use_public_api):
            """Connect to a single exchange"""
            if use_public_api or (config['apiKey'] and config['secret']):
                try:
                    result = self._create_exchange_pair(exchange_name, config, use_public_api)
                    print(f"✅ {exchange_name.upper()} connected")
                    return exchange_name, result
                except Exception as e:
                    print(f"⚠️ {exchange_name.upper()} failed: {e}")
            return exchange_name, None

        # 병렬로 모든 거래소 연결
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = []
            for exchange_name, config in EXCHANGES_CONFIG.items():
                future = executor.submit(connect_exchange, exchange_name, config, use_public_api)
                futures.append(future)

            # 결과 수집
            for future in concurrent.futures.as_completed(futures):
                exchange_name, result = future.result()
                # _create_exchange_pair가 이미 self.exchanges에 추가하므로 별도 처리 불필요

        if not self.exchanges:
            raise RuntimeError("No exchanges available. Check API keys.")

        return self.exchanges

    def _create_exchange_pair(self, exchange_name: str, config: dict, use_public_api: bool):
        """Create spot and perpetual exchange instances"""

        if exchange_name == 'gateio':
            # GateIO spot configuration
            spot_params = {
                'options': config['spot_options'],
                'enableRateLimit': True,
            }
            # GateIO perpetual configuration
            perp_params = {
                'options': config['perp_options'],
                'enableRateLimit': True,
            }

            if not use_public_api:
                spot_params.update({
                    'apiKey': config['apiKey'],
                    'secret': config['secret'],
                })
                perp_params.update({
                    'apiKey': config['apiKey'],
                    'secret': config['secret'],
                })

            self.exchanges[exchange_name] = {
                'spot': ccxt.gateio(spot_params),
                'perp': ccxt.gateio(perp_params)
            }

        elif exchange_name == 'bybit':
            # Bybit uses unified account now
            # For spot trading
            spot_params = {
                'options': {
                    'defaultType': 'spot',
                    'recvWindow': 10000,
                    'adjustForTimeDifference': True,  # Important for Bybit
                },
                'enableRateLimit': True,
            }
            # For USDT perpetual (linear)
            perp_params = {
                'options': {
                    'defaultType': 'linear',  # USDT perpetual
                    'recvWindow': 10000,
                    'adjustForTimeDifference': True,
                },
                'enableRateLimit': True,
            }

            if not use_public_api:
                spot_params.update({
                    'apiKey': config['apiKey'],
                    'secret': config['secret'],
                })
                perp_params.update({
                    'apiKey': config['apiKey'],
                    'secret': config['secret'],
                })

            self.exchanges[exchange_name] = {
                'spot': ccxt.bybit(spot_params),
                'perp': ccxt.bybit(perp_params)
            }

        elif exchange_name == 'okx':
            # OKX configuration
            spot_params = {
                'options': {
                    'defaultType': 'spot',
                },
                'enableRateLimit': True,
            }
            # OKX USDT perpetual swap
            perp_params = {
                'options': {
                    'defaultType': 'swap',  # Perpetual swap
                },
                'enableRateLimit': True,
            }

            if not use_public_api:
                # OKX requires passphrase
                spot_params.update({
                    'apiKey': config['apiKey'],
                    'secret': config['secret'],
                    'password': config.get('password', ''),  # OKX calls it passphrase
                })
                perp_params.update({
                    'apiKey': config['apiKey'],
                    'secret': config['secret'],
                    'password': config.get('password', ''),
                })

            self.exchanges[exchange_name] = {
                'spot': ccxt.okx(spot_params),
                'perp': ccxt.okx(perp_params)
            }

    def load_markets_for_coin(self, coin: str) -> Dict[str, Dict[str, str]]:
        """Load markets and validate symbols for a specific coin"""

        for exchange_name, exchange_pair in self.exchanges.items():
            try:
                # Load markets
                exchange_pair['spot'].load_markets()
                exchange_pair['perp'].load_markets()

                # Get symbol formats - CCXT unified format
                spot_symbol = f'{coin}/USDT'  # Standard spot format

                # Perpetual symbol varies by exchange
                if exchange_name == 'gateio':
                    perp_symbol = f'{coin}/USDT:USDT'  # GateIO format
                elif exchange_name == 'bybit':
                    perp_symbol = f'{coin}/USDT:USDT'  # Bybit linear format
                elif exchange_name == 'okx':
                    perp_symbol = f'{coin}/USDT:USDT'  # OKX swap format
                else:
                    perp_symbol = f'{coin}/USDT:USDT'  # Default

                # Store ANY available market (spot OR perp OR both)
                self.symbols[exchange_name] = {}

                # Check and store spot if available
                if spot_symbol in exchange_pair['spot'].symbols:
                    self.symbols[exchange_name]['spot'] = spot_symbol
                    self.symbols[exchange_name]['spot_market'] = exchange_pair['spot'].markets[spot_symbol]
                    print(f"✅ {exchange_name.upper()}: {spot_symbol} (Spot)")
                else:
                    print(f"❌ {exchange_name.upper()}: No spot market for {coin}")

                # Check and store perp if available
                if perp_symbol in exchange_pair['perp'].symbols:
                    self.symbols[exchange_name]['perp'] = perp_symbol
                    self.symbols[exchange_name]['perp_market'] = exchange_pair['perp'].markets[perp_symbol]
                    print(f"✅ {exchange_name.upper()}: {perp_symbol} (Perp)")
                else:
                    print(f"❌ {exchange_name.upper()}: No perp market for {coin}")

                # Only remove if neither spot nor perp is available
                if not self.symbols[exchange_name]:
                    del self.symbols[exchange_name]
                    print(f"⚠️ {exchange_name.upper()}: No markets available for {coin}")

            except Exception as e:
                print(f"⚠️ {exchange_name.upper()} markets load failed: {e}")

        if not self.symbols:
            raise RuntimeError(f"No exchanges have {coin} trading pairs")

        return self.symbols

    def set_leverage(self, exchange_name: str, leverage: int = FUTURES_LEVERAGE) -> bool:
        """Set leverage for a specific exchange - ALWAYS enforce 1x for delta neutral"""

        if exchange_name not in self.exchanges or exchange_name not in self.symbols:
            return False

        perp_ex = self.exchanges[exchange_name]['perp']
        perp_symbol = self.symbols[exchange_name]['perp']

        # FORCE leverage to 1 for delta neutral hedging
        leverage = 1
        print(f"⚙️ Setting {exchange_name.upper()} leverage to {leverage}x (delta-neutral mode)")

        try:
            if exchange_name == 'gateio':
                # GateIO leverage setting - skip margin mode as it's not supported
                try:
                    perp_ex.set_position_mode(False, perp_symbol)  # one-way mode
                except:
                    pass  # Might already be set

                try:
                    # GateIO doesn't support setMarginMode, skip it
                    result = perp_ex.set_leverage(leverage, perp_symbol,
                        params={'leverage': str(leverage)})
                    print(f"   ✅ GateIO leverage set to {leverage}x")
                except Exception as e:
                    print(f"   ⚠️ GateIO leverage setting: {e}")

            elif exchange_name == 'bybit':
                # Bybit unified account
                try:
                    # Bybit V5 API - position mode is account-wide
                    perp_ex.set_position_mode(False)  # one-way mode (account level)
                except:
                    pass  # May already be set or not changeable

                try:
                    perp_ex.set_margin_mode('isolated', perp_symbol)
                except:
                    pass  # May already be set

                result = perp_ex.set_leverage(leverage, perp_symbol)
                print(f"   ✅ Bybit leverage set: {result.get('leverage', 'unknown')}")

            elif exchange_name == 'okx':
                # OKX leverage setting
                try:
                    # OKX position mode is account-wide
                    perp_ex.set_position_mode(False)  # one-way mode
                except:
                    pass  # May already be set

                try:
                    # OKX set margin mode first
                    perp_ex.set_margin_mode('isolated', perp_symbol,
                        params={'lever': str(leverage)})
                except:
                    pass  # May already be set

                # OKX set leverage
                try:
                    result = perp_ex.set_leverage(leverage, perp_symbol,
                        params={
                            'mgnMode': 'isolated',
                            'lever': str(leverage)  # OKX requires lever param
                        })
                    print(f"   ✅ OKX leverage set to {leverage}x")
                except Exception as e:
                    print(f"   ⚠️ OKX leverage setting: {e}")
            return True

        except Exception as e:
            print(f"⚠️ {exchange_name.upper()} leverage setting failed: {e}")
            # Try to continue anyway - leverage might already be set correctly
            return True  # Return True to continue trading

    def get_exchange(self, exchange_name: str) -> Optional[Dict[str, ccxt.Exchange]]:
        """Get exchange instances by name"""
        return self.exchanges.get(exchange_name)

    def get_symbols(self, exchange_name: str) -> Optional[Dict[str, str]]:
        """Get symbols for a specific exchange"""
        return self.symbols.get(exchange_name)