import hashlib
import hmac
import base64
import time
import urllib.parse
import requests
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class BithumbExchange:
    """Bithumb Native API 거래소 구현"""
    
    def __init__(self, api_key: str, api_secret: str):
        self.exchange_id = 'bithumb'
        
        # Validate API credentials
        if not api_key or not api_secret:
            raise ValueError("API credentials not provided for Bithumb exchange")
        
        self.api_key = api_key
        self.api_secret = api_secret
        
        self.public_api_url = "https://api.bithumb.com/public"
        self.private_api_url = "https://api.bithumb.com"

        self.session = requests.Session()
        self.session.headers.update({
            'Api-Key': self.api_key,
            'Api-Sign': '',
            'Api-Nonce': ''
        })
    
    def _create_signature(self, endpoint: str, params: Dict) -> Dict:
        """Create signature for private API calls"""
        nonce = str(int(time.time() * 1000))
        
        # Create the message to sign
        data = endpoint + chr(0) + urllib.parse.urlencode(params) + chr(0) + nonce
        
        # Create signature
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            data.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()
        
        # Encode signature
        api_sign = base64.b64encode(signature.encode('utf-8')).decode('utf-8')
        
        return {
            'Api-Key': self.api_key,
            'Api-Sign': api_sign,
            'Api-Nonce': nonce,
            'Content-Type': 'application/x-www-form-urlencoded'
        }
    
    def _public_api_call(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make public API call"""
        try:
            url = f"{self.public_api_url}/{endpoint}"
            if params:
                url += f"/{params.get('order_currency', 'ALL')}_{params.get('payment_currency', 'KRW')}"
            
            response = self.session.get(url)
            data = response.json()
            
            if data.get('status') == '0000':
                return data.get('data')
            else:
                logger.error(f"API error: {data.get('message')}")
                return None
        except Exception as e:
            logger.error(f"Public API call failed: {e}")
            return None
    
    def _private_api_call(self, endpoint: str, params: Dict) -> Optional[Dict]:
        """Make private API call"""
        try:
            url = f"{self.private_api_url}{endpoint}"
            headers = self._create_signature(endpoint, params)
            
            response = self.session.post(url, headers=headers, data=params)
            data = response.json()
            
            if data.get('status') == '0000':
                # Return successful response
                # For market orders, the response includes order_id directly
                if endpoint in ['/trade/market_buy', '/trade/market_sell']:
                    return {'order_id': data.get('order_id')}
                return data.get('data')
            else:
                # Debug print for specific errors
                error_msg = data.get('message', 'Unknown error')
                error_code = data.get('status', 'Unknown')
                logger.error(f"API error [{error_code}]: {error_msg}")
                return None  # Return None on error
        except Exception as e:
            logger.error(f"Private API call failed: {e}")
            return None
    
    def get_ticker(self, symbol: str) -> Optional[Dict]:
        """Get ticker information"""
        try:
            # Convert symbol format: XRP/KRW -> XRP_KRW
            base, quote = symbol.split('/')
            
            # Get orderbook to get bid/ask prices
            orderbook_data = self._public_api_call('orderbook', {
                'order_currency': base,
                'payment_currency': quote
            })
            
            # Get ticker for last price
            ticker_data = self._public_api_call('ticker', {
                'order_currency': base,
                'payment_currency': quote
            })
            
            if ticker_data:
                result = {
                    'symbol': symbol,
                    'last': float(ticker_data['closing_price']),
                    'bid': None,
                    'ask': None,
                    'high': float(ticker_data['max_price']),
                    'low': float(ticker_data['min_price']),
                    'volume': float(ticker_data['units_traded'])
                }
                
                # Add bid/ask from orderbook if available
                if orderbook_data:
                    if 'bids' in orderbook_data and len(orderbook_data['bids']) > 0:
                        result['bid'] = float(orderbook_data['bids'][0]['price'])
                    if 'asks' in orderbook_data and len(orderbook_data['asks']) > 0:
                        result['ask'] = float(orderbook_data['asks'][0]['price'])
                
                return result
            return None
        except Exception as e:
            logger.error(f"Failed to get ticker for {symbol}: {e}")
            return None
    
    def get_balance(self, currency: str) -> Optional[Dict]:
        """Get balance for a specific currency"""
        try:
            # Bithumb API는 currency를 'ALL'로 보내야 모든 잔고를 받을 수 있음
            # 특정 통화만 요청하면 오류 발생
            params = {
                'currency': 'ALL'
            }
            
            data = self._private_api_call('/info/balance', params)
            
            if data and isinstance(data, dict):
                # Bithumb returns balances with currency code in lowercase
                currency_lower = currency.lower()
                
                # For KRW, directly use the provided values
                if currency.upper() == 'KRW':
                    total = float(data.get('total_krw', 0))
                    in_use = float(data.get('in_use_krw', 0))
                    available = float(data.get('available_krw', 0))
                else:
                    # For other currencies, use currency-specific keys
                    total = float(data.get(f'total_{currency_lower}', 0))
                    in_use = float(data.get(f'in_use_{currency_lower}', 0))
                    available = float(data.get(f'available_{currency_lower}', 0))
                
                return {
                    'free': available,
                    'used': in_use,
                    'total': total
                }
            return {'free': 0, 'used': 0, 'total': 0}
        except Exception as e:
            logger.error(f"Failed to get balance for {currency}: {e}")
            return {'free': 0, 'used': 0, 'total': 0}
    
    def create_market_order(self, symbol: str, side: str, amount: float, params: Optional[Dict] = None) -> Optional[Dict]:
        """Create a market order
        
        For buy orders: amount is in KRW (how much KRW to spend)
        For sell orders: amount is in crypto (how much crypto to sell)
        """
        try:
            # Convert symbol format: XRP/KRW -> XRP
            base, quote = symbol.split('/')
            
            # Bithumb market order requires crypto units, not KRW amount
            # So for buy orders, we need to calculate crypto units from KRW amount
            
            if side == 'buy':
                # Get current price to calculate crypto units
                ticker = self.get_ticker(symbol)
                if not ticker:
                    logger.error(f"Cannot get ticker for {symbol}")
                    return None
                
                # Use ask price for buy orders (실제 매수 가격)
                price = ticker.get('ask')
                if not price:
                    logger.error(f"No ask price available for {symbol}")
                    return None
                
                # Calculate crypto units from KRW amount
                # Bithumb API 자동거래는 4자리까지만 지원
                crypto_units = round(amount / price, 4)
                
                endpoint = '/trade/market_buy'
                order_params = {
                    'order_currency': base,
                    'payment_currency': quote,
                    'units': str(crypto_units)  # Crypto units for market buy
                }
                
            else:
                # For sell, amount is already in crypto units
                endpoint = '/trade/market_sell'
                order_params = {
                    'order_currency': base,
                    'payment_currency': quote,
                    'units': str(round(amount, 4))  # API 자동거래는 4자리까지 지원
                }
            
            data = self._private_api_call(endpoint, order_params)
            
            if data:
                logger.info(f"Market order placed: {symbol} {side} {amount}")
                
                # Parse response based on Bithumb's actual format
                order_id = data.get('order_id', 'unknown')
                
                # Get executed amount and cost from response
                if side == 'buy':
                    # For buy orders, amount is KRW spent
                    filled = float(data.get('units', 0))  # Crypto received
                    cost = amount  # KRW spent
                else:
                    # For sell orders, amount is crypto sold
                    filled = amount  # Crypto sold
                    cost = float(data.get('total', 0))  # KRW received
                
                return {
                    'id': order_id,
                    'symbol': symbol,
                    'side': side,
                    'amount': amount,
                    'status': 'closed',
                    'filled': filled,
                    'cost': cost
                }
            else:
                return None
            
        except Exception as e:
            logger.error(f"Failed to create market order: {e}")
            return None
    
    def get_markets(self) -> Dict:
        """Get all markets"""
        # For simplicity, return empty dict as we focus on KRW markets
        return {}
    
    def get_usdt_krw_price(self) -> Optional[float]:
        """Get USDT/KRW price (ask price for buying)"""
        ticker = self.get_ticker('USDT/KRW')
        return ticker['ask'] if ticker else None
    
    @property
    def exchange(self):
        """Compatibility property"""
        return self