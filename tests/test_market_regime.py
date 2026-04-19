"""
Tests for the Market Regime detection module.
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
from src.indicators.market_regime import MarketRegime, detect_regime


def _make_regime_df(
    adx: float,
    plus_di: float = 30.0,
    minus_di: float = 20.0,
    bb_bandwidth: float = 0.05,
    bb_bandwidth_avg: float = 0.05,
    n: int = 25,
):
    """Build a DataFrame with the columns detect_regime() needs."""
    rows = []
    for i in range(n):
        rows.append({
            "adx": adx,
            "plus_di": plus_di,
            "minus_di": minus_di,
            # Build bb_bandwidth so that the average and the latest are controllable:
            # last row gets the explicit value, earlier rows get the avg value
            "bb_bandwidth": bb_bandwidth if i == n - 1 else bb_bandwidth_avg,
        })
    df = pd.DataFrame(rows)
    return df


class TestMarketRegime:

    def test_strong_trend_detection(self):
        """ADX > 40 with plus_di > minus_di -> STRONG_TREND_UP."""
        df = _make_regime_df(adx=45, plus_di=35, minus_di=15)
        regime = detect_regime(df)
        assert regime == MarketRegime.STRONG_TREND_UP

    def test_strong_trend_down_detection(self):
        """ADX > 40 with minus_di > plus_di -> STRONG_TREND_DOWN."""
        df = _make_regime_df(adx=45, plus_di=15, minus_di=35)
        regime = detect_regime(df)
        assert regime == MarketRegime.STRONG_TREND_DOWN

    def test_ranging_detection(self):
        """ADX < 20 with normal BB bandwidth -> RANGING."""
        df = _make_regime_df(adx=15, bb_bandwidth=0.05, bb_bandwidth_avg=0.05)
        regime = detect_regime(df)
        assert regime == MarketRegime.RANGING

    def test_volatile_detection(self):
        """ADX < 20 with BB bandwidth > 2x average -> VOLATILE."""
        # Average bb_bandwidth ~ 0.04, latest = 0.10 (>2x avg)
        df = _make_regime_df(
            adx=15,
            bb_bandwidth=0.10,
            bb_bandwidth_avg=0.04,
            n=25,
        )
        regime = detect_regime(df)
        assert regime == MarketRegime.VOLATILE

    def test_trend_up_mid_adx(self):
        """ADX 25-40 with bullish DI -> TREND_UP."""
        df = _make_regime_df(adx=32, plus_di=28, minus_di=18)
        regime = detect_regime(df)
        assert regime == MarketRegime.TREND_UP

    def test_empty_df_defaults_to_ranging(self):
        """Empty DataFrame -> RANGING (safe default)."""
        df = pd.DataFrame()
        regime = detect_regime(df)
        assert regime == MarketRegime.RANGING

    def test_regime_is_trending_property(self):
        """MarketRegime.is_trending works for trend enums."""
        assert MarketRegime.STRONG_TREND_UP.is_trending is True
        assert MarketRegime.TREND_DOWN.is_trending is True
        assert MarketRegime.RANGING.is_trending is False
        assert MarketRegime.VOLATILE.is_trending is False
