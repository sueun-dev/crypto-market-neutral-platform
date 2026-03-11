"""
Gate.io Native API 거래소 클래스
"""
import gate_api
from gate_api.exceptions import GateApiException
import logging
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

class GateIOExchange:
    """Gate.io Native API 거래소 구현"""
    
    def __init__(self, api_credentials):
        self.exchange_id = 'gateio'
        
        # Validate API credentials
        if not api_credentials:
            raise ValueError("API credentials not provided for Gate.io exchange")
        
        self.api_key = api_credentials.get('apiKey')
        self.api_secret = api_credentials.get('secret')
        
        if not self.api_key or not self.api_secret:
            raise ValueError("API key and secret are required for Gate.io exchange")
        
        # Configure Gate.io API
        configuration = gate_api.Configuration(
            host="https://api.gateio.ws/api/v4",
            key=self.api_key,
            secret=self.api_secret
        )
        
        self.api_client = gate_api.ApiClient(configuration)
        # Only futures API needed - Gate.io is used for shorting only
        self.futures_api = gate_api.FuturesApi(self.api_client)
        
        # Load markets info
        self.futures_markets = {}
        self._load_futures_markets()
    
    def _load_futures_markets(self):
        """Load futures market information"""
        try:
            contracts = self.futures_api.list_futures_contracts('usdt')
            for contract in contracts:
                # Extract underlying from contract name (e.g., BTC_USDT -> BTC)
                underlying = contract.name.replace('_USDT', '')
                symbol = f"{underlying}/USDT:USDT"
                self.futures_markets[symbol] = {
                    'name': contract.name,
                    'contract_size': float(contract.quanto_multiplier) if contract.quanto_multiplier else 1,
                    'underlying': underlying
                }
            logger.info(f"Loaded {len(self.futures_markets)} futures markets")
        except Exception as e:
            logger.error(f"Failed to load futures markets: {e}")
    
    def get_balance(self, currency: str) -> Optional[Dict]:
        """Get balance for a specific currency"""
        try:
            # Check futures balance
            futures_accounts = self.futures_api.list_futures_accounts('usdt')
            
            if currency == 'USDT':
                # Gate API returns a single account object for futures
                if hasattr(futures_accounts, 'available'):
                    # Single account object
                    available = float(futures_accounts.available) if futures_accounts.available else 0
                    total = float(futures_accounts.total) if futures_accounts.total else 0
                    # Calculate used from position_margin and order_margin
                    position_margin = float(futures_accounts.position_margin) if hasattr(futures_accounts, 'position_margin') and futures_accounts.position_margin else 0
                    order_margin = float(futures_accounts.order_margin) if hasattr(futures_accounts, 'order_margin') and futures_accounts.order_margin else 0
                    used = position_margin + order_margin
                    
                    return {
                        'free': available,
                        'used': used,
                        'total': total
                    }
            # Only USDT is used for futures trading
            return {'free': 0, 'used': 0, 'total': 0}
            
        except Exception as e:
            logger.error(f"Failed to get balance for {currency}: {e}")
            return None
    
    def get_ticker(self, symbol: str) -> Optional[Dict]:
        """Get ticker information"""
        try:
            if ':USDT' in symbol:
                # Futures ticker
                contract = symbol.replace('/USDT:USDT', '_USDT')
                tickers = self.futures_api.list_futures_tickers('usdt', contract=contract)
                if tickers:
                    ticker = tickers[0]
                    return {
                        'symbol': symbol,
                        'last': float(ticker.last),
                        'bid': float(ticker.highest_bid) if ticker.highest_bid else None,
                        'ask': float(ticker.lowest_ask) if ticker.lowest_ask else None,
                        'high': float(ticker.high_24h),
                        'low': float(ticker.low_24h),
                        'volume': float(ticker.volume_24h)
                    }
            # Only futures tickers are used
            return None
        except Exception as e:
            logger.error(f"Failed to get ticker for {symbol}: {e}")
            return None
    
    def create_market_order(self, symbol: str, side: str, amount: float, params: Optional[Dict] = None) -> Optional[Dict]:
        """Create a market order"""
        try:
            if ':USDT' in symbol:
                # Futures order
                contract = symbol.replace('/USDT:USDT', '_USDT')
                
                # Get contract size
                contract_info = self.futures_markets.get(symbol, {})
                contract_size = contract_info.get('contract_size', 1)
                
                # Convert amount to contracts
                # OrderExecutor already converts to contracts via _calculate_futures_quantity
                # So amount here is already in contracts
                if params and params.get('from_order_executor'):
                    # Amount is already in contracts from OrderExecutor
                    # Round to nearest integer for minimum contract requirement
                    contracts = round(amount)
                else:
                    # Direct API call, convert from coin amount to contracts
                    contracts = round(amount / contract_size)
                
                if contracts < 1:
                    logger.error(f"Contract amount too small: {amount} {symbol} = {contracts} contracts")
                    return None
                
                # Create futures order
                # Gate.io API requires size as string
                size_str = str(contracts if side == 'buy' else -contracts)  # Negative for sell/short
                
                order = gate_api.FuturesOrder(
                    contract=contract,
                    size=size_str,  # String type as per API spec
                    price='0',  # Market order
                    tif='ioc',  # Immediate or cancel
                    reduce_only=params.get('reduce_only', False) if params else False
                )
                
                response = self.futures_api.create_futures_order('usdt', order)
                
                logger.info(f"Futures order placed: {symbol} {side} {contracts} contracts")
                
                return {
                    'id': response.id,
                    'symbol': symbol,
                    'side': side,
                    'amount': contracts,
                    'status': response.status,
                    'filled': response.size - response.left if response.left else response.size
                }
            else:
                # Spot order - not implemented yet
                logger.error("Spot orders not implemented in native API yet")
                return None
                
        except GateApiException as ex:
            logger.error(f"Gate API exception: {ex.label}, {ex.message}")
            return None
        except Exception as e:
            logger.error(f"Failed to create market order: {e}")
            return None
    
    def get_markets(self) -> Dict:
        """Get all markets"""
        return self.futures_markets
    
    def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage for a symbol"""
        try:
            contract = symbol.replace('/USDT:USDT', '_USDT')
            # Gate.io uses cross margin by default, leverage is set per position
            # This is handled automatically when opening positions
            return True
        except Exception as e:
            logger.error(f"Failed to set leverage: {e}")
            return False
    
    def get_positions(self) -> List[Dict]:
        """Get all futures positions"""
        try:
            positions = self.futures_api.list_positions('usdt')
            result = []
            
            for pos in positions:
                if pos.size != 0:  # Only include open positions
                    symbol = f"{pos.contract.replace('_USDT', '')}/USDT:USDT"
                    side = 'short' if pos.size < 0 else 'long'
                    contracts = abs(pos.size)
                    notional = abs(float(pos.value))
                    
                    result.append({
                        'symbol': symbol,
                        'side': side,
                        'contracts': contracts,
                        'notional': notional,
                        'mode': pos.mode,
                        'mark_price': float(pos.mark_price),
                        'entry_price': float(pos.entry_price) if pos.entry_price else 0
                    })
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []
    
    @property
    def exchange(self):
        """Compatibility property for accessing exchange methods"""
        return self
    
    def fetch_positions(self, symbols=None):
        """Compatibility method for ccxt-style position fetching"""
        positions = self.get_positions()
        if symbols:
            # Filter by symbols if provided
            filtered = []
            for pos in positions:
                if pos['symbol'] in symbols:
                    filtered.append(pos)
            return filtered
        return positions
    
    def load_markets(self):
        """Compatibility method for ccxt-style market loading"""
        return self.futures_markets