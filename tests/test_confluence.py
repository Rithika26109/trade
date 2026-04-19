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
        expected_keys = [
            "trend_alignment",
            "volume",
            "vwap_position",
            "rsi_momentum",
            "support_resistance",
        ]
        for k in expected_keys:
            assert k in result.components, f"Missing component: {k}"

        # Each component 0-20, total 0-100
        assert 0 <= result.total <= 100
        for v in result.components.values():
            assert 0 <= v <= 20

    def test_confluence_scoring_sell(self):
        """SELL signal produces a score with proper component keys."""
        df = _make_confluence_df(vwap_offset=5)  # close < vwap
        result = calculate_confluence(Signal.SELL, df)

        assert isinstance(result, ConfluenceScore)
        assert result.total > 0
        assert "vwap_position" in result.components

    def test_volume_scoring(self):
        """High volume relative to average -> higher volume score."""
        # Low volume baseline
        df_low_vol = _make_confluence_df(volume=500_000)
        score_low = calculate_confluence(Signal.BUY, df_low_vol)

        # High volume: 2x what would be the average
        df_high_vol = _make_confluence_df(volume=500_000)
        # Set the last candle's volume to 3x average
        df_high_vol.loc[df_high_vol.index[-1], "volume"] = 3_000_000
        score_high = calculate_confluence(Signal.BUY, df_high_vol)

        assert score_high.components["volume"] > score_low.components["volume"], (
            f"High vol ({score_high.components['volume']}) should score higher "
            f"than low vol ({score_low.components['volume']})"
        )

    def test_vwap_alignment_buy(self):
        """Price above VWAP gives better VWAP score for BUY signals."""
        df_above = _make_confluence_df(vwap_offset=-10)  # close > vwap
        df_below = _make_confluence_df(vwap_offset=10)   # close < vwap

        score_above = calculate_confluence(Signal.BUY, df_above)
        score_below = calculate_confluence(Signal.BUY, df_below)

        assert score_above.components["vwap_position"] > score_below.components["vwap_position"]

    def test_no_htf_gives_neutral_trend(self):
        """Without HTF data, trend_alignment should be neutral (10)."""
        df = _make_confluence_df()
        result = calculate_confluence(Signal.BUY, df, df_htf=None, regime=None)
        assert result.components["trend_alignment"] == 10
