"""
Confluence Scoring Engine
─────────────────────────
Assigns a 0-100 confidence score to trade signals based on multiple
independent factors. Higher confluence = higher probability trade.

Professional traders only take high-confluence setups. This module
quantifies that intuition into a systematic score.
"""

from dataclasses import dataclass, field

import pandas as pd

from src.strategy.base import Signal


@dataclass
class ConfluenceScore:
    total: float = 0.0
    components: dict = field(default_factory=dict)


def calculate_confluence(
    signal: Signal,
    df: pd.DataFrame,
    df_htf: pd.DataFrame = None,
    regime=None,
) -> ConfluenceScore:
    """
    Calculate confluence score (0-100) for a trade signal.

    Components (each 0-20 points):
    1. Trend Alignment — HTF trend agrees with signal direction
    2. Volume Confirmation — Current volume vs average
    3. VWAP Position — Price relative to VWAP
    4. RSI Momentum — RSI in favorable zone + momentum direction
    5. Support/Resistance — Price near key levels
    """
    score = ConfluenceScore()

    # 1. Trend Alignment (0-20)
    trend_score = _score_trend_alignment(signal, df_htf, regime)
    score.components["trend_alignment"] = trend_score

    # 2. Volume Confirmation (0-20)
    vol_score = _score_volume(signal, df)
    score.components["volume"] = vol_score

    # 3. VWAP Position (0-20)
    vwap_score = _score_vwap(signal, df)
    score.components["vwap_position"] = vwap_score

    # 4. RSI Momentum (0-20)
    rsi_score = _score_rsi_momentum(signal, df)
    score.components["rsi_momentum"] = rsi_score

    # 5. Support/Resistance (0-20)
    sr_score = _score_support_resistance(signal, df)
    score.components["support_resistance"] = sr_score

    score.total = sum(score.components.values())
    return score


def _score_trend_alignment(signal: Signal, df_htf: pd.DataFrame, regime) -> float:
    """Score based on higher-timeframe trend agreeing with signal."""
    if df_htf is None or df_htf.empty:
        return 10  # Neutral — no HTF data available

    points = 0

    # Check HTF EMA alignment
    if "ema_fast" in df_htf.columns and "ema_slow" in df_htf.columns:
        htf_fast = df_htf["ema_fast"].iloc[-1]
        htf_slow = df_htf["ema_slow"].iloc[-1]
        if not pd.isna(htf_fast) and not pd.isna(htf_slow):
            htf_bullish = htf_fast > htf_slow
            if signal == Signal.BUY and htf_bullish:
                points += 10
            elif signal == Signal.SELL and not htf_bullish:
                points += 10

    # Check regime alignment
    if regime is not None:
        if signal == Signal.BUY and regime.is_bullish:
            points += 10
        elif signal == Signal.SELL and regime.is_bearish:
            points += 10
        elif regime.is_trending:
            points += 5  # At least trending, even if wrong direction

    return min(points, 20)


def _score_volume(signal: Signal, df: pd.DataFrame) -> float:
    """Score based on volume relative to average."""
    if "volume" not in df.columns or len(df) < 6:
        return 10  # Neutral

    current_vol = df["volume"].iloc[-1]
    avg_vol = df["volume"].iloc[-21:-1].mean() if len(df) >= 21 else df["volume"].iloc[:-1].mean()

    if pd.isna(current_vol) or pd.isna(avg_vol) or avg_vol <= 0:
        return 10

    vol_ratio = current_vol / avg_vol

    if vol_ratio >= 2.0:
        return 20
    elif vol_ratio >= 1.5:
        return 15
    elif vol_ratio >= 1.2:
        return 10
    elif vol_ratio >= 0.8:
        return 5
    else:
        return 0  # Below average volume — weak conviction


