"""
Tests for the Simplified Pairs Trading strategy (v1).
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import pytest

from config import settings
from src.strategy.base import Signal
from src.strategy.pairs import PairsTradingStrategy


def _make_candles(n=60, base=2000.0, trend=0.0, tz=None):
    """Build an OHLCV DataFrame with `n` candles."""
    closes = [base + i * trend + np.random.normal(0, 1) for i in range(n)]
    dates = pd.date_range(
        start="2026-04-17 09:15:00",
        periods=n,
        freq="5min",
        tz=tz or settings.IST,
    )
    return pd.DataFrame({
        "date": dates,
        "open": [c - 0.5 for c in closes],
        "high": [c + 3 for c in closes],
        "low": [c - 3 for c in closes],
        "close": closes,
        "volume": [1_000_000] * n,
        "rsi": [50.0] * n,
        "atr": [10.0] * n,
    })


def _make_diverged_pair(n=60, base_a=2000.0, base_b=2000.0):
    """Build two DataFrames where A has diverged from B (A is cheaper)."""
    np.random.seed(42)
    dates = pd.date_range(
        start="2026-04-17 09:15:00",
        periods=n,
        freq="5min",
        tz=settings.IST,
    )
    # A and B start together, then A drops relative to B
    closes_a = [base_a + np.random.normal(0, 0.5) for _ in range(n)]
    closes_b = [base_b + np.random.normal(0, 0.5) for _ in range(n)]
    # Make A significantly cheaper in last candles (divergence)
    for i in range(n - 5, n):
        closes_a[i] = base_a - 30  # Drop A
        closes_b[i] = base_b + 30  # Lift B

    def _to_df(closes):
        return pd.DataFrame({
            "date": dates,
            "open": [c - 0.5 for c in closes],
            "high": [c + 3 for c in closes],
            "low": [c - 3 for c in closes],
            "close": closes,
            "volume": [1_000_000] * n,
            "rsi": [50.0] * n,
            "atr": [10.0] * n,
        })

    return _to_df(closes_a), _to_df(closes_b)


class TestPairsSignal:

    def test_buy_when_undervalued(self, monkeypatch):
        """Symbol undervalued vs partner (z < -entry) → BUY."""
        monkeypatch.setattr(settings, "ENABLE_PAIRS_TRADING", True)
        monkeypatch.setattr(settings, "PAIRS_SYMBOLS", [("STOCK_A", "STOCK_B")])
        monkeypatch.setattr(settings, "PAIRS_ENTRY_Z", 2.0)
        monkeypatch.setattr(settings, "PAIRS_LOOKBACK", 50)
        monkeypatch.setattr(settings, "PAIRS_MIN_HISTORY", 20)

        df_a, df_b = _make_diverged_pair()

        mock_md = MagicMock()
        mock_md.get_todays_candles.return_value = df_b

        strat = PairsTradingStrategy(market_data=mock_md)
        result = strat.analyze(df_a, "STOCK_A")

        assert result.signal == Signal.BUY
        assert "undervalued" in result.reason.lower()

    def test_sell_when_overvalued(self, monkeypatch):
        """Symbol overvalued vs partner (z > +entry) → SELL."""
        monkeypatch.setattr(settings, "ENABLE_PAIRS_TRADING", True)
        monkeypatch.setattr(settings, "PAIRS_SYMBOLS", [("STOCK_A", "STOCK_B")])
        monkeypatch.setattr(settings, "PAIRS_ENTRY_Z", 2.0)
        monkeypatch.setattr(settings, "PAIRS_LOOKBACK", 50)
        monkeypatch.setattr(settings, "PAIRS_MIN_HISTORY", 20)

        df_a, df_b = _make_diverged_pair()

        # Give the strategy STOCK_B's perspective: B is the one that's up
        mock_md = MagicMock()
        mock_md.get_todays_candles.return_value = df_a

        strat = PairsTradingStrategy(market_data=mock_md)
        result = strat.analyze(df_b, "STOCK_B")

        assert result.signal == Signal.SELL
        assert "overvalued" in result.reason.lower()


class TestPairsHold:

    def test_hold_within_bounds(self, monkeypatch):
        """Z-score within entry bounds → HOLD."""
        monkeypatch.setattr(settings, "ENABLE_PAIRS_TRADING", True)
        monkeypatch.setattr(settings, "PAIRS_SYMBOLS", [("STOCK_A", "STOCK_B")])
        monkeypatch.setattr(settings, "PAIRS_ENTRY_Z", 2.0)
        monkeypatch.setattr(settings, "PAIRS_LOOKBACK", 50)
        monkeypatch.setattr(settings, "PAIRS_MIN_HISTORY", 20)

        np.random.seed(0)
        # Both stocks move together — no divergence
        df_a = _make_candles(n=60, base=2000.0, trend=0.1)
        df_b = _make_candles(n=60, base=2000.0, trend=0.1)

        mock_md = MagicMock()
        mock_md.get_todays_candles.return_value = df_b

        strat = PairsTradingStrategy(market_data=mock_md)
        result = strat.analyze(df_a, "STOCK_A")

        assert result.signal == Signal.HOLD
        assert "within bounds" in result.reason.lower()


class TestPairsNoPartner:

    def test_symbol_not_in_pair(self, monkeypatch):
        """Symbol not in any configured pair → HOLD."""
        monkeypatch.setattr(settings, "PAIRS_SYMBOLS", [("HDFCBANK", "ICICIBANK")])

        mock_md = MagicMock()
        strat = PairsTradingStrategy(market_data=mock_md)

        df = _make_candles(n=30)
        result = strat.analyze(df, "RELIANCE")

        assert result.signal == Signal.HOLD
        assert "Not in any" in result.reason


class TestPairsNoData:

    def test_no_market_data(self, monkeypatch):
        """No market_data reference → HOLD gracefully."""
        monkeypatch.setattr(settings, "PAIRS_SYMBOLS", [("STOCK_A", "STOCK_B")])

        strat = PairsTradingStrategy(market_data=None)

        df = _make_candles(n=30)
        result = strat.analyze(df, "STOCK_A")

        assert result.signal == Signal.HOLD
        assert "No market data" in result.reason

    def test_partner_data_empty(self, monkeypatch):
        """Partner returns empty DataFrame → HOLD."""
        monkeypatch.setattr(settings, "PAIRS_SYMBOLS", [("STOCK_A", "STOCK_B")])

        mock_md = MagicMock()
        mock_md.get_todays_candles.return_value = pd.DataFrame()

        strat = PairsTradingStrategy(market_data=mock_md)

        df = _make_candles(n=30)
        result = strat.analyze(df, "STOCK_A")

        assert result.signal == Signal.HOLD

    def test_insufficient_aligned_data(self, monkeypatch):
        """Too few aligned candles → HOLD."""
        monkeypatch.setattr(settings, "PAIRS_SYMBOLS", [("STOCK_A", "STOCK_B")])
        monkeypatch.setattr(settings, "PAIRS_MIN_HISTORY", 20)

        # Only 5 candles for partner — not enough
        mock_md = MagicMock()
        mock_md.get_todays_candles.return_value = _make_candles(n=5)

        strat = PairsTradingStrategy(market_data=mock_md)

        df = _make_candles(n=60)
        result = strat.analyze(df, "STOCK_A")

        assert result.signal == Signal.HOLD
