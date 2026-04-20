"""
Tests for the Confluence Scoring Engine.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import pytest

from config import settings
from src.strategy.base import Signal
from src.strategy.confluence import ConfluenceScore, calculate_confluence


def _make_confluence_df(
    n=25,
    base_close=2000.0,
    rsi=45.0,
    volume=1_000_000,
    vwap_offset=-5.0,
):
    """Build a DataFrame with columns the confluence engine consumes."""
    np.random.seed(99)
    closes = [base_close + i * 0.5 for i in range(n)]
    highs = [c + 3 for c in closes]
    lows = [c - 3 for c in closes]
    volumes = [volume] * n
    rsis = [rsi] * n
    # Make RSI trend: rsi going up for buy, to test momentum scoring
    for i in range(n):
        rsis[i] = rsi + (i - n // 2) * 0.3
    vwaps = [c + vwap_offset for c in closes]

    df = pd.DataFrame({
        "close": closes,
        "high": highs,
        "low": lows,
        "volume": volumes,
        "rsi": rsis,
        "vwap": vwaps,
    })
    return df


class TestConfluenceScoring:

    def test_confluence_scoring_buy(self):
        """BUY signal should produce a score with all component keys."""
        df = _make_confluence_df(vwap_offset=-5)  # close > vwap
        result = calculate_confluence(Signal.BUY, df)

        assert isinstance(result, ConfluenceScore)
        assert result.total > 0
        expected_keys = ["trend", "momentum", "location", "participation"]
        for k in expected_keys:
            assert k in result.components, f"Missing component: {k}"

        # Each axis 0-25, total 0-100
        assert 0 <= result.total <= 100
        for v in result.components.values():
            assert 0 <= v <= 25

    def test_confluence_scoring_sell(self):
        """SELL signal produces a score with proper component keys."""
        df = _make_confluence_df(vwap_offset=5)  # close < vwap
        result = calculate_confluence(Signal.SELL, df)

        assert isinstance(result, ConfluenceScore)
        assert result.total > 0
        assert "location" in result.components

    def test_volume_scoring(self):
        """High volume relative to average -> higher participation score."""
        rng = np.random.default_rng(7)

        def _with_noisy_vol(last_vol: int):
            df = _make_confluence_df(volume=500_000)
            noise = rng.integers(-50_000, 50_000, size=len(df))
            df["volume"] = (df["volume"].values + noise).astype(int)
            df.loc[df.index[-1], "volume"] = last_vol
            return df

        # Low: last bar in-line with baseline ~500k
        score_low = calculate_confluence(Signal.BUY, _with_noisy_vol(500_000))
        # High: last bar 3x baseline -> high z-score
        score_high = calculate_confluence(Signal.BUY, _with_noisy_vol(3_000_000))

        assert score_high.components["participation"] > score_low.components["participation"], (
            f"High vol ({score_high.components['participation']}) should score higher "
            f"than low vol ({score_low.components['participation']})"
        )

    def test_vwap_alignment_buy(self):
        """Price above VWAP gives better VWAP score for BUY signals."""
        df_above = _make_confluence_df(vwap_offset=-10)  # close > vwap
        df_below = _make_confluence_df(vwap_offset=10)   # close < vwap

        score_above = calculate_confluence(Signal.BUY, df_above)
        score_below = calculate_confluence(Signal.BUY, df_below)

        assert score_above.components["location"] > score_below.components["location"]

    def test_no_htf_gives_neutral_trend(self):
        """Without HTF data or regime, trend axis should be neutral (12.5)."""
        df = _make_confluence_df()
        # Drop adx so there is literally no trend info
        if "adx" in df.columns:
            df = df.drop(columns=["adx"])
        result = calculate_confluence(Signal.BUY, df, df_htf=None, regime=None)
        assert result.components["trend"] == 12.5
