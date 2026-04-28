"""
Tests for the three trading strategies: ORB, RSI+EMA, VWAP+Supertrend.
"""

import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import pytest

from config import settings
from src.indicators.market_regime import MarketRegime
from src.strategy.base import Signal
from src.strategy.orb import ORBStrategy
from src.strategy.rsi_ema import RSIEMAStrategy
from src.strategy.vwap_supertrend import VWAPSupertrendStrategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_df(rows: list[dict], tz=None) -> pd.DataFrame:
    """Build a DataFrame from a list of row dicts.  Adds a date column."""
    df = pd.DataFrame(rows)
    if "date" not in df.columns:
        n = len(df)
        df["date"] = pd.date_range(
            start="2026-04-17 09:15:00",
            periods=n,
            freq="5min",
            tz=tz or settings.IST,
        )
    return df


# ═══════════════════════════════════════════════════════════════════════════
# ORB Strategy Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestORBStrategy:

    def _make_orb_df(self, closes, highs=None, lows=None, volumes=None):
        """Build a minimal DataFrame for ORB with the last 2+ candles."""
        n = len(closes)
        if highs is None:
            highs = [c + 2 for c in closes]
        if lows is None:
            lows = [c - 2 for c in closes]
        if volumes is None:
            volumes = [1_500_000] * n  # Well above average

        rows = []
        for i in range(n):
            rows.append({
                "open": closes[i],
                "high": highs[i],
                "low": lows[i],
                "close": closes[i],
                "volume": volumes[i],
                "atr": 5.0,
            })
        return _make_df(rows)

    def test_orb_buy_signal(self):
        """Price breaks above ORB high with volume -> BUY."""
        strat = ORBStrategy()
        strat.set_opening_range("RELIANCE", high=2500.0, low=2480.0, open_price=2490.0)

        # prev_close <= orb_high, current_close > orb_high
        # 6+ rows so the volume-average window works
        closes = [2490, 2492, 2494, 2496, 2498, 2495, 2498, 2505]
        volumes = [800_000, 900_000, 850_000, 950_000, 900_000, 880_000, 920_000, 1_800_000]
        df = self._make_orb_df(closes, volumes=volumes)

        result = strat.analyze(df, "RELIANCE")
        assert result.signal == Signal.BUY

    def test_orb_sell_signal(self):
        """Price breaks below ORB low with volume -> SELL."""
        strat = ORBStrategy()
        strat.set_opening_range("TCS", high=3600.0, low=3560.0, open_price=3580.0)

        closes = [3580, 3575, 3572, 3568, 3565, 3562, 3563, 3555]
        volumes = [800_000, 900_000, 850_000, 950_000, 900_000, 880_000, 920_000, 1_800_000]
        df = self._make_orb_df(closes, volumes=volumes)

        result = strat.analyze(df, "TCS")
        assert result.signal == Signal.SELL

    def test_orb_hold_within_range(self):
        """Price stays within the opening range -> HOLD."""
        strat = ORBStrategy()
        strat.set_opening_range("INFY", high=1500.0, low=1480.0, open_price=1490.0)

        closes = [1490, 1492, 1494, 1493, 1491, 1490, 1492, 1494]
        df = self._make_orb_df(closes)

        result = strat.analyze(df, "INFY")
        assert result.signal == Signal.HOLD

    def test_orb_range_too_tight(self):
        """ORB range < 0.3% of open -> HOLD (skips breakout)."""
        strat = ORBStrategy()
        # range = 1.0, open = 2500 => 0.04% — way below 0.3%
        strat.set_opening_range("RELIANCE", high=2500.5, low=2499.5, open_price=2500.0)

        closes = [2500, 2501]
        df = self._make_orb_df(closes)
        result = strat.analyze(df, "RELIANCE")
        assert result.signal == Signal.HOLD
        assert "too tight" in result.reason.lower()


