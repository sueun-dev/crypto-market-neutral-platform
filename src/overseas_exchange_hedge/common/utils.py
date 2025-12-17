"""Utility helpers for formatting, validation, and precision handling."""

from __future__ import annotations

import math
from typing import Any, Dict, Optional

DEFAULT_PRECISION = 8


def round_to_precision(amount: float, market_info: Optional[Dict[str, Any]] = None) -> float:
    """Rounds an amount to the exchange's required precision.

    Args:
        amount: Base asset quantity to round.
        market_info: Optional market metadata returned by ccxt.

    Returns:
        Rounded amount that respects exchange precision and minimum size limits.
    """
    if amount <= 0:
        return 0.0

    if market_info is None:
        return round(amount, DEFAULT_PRECISION)

    precision_info = market_info.get("precision", {})
    amount_precision = precision_info.get("amount")

    if isinstance(amount_precision, int):
        precision = amount_precision
    elif isinstance(amount_precision, float) and amount_precision > 0:
        precision = max(0, int(round(-math.log10(amount_precision))))
    else:
        precision = DEFAULT_PRECISION

    rounded = float(f"{amount:.{precision}f}")

    limits = market_info.get("limits", {})
    amount_limits = limits.get("amount", {})
    min_amount = amount_limits.get("min")

    if min_amount and rounded < float(min_amount):
        rounded = float(f"{float(min_amount):.{precision}f}")

    return rounded


def format_percentage(value: float, decimals: int = 3) -> str:
    """Formats a float as a percentage string.

    Args:
        value: Decimal value (e.g., 0.0123 for 1.23%).
        decimals: Number of decimal places to display.

    Returns:
        Percentage string formatted for display.
    """
    return f"{value * 100:.{decimals}f}%"


def validate_api_keys(config: Dict[str, Dict]) -> Dict[str, bool]:
    """Validates which exchanges have usable API keys configured.

    Args:
        config: Exchange configuration mapping.

    Returns:
        Mapping of exchange name to boolean indicating credential presence.
    """
    status = {}

    for exchange, creds in config.items():
        if exchange == "okx":
            status[exchange] = bool(creds.get("apiKey") and creds.get("secret") and creds.get("password"))
        else:
            status[exchange] = bool(creds.get("apiKey") and creds.get("secret"))

    return status
