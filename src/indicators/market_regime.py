"""
Market Regime Detection
───────────────────────
Detects whether the market is trending, ranging, or volatile using ADX
and Bollinger Band width. This is the single most impactful filter for
preventing strategy whipsaw in wrong conditions.

Usage:
    regime = detect_regime(df_15min)
    # STRONG_TREND_UP, TREND_UP, RANGING, TREND_DOWN, STRONG_TREND_DOWN, VOLATILE
"""

from enum import Enum

import pandas as pd

from config import settings


class MarketRegime(Enum):
    STRONG_TREND_UP = "STRONG_TREND_UP"
    TREND_UP = "TREND_UP"
    RANGING = "RANGING"
    TREND_DOWN = "TREND_DOWN"
    STRONG_TREND_DOWN = "STRONG_TREND_DOWN"
    VOLATILE = "VOLATILE"

    @property
    def is_trending(self) -> bool:
        return self in (
            MarketRegime.STRONG_TREND_UP,
            MarketRegime.TREND_UP,
            MarketRegime.STRONG_TREND_DOWN,
            MarketRegime.TREND_DOWN,
        )

    @property
    def is_bullish(self) -> bool:
        return self in (MarketRegime.STRONG_TREND_UP, MarketRegime.TREND_UP)

    @property
    def is_bearish(self) -> bool:
        return self in (MarketRegime.STRONG_TREND_DOWN, MarketRegime.TREND_DOWN)


def detect_regime(df: pd.DataFrame) -> MarketRegime:
    """
    Detect market regime from a DataFrame with ADX, +DI, -DI, and BB columns.

    Algorithm:
    - ADX > 40 → STRONG_TREND (direction from +DI vs -DI)
    - ADX 25-40 → TREND
    - ADX < 20 → RANGING (unless BB squeeze suggests VOLATILE)
    - ADX < 20 AND BB bandwidth expanding > 2x average → VOLATILE

    Args:
        df: DataFrame with 'adx', 'plus_di', 'minus_di', 'bb_bandwidth' columns.
            Should be higher-timeframe (15min) for best results.

    Returns:
        MarketRegime enum value
    """
    if df.empty or len(df) < 5:
        return MarketRegime.RANGING

    # Get latest values
    adx = df["adx"].iloc[-1] if "adx" in df.columns else None
    plus_di = df["plus_di"].iloc[-1] if "plus_di" in df.columns else None
    minus_di = df["minus_di"].iloc[-1] if "minus_di" in df.columns else None

    if adx is None or pd.isna(adx):
        return MarketRegime.RANGING

    # Determine direction from DI
    bullish_direction = True
    if plus_di is not None and minus_di is not None:
        if not pd.isna(plus_di) and not pd.isna(minus_di):
            bullish_direction = plus_di > minus_di

    # ADX thresholds
    adx_strong = getattr(settings, 'ADX_STRONG_TREND', 40)
    adx_trend = getattr(settings, 'ADX_TREND', 25)
    adx_ranging = getattr(settings, 'ADX_RANGING', 20)

    if adx > adx_strong:
        return MarketRegime.STRONG_TREND_UP if bullish_direction else MarketRegime.STRONG_TREND_DOWN

    if adx >= adx_trend:
        return MarketRegime.TREND_UP if bullish_direction else MarketRegime.TREND_DOWN

    if adx < adx_ranging:
        # Check for volatility squeeze breakout via Bollinger Band width
        if "bb_bandwidth" in df.columns:
            bb_bw = df["bb_bandwidth"].dropna()
            if len(bb_bw) >= 10:
                current_bw = bb_bw.iloc[-1]
                avg_bw = bb_bw.iloc[-20:].mean() if len(bb_bw) >= 20 else bb_bw.mean()
                if not pd.isna(current_bw) and not pd.isna(avg_bw) and avg_bw > 0:
                    if current_bw > 2.0 * avg_bw:
                        return MarketRegime.VOLATILE

        return MarketRegime.RANGING

    # ADX between ranging and trend thresholds — treat as weak ranging
    return MarketRegime.RANGING


def get_regime_multiplier(regime: MarketRegime) -> float:
    """
    Position size multiplier based on regime.
    Reduce size in ranging/volatile markets where signals are less reliable.
    """
    multipliers = {
        MarketRegime.STRONG_TREND_UP: 1.0,
        MarketRegime.STRONG_TREND_DOWN: 1.0,
        MarketRegime.TREND_UP: 1.0,
        MarketRegime.TREND_DOWN: 1.0,
        MarketRegime.RANGING: 0.6,
        MarketRegime.VOLATILE: 0.5,
    }
    return multipliers.get(regime, 1.0)
