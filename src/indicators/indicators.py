"""
Technical Indicators
────────────────────
Calculates all trading indicators on OHLCV DataFrames using pandas-ta.
Each function takes a DataFrame and returns it with new indicator columns added.
"""

import pandas as pd
import pandas_ta as ta

from config import settings


def add_rsi(df: pd.DataFrame, period: int = None) -> pd.DataFrame:
    """Add RSI (Relative Strength Index) column."""
    period = period or settings.RSI_PERIOD
    df["rsi"] = ta.rsi(df["close"], length=period)
    return df


def add_ema(df: pd.DataFrame, fast: int = None, slow: int = None) -> pd.DataFrame:
    """Add fast and slow EMA columns."""
    fast = fast or settings.EMA_FAST
    slow = slow or settings.EMA_SLOW
    df["ema_fast"] = ta.ema(df["close"], length=fast)
    df["ema_slow"] = ta.ema(df["close"], length=slow)
    return df


def add_macd(
    df: pd.DataFrame,
    fast: int = None,
    slow: int = None,
    signal: int = None,
) -> pd.DataFrame:
    """Add MACD, MACD Signal, and MACD Histogram columns."""
    fast = fast or settings.MACD_FAST
    slow = slow or settings.MACD_SLOW
    signal = signal or settings.MACD_SIGNAL
    macd = ta.macd(df["close"], fast=fast, slow=slow, signal=signal)
    if macd is None or macd.empty:
        df["macd"] = float("nan")
        df["macd_histogram"] = float("nan")
        df["macd_signal"] = float("nan")
        return df
    df["macd"] = macd.iloc[:, 0]  # MACD line
    df["macd_histogram"] = macd.iloc[:, 1]  # Histogram
    df["macd_signal"] = macd.iloc[:, 2]  # Signal line
    return df


def add_bollinger_bands(
    df: pd.DataFrame, period: int = None, std: float = None
) -> pd.DataFrame:
    """Add Bollinger Bands (upper, middle, lower) columns."""
    period = period or settings.BOLLINGER_PERIOD
    std = std or settings.BOLLINGER_STD
    bbands = ta.bbands(df["close"], length=period, std=std)
    if bbands is None or bbands.empty:
        df["bb_lower"] = float("nan")
        df["bb_middle"] = float("nan")
        df["bb_upper"] = float("nan")
        df["bb_bandwidth"] = float("nan")
        return df
    df["bb_lower"] = bbands.iloc[:, 0]  # Lower band
    df["bb_middle"] = bbands.iloc[:, 1]  # Middle band (SMA)
    df["bb_upper"] = bbands.iloc[:, 2]  # Upper band
    df["bb_bandwidth"] = bbands.iloc[:, 3] if bbands.shape[1] > 3 else None
    return df


def add_atr(df: pd.DataFrame, period: int = None) -> pd.DataFrame:
    """Add ATR (Average True Range) for volatility-based stop-losses."""
    period = period or settings.ATR_PERIOD
    df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=period)
    return df


