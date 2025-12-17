"""Runtime configuration for the multi-exchange hedge bot.

All constants are loaded from the environment where appropriate and typed for
clarity. Values are expressed in native units (e.g. spreads as decimals).
"""

from __future__ import annotations

import os
from typing import Any, Dict

from dotenv import load_dotenv

load_dotenv()

# Trading parameters.
ENTRY_AMOUNT: float = 100.0
MAX_ENTRIES: int = 40
PRICE_DIFF_THRESHOLD: float = 0.0015
SLEEP_SEC: int = 3
FUTURES_LEVERAGE: int = 1

# Exchange API configuration.
EXCHANGES_CONFIG: Dict[str, Dict[str, Any]] = {
    "gateio": {
        "apiKey": os.getenv("GATEIO_API_KEY", ""),
        "secret": os.getenv("GATEIO_API_SECRET", ""),
        "spot_symbol_template": "{coin}/USDT",
        "perp_symbol_template": "{coin}/USDT:USDT",
        "spot_options": {
            "defaultType": "spot",
            "createMarketBuyOrderRequiresPrice": False,
        },
        "perp_options": {
            "defaultType": "swap",
            "settle": "usdt",
        },
    },
    "bybit": {
        "apiKey": os.getenv("BYBIT_API_KEY", ""),
        "secret": os.getenv("BYBIT_API_SECRET", ""),
        "spot_symbol_template": "{coin}/USDT",
        "perp_symbol_template": "{coin}/USDT:USDT",
        "spot_options": {
            "defaultType": "spot",
            "recvWindow": 10000,
        },
        "perp_options": {
            "defaultType": "linear",
        },
    },
    "okx": {
        "apiKey": os.getenv("OKX_API_KEY", ""),
        "secret": os.getenv("OKX_API_SECRET", ""),
        "password": os.getenv("OKX_API_PASSWORD", ""),
        "spot_symbol_template": "{coin}/USDT",
        "perp_symbol_template": "{coin}/USDT:USDT",
        "spot_options": {
            "defaultType": "spot",
        },
        "perp_options": {
            "defaultType": "swap",
        },
    },
}

# Exchange trading fees.
EXCHANGE_FEES: Dict[str, Dict[str, Dict[str, float]]] = {
    "gateio": {
        "spot": {"maker": 0.002, "taker": 0.002},
        "futures": {"maker": 0.00015, "taker": 0.0005},
    },
    "bybit": {
        "spot": {"maker": 0.001, "taker": 0.001},
        "futures": {"maker": 0.0001, "taker": 0.00055},
    },
    "okx": {
        "spot": {"maker": 0.0008, "taker": 0.001},
        "futures": {"maker": 0.0002, "taker": 0.0005},
    },
    "bithumb": {
        "spot": {"maker": 0.0004, "taker": 0.0004},
    },
}
