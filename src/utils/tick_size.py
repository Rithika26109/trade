"""
Tick Size Utilities
───────────────────
NSE/BSE require order prices to be multiples of an instrument's tick size
(typically 0.05 for most equities, 1.00 for a few). Un-aligned prices are
rejected by the broker.

Usage:
    from src.utils.tick_size import round_to_tick, get_tick_size

    sl = round_to_tick(signal.stop_loss, tick_size=0.05)
"""

from __future__ import annotations

import math

DEFAULT_TICK_SIZE = 0.05


def round_to_tick(price: float, tick_size: float = DEFAULT_TICK_SIZE, mode: str = "nearest") -> float:
    """
    Round a price to the nearest valid tick.

    Args:
        price: The raw price.
        tick_size: Tick increment (e.g. 0.05).
        mode: "nearest" (default), "floor" (for stop-loss on long / target on short),
              "ceil" (for stop-loss on short / target on long). For most uses
              "nearest" is safe; directional modes avoid accidentally widening
              the stop (favourable to trader).

    Returns:
        Price rounded to the nearest valid tick, with float precision cleaned
        up so 123.05 stays 123.05 rather than 123.04999999.
    """
    if tick_size <= 0:
        return price
    ratio = price / tick_size
    if mode == "floor":
        snapped = math.floor(ratio) * tick_size
    elif mode == "ceil":
        snapped = math.ceil(ratio) * tick_size
    else:
        snapped = round(ratio) * tick_size
    # Clean up binary float drift — tick sizes are decimals
    decimals = max(0, -int(math.floor(math.log10(tick_size))) if tick_size < 1 else 0)
    return round(snapped, decimals + 2)


def get_tick_size(instruments_cache: dict | None, symbol: str, exchange: str = "NSE") -> float:
    """
    Look up an instrument's tick_size from the loaded Kite instruments cache.
    Falls back to DEFAULT_TICK_SIZE if not found.
    """
    if not instruments_cache:
        return DEFAULT_TICK_SIZE
    key = f"{exchange}:{symbol}"
    inst = instruments_cache.get(key)
    if not inst:
        return DEFAULT_TICK_SIZE
    tick = inst.get("tick_size")
    if not tick or tick <= 0:
        return DEFAULT_TICK_SIZE
    return float(tick)