def add_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add VWAP (Volume Weighted Average Price), anchored daily.

    Resets at the start of every trading day so the live session uses the
    same definition as the backtest (`_daily_vwap` in backtest/run_backtest.py).
    Using pandas_ta's `ta.vwap` directly anchors off-index when the frame
    contains multiple sessions, which silently drifts from the backtest.
    """
    if df.empty or "volume" not in df.columns or "date" not in df.columns:
        return df

    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
    tp_vol = typical_price * df["volume"]

    # Group by calendar date so VWAP resets at the daily boundary.
    dates = df["date"].dt.date
    cum_tp_vol = tp_vol.groupby(dates).cumsum()
    cum_vol = df["volume"].groupby(dates).cumsum().replace(0, float("nan"))
    df["vwap"] = cum_tp_vol / cum_vol
    return df


def drop_incomplete_last_bar(
    df: pd.DataFrame, interval_seconds: int, now_ts=None
) -> pd.DataFrame:
    """
    Drop a trailing partial candle so indicators compute on closed bars only.
    Mirrors backtest behaviour where every bar is fully formed before decisions.

    Args:
        df: OHLCV frame with a `date` column (tz-aware IST recommended).
        interval_seconds: duration of one candle (e.g. 300 for 5min).
        now_ts: optional override of current time (mostly for tests).
    """
    if df.empty or "date" not in df.columns or interval_seconds <= 0:
        return df
    if now_ts is None:
        now_ts = settings.now_ist()

    last_bar_open = df["date"].iloc[-1]
    # If `last_bar_open` isn't tz-aware but now_ts is, normalise for compare.
    try:
        if last_bar_open.tzinfo is None and now_ts.tzinfo is not None:
            last_bar_open = last_bar_open.tz_localize(now_ts.tzinfo)
        elif last_bar_open.tzinfo is not None and now_ts.tzinfo is None:
            now_ts = now_ts.replace(tzinfo=last_bar_open.tzinfo)
    except Exception:
        return df

    bar_close = last_bar_open + pd.Timedelta(seconds=interval_seconds)
    if now_ts < bar_close:
        return df.iloc[:-1].copy()
    return df


def add_supertrend(
    df: pd.DataFrame, period: int = None, multiplier: float = None
) -> pd.DataFrame:
    """Add Supertrend indicator columns."""
    period = period or settings.SUPERTREND_PERIOD
    multiplier = multiplier or settings.SUPERTREND_MULTIPLIER
    st = ta.supertrend(df["high"], df["low"], df["close"],
                       length=period, multiplier=multiplier)
    if st is None or st.empty:
        df["supertrend"] = float("nan")
        df["supertrend_direction"] = float("nan")
        return df
    # pandas-ta returns: SUPERT_{period}_{mult}, SUPERTd_{period}_{mult},
    # SUPERTl_{period}_{mult}, SUPERTs_{period}_{mult}
    cols = st.columns.tolist()
    supert_col = [c for c in cols if c.startswith("SUPERT_")][0]
    supertd_col = [c for c in cols if c.startswith("SUPERTd_")][0]
    df["supertrend"] = st[supert_col]
    df["supertrend_direction"] = st[supertd_col]  # 1 = bullish, -1 = bearish
    return df


def add_adx(df: pd.DataFrame, period: int = None) -> pd.DataFrame:
    """Add ADX (Average Directional Index) with +DI and -DI for trend strength."""
    period = period or settings.ATR_PERIOD
    adx_data = ta.adx(df["high"], df["low"], df["close"], length=period)
    if adx_data is not None and not adx_data.empty:
        cols = adx_data.columns.tolist()
        adx_col = [c for c in cols if c.startswith("ADX_")]
        dmp_col = [c for c in cols if c.startswith("DMP_")]
        dmn_col = [c for c in cols if c.startswith("DMN_")]
        if adx_col:
            df["adx"] = adx_data[adx_col[0]]
        if dmp_col:
            df["plus_di"] = adx_data[dmp_col[0]]
        if dmn_col:
            df["minus_di"] = adx_data[dmn_col[0]]
    return df


def add_vwap_bands(df: pd.DataFrame) -> pd.DataFrame:
    """Add VWAP standard deviation bands (1 and 2 sigma)."""
    if "vwap" not in df.columns or "close" not in df.columns:
        return df

    # Rolling deviation from VWAP
    deviation = df["close"] - df["vwap"]
    rolling_std = deviation.rolling(window=20, min_periods=5).std()

    df["vwap_upper_1"] = df["vwap"] + rolling_std
    df["vwap_lower_1"] = df["vwap"] - rolling_std
    df["vwap_upper_2"] = df["vwap"] + (2 * rolling_std)
    df["vwap_lower_2"] = df["vwap"] - (2 * rolling_std)
    return df


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all indicators to the DataFrame in one call."""
    df = add_rsi(df)
    df = add_ema(df)
    df = add_macd(df)
    df = add_bollinger_bands(df)
    df = add_atr(df)
    df = add_adx(df)
    if "volume" in df.columns and df["volume"].sum() > 0:
        df = add_vwap(df)
        df = add_vwap_bands(df)
    df = add_supertrend(df)
    return df


def ema_crossover(df: pd.DataFrame, lookback: int = 1) -> str | None:
    """
    Check for EMA crossover on the latest candles.
    With lookback > 1, scans the last N candle-pairs for the most recent
    crossover (useful for catch-up after mid-session restart).
    Returns: "BULLISH", "BEARISH", or None
    """
    if len(df) < 2 or "ema_fast" not in df.columns:
        return None

    for i in range(1, min(lookback + 1, len(df))):
        prev_fast = df["ema_fast"].iloc[-(i + 1)]
        prev_slow = df["ema_slow"].iloc[-(i + 1)]
        curr_fast = df["ema_fast"].iloc[-i]
        curr_slow = df["ema_slow"].iloc[-i]

        if pd.isna(prev_fast) or pd.isna(curr_fast):
            continue

        if prev_fast <= prev_slow and curr_fast > curr_slow:
            return "BULLISH"
        elif prev_fast >= prev_slow and curr_fast < curr_slow:
            return "BEARISH"

    return None


def macd_crossover(df: pd.DataFrame) -> str | None:
    """
    Check for MACD crossover on the latest candles.
    Returns: "BULLISH", "BEARISH", or None
    """
    if len(df) < 2 or "macd" not in df.columns:
        return None

    prev_macd = df["macd"].iloc[-2]
    prev_signal = df["macd_signal"].iloc[-2]
    curr_macd = df["macd"].iloc[-1]
    curr_signal = df["macd_signal"].iloc[-1]

    if pd.isna(prev_macd) or pd.isna(curr_macd):
        return None

    if prev_macd <= prev_signal and curr_macd > curr_signal:
        return "BULLISH"
    elif prev_macd >= prev_signal and curr_macd < curr_signal:
        return "BEARISH"
    return None