# ═══════════════════════════════════════════════════════════════════════════
# RSI + EMA Strategy Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestRSIEMAStrategy:

    def _base_rows(self, n=10, base=2000):
        """Generate n generic rows with the required indicator columns."""
        rows = []
        for i in range(n):
            rows.append({
                "close": base + i,
                "open": base + i - 0.5,
                "high": base + i + 2,
                "low": base + i - 2,
                "volume": 1_000_000,
                "rsi": 45.0,
                "ema_fast": base + i,
                "ema_slow": base + i,
                "atr": 10.0,
                "vwap": base + i - 1,
            })
        return rows

    def test_rsi_ema_buy_signal(self):
        """Bullish EMA crossover + RSI in buy range -> BUY."""
        strat = RSIEMAStrategy()
        rows = self._base_rows(10)
        # Set up crossover: prev_fast <= prev_slow, curr_fast > curr_slow
        rows[-2]["ema_fast"] = 2007.0
        rows[-2]["ema_slow"] = 2008.0  # fast <= slow
        rows[-1]["ema_fast"] = 2010.0
        rows[-1]["ema_slow"] = 2008.0  # fast > slow
        rows[-1]["rsi"] = 42.0  # Within RSI_BUY_MIN..RSI_BUY_MAX (30-55)
        rows[-1]["close"] = 2012.0
        rows[-1]["vwap"] = 2005.0  # price above VWAP
        rows[-1]["adx"] = 30.0  # Above 20 so ADX filter passes

        df = _make_df(rows)
        result = strat.analyze(df, "RELIANCE")
        assert result.signal == Signal.BUY

    def test_rsi_ema_sell_signal(self):
        """Bearish EMA crossover + RSI in sell range -> SELL."""
        strat = RSIEMAStrategy()
        rows = self._base_rows(10)
        rows[-2]["ema_fast"] = 2010.0
        rows[-2]["ema_slow"] = 2008.0  # fast >= slow
        rows[-1]["ema_fast"] = 2006.0
        rows[-1]["ema_slow"] = 2008.0  # fast < slow
        rows[-1]["rsi"] = 62.0  # Within RSI_SELL_MIN..RSI_SELL_MAX (45-70)
        rows[-1]["close"] = 2004.0
        rows[-1]["vwap"] = 2010.0  # price below VWAP
        rows[-1]["adx"] = 30.0

        df = _make_df(rows)
        result = strat.analyze(df, "TCS")
        assert result.signal == Signal.SELL

    def test_rsi_ema_adx_filter(self):
        """ADX < 10 -> HOLD regardless of crossover."""
        strat = RSIEMAStrategy()
        rows = self._base_rows(10)
        # Set up a bullish crossover
        rows[-2]["ema_fast"] = 2007.0
        rows[-2]["ema_slow"] = 2008.0
        rows[-1]["ema_fast"] = 2010.0
        rows[-1]["ema_slow"] = 2008.0
        rows[-1]["rsi"] = 42.0
        rows[-1]["close"] = 2012.0
        rows[-1]["vwap"] = 2005.0
        rows[-1]["adx"] = 8.0  # Below new ADX floor of 10

        df = _make_df(rows)
        result = strat.analyze(df, "INFY")
        assert result.signal == Signal.HOLD
        assert "adx" in result.reason.lower()


# ═══════════════════════════════════════════════════════════════════════════
# VWAP + Supertrend Strategy Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestVWAPSupertrendStrategy:

    def _make_vwap_st_df(
        self,
        closes,
        vwaps,
        st_values,
        st_dirs,
        volumes=None,
    ):
        """Build a DataFrame with all columns VWAP+Supertrend needs."""
        n = len(closes)
        if volumes is None:
            volumes = [1_500_000] * n
        rows = []
        for i in range(n):
            rows.append({
                "close": closes[i],
                "open": closes[i] - 1,
                "high": closes[i] + 3,
                "low": closes[i] - 3,
                "volume": volumes[i],
                "vwap": vwaps[i],
                "supertrend": st_values[i],
                "supertrend_direction": st_dirs[i],
                "atr": 8.0,
            })
        return _make_df(rows)

    def test_vwap_supertrend_buy(self):
        """Bullish ST flip + price above VWAP -> BUY."""
        strat = VWAPSupertrendStrategy()
        # confirm_candles=2 so recent_dirs = last (2+2)=4 rows.
        # recent_dirs[0] must be -1, rest must be 1 for bullish flip.
        # Build enough rows so the last-4 slice has [-1, 1, 1, 1].
        n = 8
        closes = [2500 + i for i in range(n)]
        vwaps = [c - 10 for c in closes]  # price above VWAP
        st_values = [c - 15 for c in closes]  # ST below price (bullish)

        # Place the flip at index n-4 so the last 4 rows are [-1, 1, 1, 1]
        st_dirs = [-1] * (n - 3) + [1, 1, 1]
        #  last 4:  dirs[-4:] = [-1, 1, 1, 1]

        # High volumes on the bullish candles to meet weighted threshold (>=2.5)
        # avg_vol ~ mean of last 8 rows. If base=800k and bullish=2.4M,
        # avg ≈ (5*800k + 3*2.4M)/8 = 1.4M, weight per candle ≈ 2.4M/1.4M ≈ 1.71
        # weighted sum of 3 bullish candles ≈ 3*1.71 = 5.1 > 2.5 ✓
        volumes = [800_000] * (n - 3) + [2_400_000, 2_400_000, 2_400_000]

        df = self._make_vwap_st_df(closes, vwaps, st_values, st_dirs, volumes)
        result = strat.analyze(df, "RELIANCE")
        assert result.signal == Signal.BUY

    def test_vwap_supertrend_ranging_no_longer_blocked(self):
        """RANGING regime no longer hard-blocks VWAP+ST (regime tracker handles weighting)."""
        strat = VWAPSupertrendStrategy()
        n = 8
        closes = [2500 + i for i in range(n)]
        vwaps = [c - 10 for c in closes]
        st_values = [c - 15 for c in closes]
        st_dirs = [-1] + [1] * (n - 1)
        volumes = [800_000] + [1_800_000] * (n - 1)

        df = self._make_vwap_st_df(closes, vwaps, st_values, st_dirs, volumes)

        original = settings.ENABLE_REGIME_DETECTION
        try:
            settings.ENABLE_REGIME_DETECTION = True
            result = strat.analyze(df, "INFY", regime=MarketRegime.RANGING)
            # Should no longer return HOLD just because of RANGING
            assert result.signal != Signal.HOLD or "ranging" not in result.reason.lower()
        finally:
            settings.ENABLE_REGIME_DETECTION = original
