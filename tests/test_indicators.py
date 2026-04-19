"""
Tests for the technical indicators module.
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
from src.indicators.indicators import (
    add_adx,
    add_all_indicators,
    ema_crossover,
)


# ---------------------------------------------------------------------------
# add_all_indicators
# ---------------------------------------------------------------------------

class TestAddAllIndicators:

    def test_add_all_indicators(self, sample_ohlcv):
        """All expected indicator columns should be present after add_all_indicators."""
        df = add_all_indicators(sample_ohlcv.copy())

        expected_cols = [
            "rsi",
            "ema_fast",
            "ema_slow",
            "macd",
            "macd_signal",
            "macd_histogram",
            "bb_lower",
            "bb_middle",
            "bb_upper",
            "atr",
            "adx",
            "supertrend",
            "supertrend_direction",
        ]
        for col in expected_cols:
            assert col in df.columns, f"Missing indicator column: {col}"

        # VWAP should be present because volume > 0
        assert "vwap" in df.columns, "VWAP should be added when volume is present"

    def test_add_adx(self, sample_ohlcv):
        """ADX column is present after add_adx."""
        df = add_adx(sample_ohlcv.copy())
        assert "adx" in df.columns
        # ADX should have at least some non-NaN values
        assert df["adx"].dropna().shape[0] > 0


# ---------------------------------------------------------------------------
# EMA Crossover Detection
# ---------------------------------------------------------------------------

class TestEMACrossover:

    def test_ema_crossover_bullish(self):
        """Detect bullish crossover (fast crosses above slow)."""
        df = pd.DataFrame({
            "ema_fast": [48.0, 49.0, 50.5],
            "ema_slow": [50.0, 50.0, 50.0],
        })
        # Row -2: fast(49) <= slow(50); Row -1: fast(50.5) > slow(50) -> BULLISH
        assert ema_crossover(df) == "BULLISH"

    def test_ema_crossover_bearish(self):
        """Detect bearish crossover (fast crosses below slow)."""
        df = pd.DataFrame({
            "ema_fast": [52.0, 51.0, 49.5],
            "ema_slow": [50.0, 50.0, 50.0],
        })
        # Row -2: fast(51) >= slow(50); Row -1: fast(49.5) < slow(50) -> BEARISH
        assert ema_crossover(df) == "BEARISH"

    def test_ema_crossover_none(self):
        """No crossover -> None."""
        df = pd.DataFrame({
            "ema_fast": [52.0, 53.0, 54.0],
            "ema_slow": [50.0, 50.0, 50.0],
        })
        assert ema_crossover(df) is None

    def test_ema_crossover_not_enough_data(self):
        """Single row -> None."""
        df = pd.DataFrame({"ema_fast": [50.0], "ema_slow": [50.0]})
        assert ema_crossover(df) is None
