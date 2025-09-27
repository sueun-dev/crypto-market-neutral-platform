"""
Utility functions module
"""
import math
from typing import Dict, Any
from datetime import datetime

def round_to_precision(amount: float, market_info: Dict[str, Any] = None) -> float:
    """Round amount to exchange's required precision"""
    if amount <= 0:
        return 0.0

    # Handle None market_info
    if market_info is None:
        return round(amount, 8)  # Default to 8 decimals

    # Get precision from market info
    precision_info = market_info.get('precision', {})
    amount_precision = precision_info.get('amount')

    if isinstance(amount_precision, int):
        precision = amount_precision
    elif isinstance(amount_precision, float) and amount_precision > 0:
        precision = max(0, int(round(-math.log10(amount_precision))))
    else:
        precision = 8  # Default precision

    # Round to precision
    rounded = float(f"{amount:.{precision}f}")

    # Check minimum amount
    limits = market_info.get('limits', {})
    amount_limits = limits.get('amount', {})
    min_amount = amount_limits.get('min')

    if min_amount and rounded < float(min_amount):
        rounded = float(f"{float(min_amount):.{precision}f}")

    return rounded

def calculate_common_quantity(spot_market: Dict, perp_market: Dict,
                             base_amount_usd: float, reference_price: float) -> float:
    """Calculate quantity that works for both spot and perpetual markets"""
    raw_qty = base_amount_usd / reference_price

    # Round for both markets
    spot_qty = round_to_precision(raw_qty, spot_market)
    perp_qty = round_to_precision(raw_qty, perp_market)

    # Use the smaller quantity
    final_qty = min(spot_qty, perp_qty)

    # Round again to ensure compatibility
    final_qty = round_to_precision(final_qty, spot_market)
    final_qty = round_to_precision(final_qty, perp_market)

    return final_qty

def format_price(price: float, decimals: int = 2) -> str:
    """Format price for display"""
    if price >= 1000:
        return f"${price:,.{decimals}f}"
    elif price >= 1:
        return f"${price:.{decimals}f}"
    else:
        # For small prices, use more decimals
        significant_digits = 4
        return f"${price:.{significant_digits}g}"

def format_percentage(value: float, decimals: int = 3) -> str:
    """Format percentage for display"""
    return f"{value * 100:.{decimals}f}%"

def print_price_table(prices: Dict[str, Dict[str, float]]) -> None:
    """Print formatted price table"""
    print(f"\n{'Exchange':<10} {'Spot Bid':<12} {'Spot Ask':<12} {'Perp Bid':<12} {'Perp Ask':<12}")
    print("-" * 60)

    for exchange, data in prices.items():
        print(f"{exchange.upper():<10} "
              f"{format_price(data['spot_bid']):<12} "
              f"{format_price(data['spot_ask']):<12} "
              f"{format_price(data['perp_bid']):<12} "
              f"{format_price(data['perp_ask']):<12}")

def print_opportunity(spot_ex: str, perp_ex: str, spot_price: float,
                     perp_price: float, spread: float, threshold: float) -> None:
    """Print hedge opportunity details"""
    print(f"\n{'='*40} BEST OPPORTUNITY {'='*40}")
    print(f"📍 Spot Buy:  {spot_ex.upper()} @ {format_price(spot_price)}")
    print(f"📍 Perp Short: {perp_ex.upper()} @ {format_price(perp_price)}")
    print(f"📊 Spread: {format_price(perp_price - spot_price)} ({format_percentage(spread)})")

    if spread >= threshold:
        print(f"✅ READY TO ENTER (Threshold: {format_percentage(threshold)})")
    else:
        print(f"⏳ WAITING (Current: {format_percentage(spread)} < Threshold: {format_percentage(threshold)})")

def log_trade(trade_type: str, exchange: str, coin: str, amount: float,
              price: float, timestamp: datetime = None) -> Dict:
    """Create trade log entry"""
    if timestamp is None:
        timestamp = datetime.now()

    return {
        'timestamp': timestamp.isoformat(),
        'type': trade_type,
        'exchange': exchange,
        'coin': coin,
        'amount': amount,
        'price': price,
        'value': amount * price
    }

def validate_api_keys(config: Dict[str, Dict]) -> Dict[str, bool]:
    """Validate which exchanges have API keys configured"""
    status = {}

    for exchange, creds in config.items():
        if exchange == 'okx':
            # OKX requires password too
            status[exchange] = bool(
                creds.get('apiKey') and
                creds.get('secret') and
                creds.get('password')
            )
        else:
            status[exchange] = bool(
                creds.get('apiKey') and
                creds.get('secret')
            )

    return status