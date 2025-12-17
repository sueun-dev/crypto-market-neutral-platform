"""Shared constants for hedge and exit flows."""

# Minimum sell order value on Korean exchanges (KRW)
KOREAN_MIN_SELL_VALUE_KRW = 5000

# Retry behaviour for network/order operations
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 2

# Market order slippage protection (50 bps)
MAX_MARKET_SLIPPAGE = 0.005

# Korean exchange price tick sizes (threshold -> tick)
KOREAN_PRICE_TICK_SIZES = {
    "bithumb": [
        (2_000_000, 1_000),
        (1_000_000, 500),
        (500_000, 100),
        (100_000, 50),
        (10_000, 10),
        (1_000, 1),
        (0, 0.1),
    ],
    "upbit": [
        (2_000_000, 1_000),
        (1_000_000, 500),
        (200_000, 100),
        (100_000, 50),
        (10_000, 10),
        (1_000, 1),
        (100, 0.1),
        (10, 0.01),
        (0, 0.001),
    ],
}

# Exit strategy allocation across profit targets
EXIT_PRICE_LEVELS = [
    ("target_3_percent", 0.3),
    ("target_5_percent", 0.5),
    ("target_10_percent", 0.2),
]
