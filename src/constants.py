"""
Constants for exchange limits and requirements
"""

# Minimum SELL order value in KRW (판매만 하므로 최소 판매금액만 필요)
KOREAN_MIN_SELL_VALUE_KRW = 5000  # 최소 판매금액 5,000원 (빗썸, 업비트 동일)

# Price tick sizes for Korean exchanges
KOREAN_PRICE_TICK_SIZES = {
    'bithumb': {
        1000000000: 1000,    # >= 1B KRW: tick 1000
        100000000: 500,      # >= 100M KRW: tick 500
        10000000: 100,       # >= 10M KRW: tick 100
        1000000: 50,         # >= 1M KRW: tick 50
        500000: 10,          # >= 500K KRW: tick 10
        100000: 5,           # >= 100K KRW: tick 5
        10000: 1,            # >= 10K KRW: tick 1
        1000: 0.1,           # >= 1K KRW: tick 0.1
        100: 0.01,           # >= 100 KRW: tick 0.01
        0: 0.001            # < 100 KRW: tick 0.001
    },
    'upbit': {
        2000000000: 1000,    # >= 2B KRW: tick 1000
        1000000000: 500,     # >= 1B KRW: tick 500
        500000000: 100,      # >= 500M KRW: tick 100
        100000000: 50,       # >= 100M KRW: tick 50
        10000000: 10,        # >= 10M KRW: tick 10
        1000000: 5,          # >= 1M KRW: tick 5
        500000: 1,           # >= 500K KRW: tick 1
        100000: 0.5,         # >= 100K KRW: tick 0.5
        10000: 0.1,          # >= 10K KRW: tick 0.1
        1000: 0.01,          # >= 1K KRW: tick 0.01
        100: 0.001,          # >= 100 KRW: tick 0.001
        10: 0.0001,          # >= 10 KRW: tick 0.0001
        0: 0.00001          # < 10 KRW: tick 0.00001
    }
}

# Maximum retries for operations
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 2

# Market order slippage protection
MAX_MARKET_SLIPPAGE = 0.02  # 2% maximum slippage

# Order monitoring intervals
ORDER_CHECK_INTERVAL = 10  # seconds
POSITION_SYNC_INTERVAL = 30  # seconds

# Exit strategy parameters
EXIT_PRICE_LEVELS = [
    ('target_3_percent', 0.3),   # 30% at 3% profit
    ('target_5_percent', 0.5),   # 50% at 5% profit
    ('target_10_percent', 0.2),  # 20% at 10% profit
]

# Balance safety thresholds
BALANCE_SAFETY_THRESHOLD = 0.95  # Use 95% of available balance
MIN_BALANCE_WARNING = 0.001  # Minimum balance to show warning

# State file paths
EXIT_STATE_FILE = "exit_state.json"
POSITION_STATE_FILE = "positions.json"