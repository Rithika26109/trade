"""
Phase 2 — Live/backtest parity tests.

Covers the changes that bring the live path onto the same footing as the
backtest stack:

- Daily-anchored VWAP (resets at session boundaries).
- `drop_incomplete_last_bar` strips a trailing partial candle so indicators
  only see closed bars.
- ORB one-trade-per-day guard (live can't re-enter after a fill).
- Multi-day HTF cache on `MarketData.get_htf_data`.
- Backtest synthetic-data guard (`--allow-synthetic` opt-in).
- Backtest intraday square-off helper (`_past_square_off`).
"""

from __future__ import annotations

from datetime import datetime, time as dtime, timedelta
from unittest.mock import MagicMock

import pandas as pd
import pytest

from config import settings
from src.indicators.indicators import (
    add_all_indicators,
    add_vwap,
    drop_incomplete_last_bar,
)
from src.strategy.base import Signal
from src.strategy.orb import ORBStrategy


# ─────────────────────────────── fixtures ────────────────────────────────
def _ohlcv(dates, closes, volumes=None):
    n = len(dates)
    vols = volumes if volumes is not None else [1_000] * n
    df = pd.DataFrame({
        "date": dates,
        "open": closes,
        "high": [c * 1.002 for c in closes],
        "low": [c * 0.998 for c in closes],
        "close": closes,
        "volume": vols,
    })
    return df


# ─────────────────────────── daily-anchored VWAP ─────────────────────────
class TestDailyAnchoredVWAP:
    def test_vwap_resets_at_day_boundary(self):
        # Two sessions of three bars each; day-2 price sits well above day-1
        # so a non-resetting VWAP would drag day-2's value down.
        d1 = pd.date_range("2026-04-17 09:15", periods=3, freq="5min", tz=settings.IST)
        d2 = pd.date_range("2026-04-18 09:15", periods=3, freq="5min", tz=settings.IST)
        dates = d1.tolist() + d2.tolist()
        closes = [100.0, 100.0, 100.0, 200.0, 200.0, 200.0]
        df = _ohlcv(dates, closes, volumes=[1_000] * 6)

        df = add_vwap(df)

        # On day-2 the VWAP must track the new session prices, not stay near 150.
        day2_first = df["vwap"].iloc[3]
        day2_last = df["vwap"].iloc[-1]
        assert abs(day2_first - 200.0) < 0.5
        assert abs(day2_last - 200.0) < 0.5

        # Day-1 VWAP should sit at ~100 (not contaminated by day-2).
        assert abs(df["vwap"].iloc[2] - 100.0) < 0.5

    def test_vwap_missing_volume_noop(self):
        # When volume column is absent `add_vwap` should return df unchanged.
        df = pd.DataFrame({
            "date": pd.date_range("2026-04-17 09:15", periods=3, freq="5min"),
            "open": [100, 101, 102],
            "high": [100, 101, 102],
            "low": [100, 101, 102],
            "close": [100, 101, 102],
        })
        out = add_vwap(df)
        assert "vwap" not in out.columns


# ───────────────────────── drop partial last bar ─────────────────────────
class TestDropIncompleteLastBar:
    def test_drops_partial_bar(self):
        dates = pd.date_range("2026-04-17 09:15", periods=3, freq="5min", tz=settings.IST)
        df = _ohlcv(dates.tolist(), [100, 101, 102])
        # Simulate wall-clock 1 minute into the 3rd bar (bar close = 09:30).
        now = datetime(2026, 4, 17, 9, 26, tzinfo=settings.IST)
        trimmed = drop_incomplete_last_bar(df, 300, now_ts=now)
        assert len(trimmed) == len(df) - 1

    def test_keeps_closed_bar(self):
        dates = pd.date_range("2026-04-17 09:15", periods=3, freq="5min", tz=settings.IST)
        df = _ohlcv(dates.tolist(), [100, 101, 102])
        # Wall clock past the 3rd bar close (09:30).
        now = datetime(2026, 4, 17, 9, 31, tzinfo=settings.IST)
        trimmed = drop_incomplete_last_bar(df, 300, now_ts=now)
        assert len(trimmed) == len(df)


