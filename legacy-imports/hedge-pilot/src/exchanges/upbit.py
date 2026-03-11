import jwt
import uuid
import hashlib
import requests
import logging
from urllib.parse import urlencode
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class UpbitExchange:
    """Upbit Native API 거래소 구현"""
    
    def __init__(self, api_key: str, api_secret: str):
        self.exchange_id = 'upbit'
        self.api_key = api_key
        self.api_secret = api_secret

        self.api_url = "https://api.upbit.com"
        
        self.session = requests.Session()
    
    def _create_jwt_token(self, query: Optional[Dict] = None) -> str:
        """Create JWT token for authentication"""
        payload = {
            'access_key': self.api_key,
            'nonce': str(uuid.uuid4()),
        }
        
        if query:
            # Create query hash for POST requests
            query_string = urlencode(query).encode()
            m = hashlib.sha512()
            m.update(query_string)
            query_hash = m.hexdigest()
            
            payload['query_hash'] = query_hash
            payload['query_hash_alg'] = 'SHA512'
        
        jwt_token = jwt.encode(payload, self.api_secret)
        return jwt_token
    
    def _api_call(self, method: str, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make API call"""
        try:
            url = f"{self.api_url}{endpoint}"
            
            if method == 'GET':
                jwt_token = self._create_jwt_token()
                headers = {'Authorization': f'Bearer {jwt_token}'}
                response = self.session.get(url, headers=headers, params=params)
            else:  # POST
                jwt_token = self._create_jwt_token(params)
                headers = {
                    'Authorization': f'Bearer {jwt_token}',
                    'Content-Type': 'application/json'
                }
                response = self.session.post(url, headers=headers, json=params)
            
            if response.status_code == 200 or response.status_code == 201:
                return response.json()
            else:
                logger.error(f"API error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"API call failed: {e}")
            return None
    
    def get_ticker(self, symbol: str) -> Optional[Dict]:
        """Get ticker information with bid/ask from orderbook"""
        try:
            # Convert symbol format: XRP/KRW -> KRW-XRP
            base, quote = symbol.split('/')
            market = f"{quote}-{base}"
            
            # Get orderbook for bid/ask prices
            orderbook_url = f"{self.api_url}/v1/orderbook"
            orderbook_response = self.session.get(orderbook_url, params={'markets': market})
            
            bid_price = None
            ask_price = None
            
            if orderbook_response.status_code == 200:
                orderbook_data = orderbook_response.json()
                if orderbook_data and len(orderbook_data) > 0:
                    orderbook = orderbook_data[0]
                    if 'orderbook_units' in orderbook and len(orderbook['orderbook_units']) > 0:
                        # Get best bid and ask
                        bid_price = float(orderbook['orderbook_units'][0]['bid_price'])
                        ask_price = float(orderbook['orderbook_units'][0]['ask_price'])
            
            # Get ticker for last price and other info
            ticker_url = f"{self.api_url}/v1/ticker"
            ticker_response = self.session.get(ticker_url, params={'markets': market})
            
            if ticker_response.status_code == 200:
                ticker_data = ticker_response.json()
                if ticker_data and len(ticker_data) > 0:
                    ticker = ticker_data[0]
                    return {
                        'symbol': symbol,
                        'last': float(ticker['trade_price']),
                        'bid': bid_price if bid_price else float(ticker['trade_price']),
                        'ask': ask_price if ask_price else float(ticker['trade_price']),
                        'high': float(ticker['high_price']),
                        'low': float(ticker['low_price']),
                        'volume': float(ticker['trade_volume'])
                    }
            return None
        except Exception as e:
            logger.error(f"Failed to get ticker for {symbol}: {e}")
            return None
    
    def get_balance(self, currency: str) -> Optional[Dict]:
        """Get balance for a specific currency"""
        try:
            data = self._api_call('GET', '/v1/accounts')
            
            if data:
                for account in data:
                    if account['currency'] == currency:
                        balance = float(account['balance'])
                        locked = float(account['locked'])
                        
                        return {
                            'free': balance - locked,
                            'used': locked,
                            'total': balance
                        }
            
            return {'free': 0, 'used': 0, 'total': 0}
            
        except Exception as e:
            logger.error(f"Failed to get balance for {currency}: {e}")
            return None
    
    def create_market_order(self, symbol: str, side: str, amount: float, params: Optional[Dict] = None) -> Optional[Dict]:
        """Create a market order
        
        For buy orders: amount is in KRW (how much KRW to spend)
        For sell orders: amount is in crypto (how much crypto to sell)
        """
        try:
            # Convert symbol format: XRP/KRW -> KRW-XRP
            base, quote = symbol.split('/')
            market = f"{quote}-{base}"
            
            if side == 'buy':
                # For buy orders, amount is already in KRW
                order_params = {
                    'market': market,
                    'side': 'bid',
                    'price': str(int(amount)),  # KRW amount as string (integer)
                    'ord_type': 'price'  # Market buy by price
                }
                
                logger.info(f"Buy order: {amount} KRW for {base}")
                
            else:
                # For sell orders, amount is the quantity in crypto
                order_params = {
                    'market': market,
                    'side': 'ask',
                    'volume': str(amount),  # Crypto amount as string
                    'ord_type': 'market'  # Market sell
                }
                
                logger.info(f"Sell order: {amount} {base}")
            
            data = self._api_call('POST', '/v1/orders', order_params)
            
            if data:
                logger.info(f"Market order placed: {symbol} {side} {amount}")
                return {
                    'id': data.get('uuid'),
                    'symbol': symbol,
                    'side': side,
                    'amount': amount,
                    'status': data.get('state'),
                    'filled': float(data.get('executed_volume', 0))
                }
            return None
            
        except Exception as e:
            logger.error(f"Failed to create market order: {e}")
            return None
    
    def get_markets(self) -> Dict:
        """Get all markets - Not needed for spot trading"""
        # Upbit은 현물 거래소이므로 계약 크기 정보 불필요
        return {}
    
    def get_usdt_krw_price(self) -> Optional[float]:
        """Get USDT/KRW price (ask price for buying)"""
        ticker = self.get_ticker('USDT/KRW')
        return ticker['ask'] if ticker else None
    
    @property
    def exchange(self):
        """Compatibility property"""
        return self