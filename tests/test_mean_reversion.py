"""
Tests for the Mean-Reversion (Bollinger Band + RSI) strategy.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import pytest

from config import settings
from src.indicators.market_regime import MarketRegime
from src.strategy.base import Signal
from src.strategy.mean_reversion import MeanReversionStrategy


def _make_df(rows: list[dict]) -> pd.DataFrame:
    """Build a DataFrame from row dicts with a date column."""
    df = pd.DataFrame(rows)
    if "date" not in df.columns:
        n = len(df)
        df["date"] = pd.date_range(
            start="2026-04-17 09:15:00",
            periods=n,
            freq="5min",
            tz=settings.IST,
        )
    return df


def _base_rows(n=25, base=2000):
    """Generate rows with all indicators a mean-reversion strategy needs.

    Default state: price at BB middle, RSI=50, ADX=15 (ranging).
    """
    rows = []
    for i in range(n):
        close = base + i * 0.1
        rows.append({
            "close": close,
            "open": close - 0.5,
            "high": close + 3,
            "low": close - 3,
            "volume": 1_000_000,
            "bb_lower": close - 20,
            "bb_upper": close + 20,
            "bb_middle": close,
            "bb_bandwidth": 2.0,
            "rsi": 50.0,
            "atr": 10.0,
            "adx": 15.0,
            "vwap": close - 1,
        })
    return rows


class TestMeanReversionBuy:

    def test_buy_at_lower_bb_with_oversold_rsi(self):
        """Price at lower BB + RSI oversold + low ADX → BUY."""
        strat = MeanReversionStrategy()
        rows = _base_rows()
        # Last candle: price at lower BB, RSI oversold
        rows[-1]["close"] = 1980.0
        rows[-1]["bb_lower"] = 1980.0
        rows[-1]["bb_upper"] = 2020.0
        rows[-1]["bb_middle"] = 2000.0
        rows[-1]["rsi"] = 28.0
        rows[-1]["adx"] = 14.0

        df = _make_df(rows)
        result = strat.analyze(df, "RELIANCE")
        assert result.signal == Signal.BUY
        assert "Mean-reversion BUY" in result.reason

    def test_buy_below_lower_bb(self):
        """Price below lower BB (penetration) still triggers BUY."""
        strat = MeanReversionStrategy()
        rows = _base_rows()
        rows[-1]["close"] = 1975.0
        rows[-1]["bb_lower"] = 1980.0
        rows[-1]["bb_upper"] = 2020.0
        rows[-1]["bb_middle"] = 2000.0
        rows[-1]["rsi"] = 25.0
        rows[-1]["adx"] = 12.0

        df = _make_df(rows)
        result = strat.analyze(df, "TCS")
        assert result.signal == Signal.BUY


class TestMeanReversionSell:

    def test_sell_at_upper_bb_with_overbought_rsi(self):
        """Price at upper BB + RSI overbought + low ADX → SELL."""
        strat = MeanReversionStrategy()
        rows = _base_rows()
        rows[-1]["close"] = 2020.0
        rows[-1]["bb_lower"] = 1980.0
        rows[-1]["bb_upper"] = 2020.0
        rows[-1]["bb_middle"] = 2000.0
        rows[-1]["rsi"] = 72.0
        rows[-1]["adx"] = 14.0

        df = _make_df(rows)
        result = strat.analyze(df, "INFY")
        assert result.signal == Signal.SELL
        assert "Mean-reversion SELL" in result.reason

    def test_sell_above_upper_bb(self):
        """Price above upper BB (penetration) still triggers SELL."""
        strat = MeanReversionStrategy()
        rows = _base_rows()
        rows[-1]["close"] = 2025.0
        rows[-1]["bb_lower"] = 1980.0
        rows[-1]["bb_upper"] = 2020.0
        rows[-1]["bb_middle"] = 2000.0
        rows[-1]["rsi"] = 75.0
        rows[-1]["adx"] = 12.0

        df = _make_df(rows)
        result = strat.analyze(df, "SBIN")
        assert result.signal == Signal.SELL


class TestMeanReversionFilters:

    def test_adx_too_high_hold(self):
        """ADX above threshold → HOLD (trending market, not mean-reverting)."""
        strat = MeanReversionStrategy()
        rows = _base_rows()
        rows[-1]["close"] = 1980.0
        rows[-1]["bb_lower"] = 1980.0
        rows[-1]["rsi"] = 28.0
        rows[-1]["adx"] = 30.0  # Well above MEAN_REV_ADX_MAX (20)

        df = _make_df(rows)
        result = strat.analyze(df, "RELIANCE")
        assert result.signal == Signal.HOLD
        assert "ADX" in result.reason

    def test_bb_squeeze_hold(self):
        """BB bandwidth too narrow (squeeze) → HOLD."""
        strat = MeanReversionStrategy()
        rows = _base_rows()
        rows[-1]["close"] = 1980.0
        rows[-1]["bb_lower"] = 1980.0
        rows[-1]["rsi"] = 28.0
        rows[-1]["adx"] = 14.0
        rows[-1]["bb_bandwidth"] = 0.1  # Below MEAN_REV_MIN_BB_WIDTH_PCT (0.5)

        df = _make_df(rows)
        result = strat.analyze(df, "TCS")
        assert result.signal == Signal.HOLD
        assert "squeeze" in result.reason.lower()

    def test_breakout_volume_hold(self):
        """High volume z-score → HOLD (breakout, not mean-reversion)."""
        strat = MeanReversionStrategy()
        rows = _base_rows(n=25)
        # Set varied normal volume for first 24 rows, spike on last
        for i, r in enumerate(rows[:-1]):
            r["volume"] = 900_000 + (i % 5) * 50_000  # 900k-1.1M range
        rows[-1]["volume"] = 5_000_000  # Massive spike
        rows[-1]["close"] = 1980.0
        rows[-1]["bb_lower"] = 1980.0
        rows[-1]["rsi"] = 28.0
        rows[-1]["adx"] = 14.0

        df = _make_df(rows)
        result = strat.analyze(df, "INFY")
        assert result.signal == Signal.HOLD
        assert "volume" in result.reason.lower()

    def test_rsi_not_oversold_hold(self):
        """Price at lower BB but RSI not oversold → HOLD."""
        strat = MeanReversionStrategy()
        rows = _base_rows()
        rows[-1]["close"] = 1980.0
        rows[-1]["bb_lower"] = 1980.0
        rows[-1]["rsi"] = 45.0  # Not oversold
        rows[-1]["adx"] = 14.0

        df = _make_df(rows)
        result = strat.analyze(df, "RELIANCE")
        assert result.signal == Signal.HOLD

    def test_trending_regime_hold(self):
        """Trending regime with ENABLE_REGIME_DETECTION → HOLD."""
        strat = MeanReversionStrategy()
        rows = _base_rows()
        rows[-1]["close"] = 1980.0
        rows[-1]["bb_lower"] = 1980.0
        rows[-1]["rsi"] = 28.0
        rows[-1]["adx"] = 14.0  # ADX would pass

        df = _make_df(rows)

        original = settings.ENABLE_REGIME_DETECTION
        try:
            settings.ENABLE_REGIME_DETECTION = True
            result = strat.analyze(df, "RELIANCE", regime=MarketRegime.TREND_UP)
            assert result.signal == Signal.HOLD
            assert "trending" in result.reason.lower()
        finally:
            settings.ENABLE_REGIME_DETECTION = original


class TestMeanReversionRiskReward:

    def test_target_meets_min_rr(self):
        """Target price always meets MIN_RISK_REWARD_RATIO."""
        strat = MeanReversionStrategy()
        rows = _base_rows()
        rows[-1]["close"] = 1980.0
        rows[-1]["bb_lower"] = 1980.0
        rows[-1]["bb_upper"] = 2020.0
        rows[-1]["bb_middle"] = 2000.0
        rows[-1]["rsi"] = 28.0
        rows[-1]["adx"] = 14.0
        rows[-1]["atr"] = 10.0

        df = _make_df(rows)
        result = strat.analyze(df, "RELIANCE")
        assert result.signal == Signal.BUY
        assert result.risk_reward_ratio >= settings.MIN_RISK_REWARD_RATIO

    def test_target_uses_bb_middle_when_larger(self):
        """When BB middle is further than min R:R target, use BB middle."""
        strat = MeanReversionStrategy()
        rows = _base_rows()
        rows[-1]["close"] = 1980.0
        rows[-1]["bb_lower"] = 1980.0
        rows[-1]["bb_upper"] = 2060.0
        rows[-1]["bb_middle"] = 2020.0  # 40 points away — larger than min R:R
        rows[-1]["rsi"] = 28.0
        rows[-1]["adx"] = 14.0
        rows[-1]["atr"] = 10.0  # SL = 1980 - 20 = 1960, risk = 20, min_target = 2010

        df = _make_df(rows)
        result = strat.analyze(df, "RELIANCE")
        assert result.signal == Signal.BUY
        assert result.target == 2020.0  # BB middle > min R:R target