# ────────────────────────── ORB traded_today guard ───────────────────────
class TestORBTradedGuard:
    def test_emits_one_signal_per_day(self, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_CONFLUENCE_SCORING", False)
        monkeypatch.setattr(settings, "ENABLE_REGIME_DETECTION", False)
        monkeypatch.setattr(settings, "ORB_VOLUME_MULTIPLIER", 0.0)
        monkeypatch.setattr(settings, "STOP_LOSS_TYPE", "ORB_RANGE")
        monkeypatch.setattr(settings, "MIN_RISK_REWARD_RATIO", 2.0)

        strat = ORBStrategy()
        strat.set_opening_range("RELIANCE", high=2500, low=2490, open_price=2495)

        # 60 bars: flat around 2495, then a clean breakout above 2500 at the end
        # so indicator warm-up (MACD needs ~26 bars) has room to settle.
        n = 60
        dates = pd.date_range("2026-04-17 09:30", periods=n, freq="5min", tz=settings.IST)
        closes = [2495.0] * (n - 2) + [2499.0, 2510.0]
        df = _ohlcv(dates.tolist(), closes, volumes=[100_000] * n)
        df = add_all_indicators(df)

        sig1 = strat.analyze(df, "RELIANCE")
        assert sig1.signal == Signal.BUY

        # A second call on the same session must be suppressed.
        sig2 = strat.analyze(df, "RELIANCE")
        assert sig2.signal == Signal.HOLD
        assert "already traded" in sig2.reason.lower()


# ─────────────────────────── HTF cache in MarketData ─────────────────────
class TestHTFCache:
    def test_htf_fetched_once_per_day(self, monkeypatch):
        from src.data.market_data import MarketData

        md = MarketData.__new__(MarketData)  # Skip __init__ (needs kite)
        md.kite = None
        md._instruments_cache = {}
        md._htf_cache = {}

        call_counter = {"n": 0}

        def fake_fetch(symbol, interval="5minute", days=5, exchange="NSE"):
            call_counter["n"] += 1
            return _ohlcv(
                pd.date_range("2026-04-17 09:15", periods=10, freq="15min").tolist(),
                [100.0 + i for i in range(10)],
            )

        monkeypatch.setattr(md, "get_historical_data", fake_fetch)

        df1 = md.get_htf_data("RELIANCE", interval="15minute", days=5)
        df2 = md.get_htf_data("RELIANCE", interval="15minute", days=5)

        assert not df1.empty
        assert call_counter["n"] == 1  # Second call must hit cache


# ─────────────────────────── Backtest guards ─────────────────────────────
class TestBacktestGuards:
    def test_synthetic_data_opt_in(self, monkeypatch, capsys):
        pytest.importorskip("backtesting")
        from backtest import run_backtest

        # Stub out the Zerodha loader so it always fails, forcing the
        # synthetic fallback path.
        class _Boom:
            def __init__(self, *a, **kw): raise RuntimeError("no broker")
        monkeypatch.setattr(run_backtest, "ZerodhaAuth", _Boom, raising=False)

        df = run_backtest.load_sample_data("INFY", days=5, allow_synthetic=False)
        assert df.empty
        captured = capsys.readouterr()
        assert "--allow-synthetic" in captured.out

    def test_past_square_off(self):
        pytest.importorskip("backtesting")
        from backtest.run_backtest import _past_square_off

        early = pd.Timestamp("2026-04-17 14:00")
        late = pd.Timestamp("2026-04-17 15:20")
        at = pd.Timestamp("2026-04-17 15:15")

        assert _past_square_off(early) is False
        assert _past_square_off(at) is True
        assert _past_square_off(late) is True