def _score_vwap(signal: Signal, df: pd.DataFrame) -> float:
    """Score based on price position relative to VWAP."""
    if "vwap" not in df.columns:
        return 10  # Neutral

    close = df["close"].iloc[-1]
    vwap = df["vwap"].iloc[-1]

    if pd.isna(close) or pd.isna(vwap) or vwap <= 0:
        return 10

    # Check if VWAP is trending in signal direction
    vwap_rising = False
    if len(df) >= 3:
        prev_vwap = df["vwap"].iloc[-3]
        if not pd.isna(prev_vwap):
            vwap_rising = vwap > prev_vwap

    if signal == Signal.BUY:
        if close > vwap and vwap_rising:
            return 20
        elif close > vwap:
            return 15
        elif abs(close - vwap) / vwap < 0.002:  # Within 0.2% of VWAP
            return 10
        else:
            return 3  # Below VWAP on a BUY — weak

    elif signal == Signal.SELL:
        if close < vwap and not vwap_rising:
            return 20
        elif close < vwap:
            return 15
        elif abs(close - vwap) / vwap < 0.002:
            return 10
        else:
            return 3

    return 10


def _score_rsi_momentum(signal: Signal, df: pd.DataFrame) -> float:
    """Score based on RSI position and momentum direction."""
    if "rsi" not in df.columns or len(df) < 3:
        return 10

    rsi = df["rsi"].iloc[-1]
    if pd.isna(rsi):
        return 10

    prev_rsi = df["rsi"].iloc[-3]
    rsi_accelerating = not pd.isna(prev_rsi) and (
        (signal == Signal.BUY and rsi > prev_rsi) or
        (signal == Signal.SELL and rsi < prev_rsi)
    )

    if signal == Signal.BUY:
        if 35 <= rsi <= 55 and rsi_accelerating:
            return 20  # Sweet spot: recovering from oversold + accelerating
        elif 30 <= rsi <= 60:
            return 15
        elif rsi < 30:
            return 10  # Oversold — could bounce or continue down
        elif rsi > 70:
            return 2   # Overbought BUY — risky
        else:
            return 8

    elif signal == Signal.SELL:
        if 45 <= rsi <= 65 and rsi_accelerating:
            return 20
        elif 40 <= rsi <= 70:
            return 15
        elif rsi > 70:
            return 10
        elif rsi < 30:
            return 2   # Oversold SELL — risky
        else:
            return 8

    return 10


def _score_support_resistance(signal: Signal, df: pd.DataFrame) -> float:
    """Score based on proximity to support/resistance levels derived from swing points."""
    if len(df) < 20:
        return 10

    close = df["close"].iloc[-1]
    highs = df["high"].iloc[-20:]
    lows = df["low"].iloc[-20:]

    # Simple swing high/low detection: local maxima/minima
    resistance_levels = []
    support_levels = []

    for i in range(2, len(highs) - 2):
        # Swing high: higher than 2 candles on each side
        if highs.iloc[i] > highs.iloc[i-1] and highs.iloc[i] > highs.iloc[i-2] and \
           highs.iloc[i] > highs.iloc[i+1] and highs.iloc[i] > highs.iloc[i+2]:
            resistance_levels.append(highs.iloc[i])

        # Swing low: lower than 2 candles on each side
        if lows.iloc[i] < lows.iloc[i-1] and lows.iloc[i] < lows.iloc[i-2] and \
           lows.iloc[i] < lows.iloc[i+1] and lows.iloc[i] < lows.iloc[i+2]:
            support_levels.append(lows.iloc[i])

    if not resistance_levels and not support_levels:
        return 10

    # Find nearest levels
    nearest_resistance = min(resistance_levels, key=lambda r: abs(r - close)) if resistance_levels else None
    nearest_support = min(support_levels, key=lambda s: abs(s - close)) if support_levels else None

    proximity_pct = 0.005  # Within 0.5% counts as "near"

    if signal == Signal.BUY:
        # Breaking above resistance is strong; buying at support is favorable
        if nearest_resistance and close > nearest_resistance:
            return 20  # Breaking resistance — strong BUY
        if nearest_support and abs(close - nearest_support) / close < proximity_pct:
            return 18  # At support — good entry
        if nearest_resistance and abs(close - nearest_resistance) / close < proximity_pct:
            return 5   # At resistance on a BUY — risky
        return 10

    elif signal == Signal.SELL:
        if nearest_support and close < nearest_support:
            return 20  # Breaking support — strong SELL
        if nearest_resistance and abs(close - nearest_resistance) / close < proximity_pct:
            return 18  # At resistance — good entry
        if nearest_support and abs(close - nearest_support) / close < proximity_pct:
            return 5   # At support on a SELL — risky
        return 10

    return 10
