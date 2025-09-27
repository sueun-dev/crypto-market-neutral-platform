"""
Configuration module for multi-exchange hedge bot
"""
import os
from dotenv import load_dotenv
from typing import Dict, Any

# Load environment variables
load_dotenv()

# Trading Parameters
ENTRY_AMOUNT = 20.0              # Base USDT amount per entry
MAX_ENTRIES = 40                 # Maximum number of hedge entries
PRICE_DIFF_THRESHOLD = 0.0021    # Minimum spread for entry (0.21%)
SLEEP_SEC = 10                   # Check interval in seconds
FUTURES_LEVERAGE = 1             # 항상 1x 레버리지 (델타 중립 필수)
SLIPPAGE = 0.004                # Slippage tolerance (0.4%)

# Exchange API Configuration
EXCHANGES_CONFIG: Dict[str, Dict[str, Any]] = {
    'gateio': {
        'apiKey': os.getenv('GATEIO_API_KEY', ''),
        'secret': os.getenv('GATEIO_API_SECRET', ''),
        'spot_options': {
            'defaultType': 'spot',
            'createMarketBuyOrderRequiresPrice': False,
        },
        'perp_options': {
            'defaultType': 'swap',
            'settle': 'usdt'
        }
    },
    'bybit': {
        'apiKey': os.getenv('BYBIT_API_KEY', ''),
        'secret': os.getenv('BYBIT_API_SECRET', ''),
        'spot_options': {
            'defaultType': 'spot',
            'recvWindow': 10000,
        },
        'perp_options': {
            'defaultType': 'linear',  # USDT perpetual
        }
    },
    'okx': {
        'apiKey': os.getenv('OKX_API_KEY', ''),
        'secret': os.getenv('OKX_API_SECRET', ''),
        'password': os.getenv('OKX_API_PASSWORD', ''),
        'spot_options': {
            'defaultType': 'spot',
        },
        'perp_options': {
            'defaultType': 'swap',  # USDT perpetual
        }
    }
}

# Exchange Trading Fees
EXCHANGE_FEES = {
    'gateio': {
        'spot': {'maker': 0.002, 'taker': 0.002},      # Spot fees
        'futures': {'maker': 0.00015, 'taker': 0.0005}  # Futures fees (much lower)
    },
    'bybit': {
        'spot': {'maker': 0.001, 'taker': 0.001},      # Spot fees
        'futures': {'maker': 0.0001, 'taker': 0.00055}  # USDT perpetual fees
    },
    'okx': {
        'spot': {'maker': 0.0008, 'taker': 0.001},     # Spot fees (VIP0)
        'futures': {'maker': 0.0002, 'taker': 0.0005}   # USDT perpetual fees (VIP0)
    },
    'bithumb': {
        'spot': {'maker': 0.0004, 'taker': 0.0004}     # Bithumb spot only
    }
}

# Symbol Format Templates
SYMBOL_FORMATS = {
    'gateio': {
        'spot': '{coin}/USDT',
        'perp': '{coin}/USDT:USDT'
    },
    'bybit': {
        'spot': '{coin}/USDT',
        'perp': '{coin}/USDT:USDT'
    },
    'okx': {
        'spot': '{coin}/USDT',
        'perp': '{coin}/USDT:USDT'
    }
}

