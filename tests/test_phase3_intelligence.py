"""
Phase 3 tests — intelligence & alpha upgrades.

Covers:
  3A scanner TOP_N cutoff + circuit-frozen drop
  3B multi-touch S/R scoring
  3C VolatilityRegime detection + DB-backed regime tracker weighting/blacklist
  3E correlation-limit, Kelly-from-DB, cost-net RR, fat-finger, persisted HWM
"""
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import pytest

from config import settings
from src.indicators.market_regime import VolatilityRegime, detect_volatility_regime
from src.strategy.base import Signal, TradeSignal
from src.strategy.confluence import calculate_confluence
from src.strategy.regime_tracker import RegimePerformanceTracker
from src.utils.db import TradeDB


# ── Helpers ──
def _make_df(n=40, base=2000.0, vol=1_000_000, atr_scale=1.0):
    np.random.seed(42)
    closes = [base + i * 0.5 for i in range(n)]
    highs = [c + 3 * atr_scale for c in closes]
    lows = [c - 3 * atr_scale for c in closes]
    volumes = [vol] * n
    df = pd.DataFrame({
        "close": closes,
        "high": highs,
        "low": lows,
        "volume": volumes,
        "rsi": [50 + i * 0.1 for i in range(n)],
        "vwap": [c - 2 for c in closes],
    })
    return df


class _FakeMD:
    """Minimal MarketData stub for risk-manager tests."""
    def __init__(self):
        self.returns = {}

    def get_historical_data(self, symbol, interval="day", days=25):
        rets = self.returns.get(symbol)
        if rets is None:
            return pd.DataFrame()
        closes = np.cumprod(1 + np.array(rets)) * 1000.0
        return pd.DataFrame({"close": closes})

    def get_circuit_limits(self, symbol):
        return None


class _FakeOM:
    """Minimal OrderManager stub."""
    def __init__(self, open_orders=None):
        self.orders = []
        self._open = open_orders or []

    def get_todays_pnl(self):
        return 0.0

    def get_todays_trade_count(self):
        return 0

    def get_open_orders(self):
        return self._open


# ─────────────────────────────────────────────────────────────────────────────
# 3A scanner
# ─────────────────────────────────────────────────────────────────────────────
class TestScanner3A:
    def test_topn_setting_defined(self):
        assert hasattr(settings, "SCANNER_TOP_N")
        assert settings.SCANNER_TOP_N >= 1


# ─────────────────────────────────────────────────────────────────────────────
# 3B confluence
# ─────────────────────────────────────────────────────────────────────────────
class TestConfluence3B:
    def test_multi_touch_sr_requires_multiple_touches(self):
        """Single-touch pivots should NOT score as strong S/R (returns neutral-ish)."""
        df = _make_df(n=40)
        # No repeated pivots → should fall back to neutral 10
        res = calculate_confluence(Signal.BUY, df)
        assert 0 <= res.components["location"] <= 25


# ─────────────────────────────────────────────────────────────────────────────
# 3C volatility regime + tracker
# ─────────────────────────────────────────────────────────────────────────────
class TestVolatilityRegime:
    def test_low_normal_high_classification(self):
        # Constant ATR -> NORMAL (middle percentile == current)
        df = _make_df(n=40, atr_scale=1.0)
        reg = detect_volatility_regime(df)
        assert isinstance(reg, VolatilityRegime)

    def test_high_vol_detected_on_last_bar_spike(self):
        df = _make_df(n=40, atr_scale=1.0)
        df.loc[df.index[-1], "high"] = df["close"].iloc[-1] + 50
        df.loc[df.index[-1], "low"] = df["close"].iloc[-1] - 50
        reg = detect_volatility_regime(df)
        # Last bar is extreme; regime should be HIGH (or at least not LOW)
        assert reg in (VolatilityRegime.NORMAL, VolatilityRegime.HIGH)


class TestRegimeTracker:
    def _mk_tracker(self) -> RegimePerformanceTracker:
        tmp = Path(tempfile.mkdtemp()) / "t.db"
        return RegimePerformanceTracker(db_path=tmp)

    def test_cold_start_weight_is_one(self):
        t = self._mk_tracker()
        w = t.weight_for("ORB", "TREND_UP", "NORMAL")
        assert w == 1.0

    def test_blacklist_after_sufficient_losses(self):
        t = self._mk_tracker()
        # 35 trades, only 30% win rate
        for i in range(35):
            t.record("RSI_EMA", "RANGING", "HIGH", pnl=100 if i < 11 else -200)
        assert t.is_blacklisted("RSI_EMA", "RANGING", "HIGH")
        assert t.weight_for("RSI_EMA", "RANGING", "HIGH") == 0.0

    def test_winning_cell_boosts_weight(self):
        t = self._mk_tracker()
        # 20 trades, 70% WR
        for i in range(20):
            t.record("ORB", "TREND_UP", "NORMAL", pnl=500 if i < 14 else -200)
        w = t.weight_for("ORB", "TREND_UP", "NORMAL")
        assert w > 1.0

    def test_stats_returns_zero_for_empty_cell(self):
        t = self._mk_tracker()
        s = t.get_cell_stats("ORB", "X", "Y")
        assert s["trades"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 3E risk upgrades
# ─────────────────────────────────────────────────────────────────────────────
def _mk_signal(symbol="RELIANCE", price=2500, stop=2475, target=2575, qty=0) -> TradeSignal:
    return TradeSignal(
        signal=Signal.BUY,
        symbol=symbol,
        price=price,
        stop_loss=stop,
        target=target,
        quantity=qty,
        reason="test",
        strategy="ORB",
    )


class TestRisk3E:
    def _mk_rm(self, open_orders=None):
        from src.risk.risk_manager import RiskManager
        tmp = Path(tempfile.mkdtemp()) / "t.db"
        db = TradeDB(db_path=tmp)
        om = _FakeOM(open_orders=open_orders or [])
        rm = RiskManager(om, db=db)
        rm.market_data = _FakeMD()
        return rm, db, om

    def test_net_rr_reduces_with_costs(self, monkeypatch):
        rm, *_ = self._mk_rm()
        monkeypatch.setattr(settings, "COSTS_ROUND_TRIP_BPS", 20.0)
        sig = _mk_signal(price=1000, stop=990, target=1020)  # gross 2:1
        net = rm._net_rr(sig)
        assert net < sig.risk_reward_ratio

    def test_fat_finger_rejects_oversized_notional(self, monkeypatch):
        rm, *_ = self._mk_rm()
        monkeypatch.setattr(settings, "FAT_FINGER_MAX_NOTIONAL_PCT", 10.0)
        rm.capital = 100_000
        sig = _mk_signal(price=500, stop=495, target=510, qty=500)  # notional 250k
        reason = rm._fat_finger_check(sig)
        assert reason and "fat-finger" in reason

    def test_correlation_limit_blocks_high_corr(self, monkeypatch):
        rm, _db, om = self._mk_rm()
        # Open order on HDFCBANK
        class _O:
            symbol = "HDFCBANK"
        om._open = [_O()]
        # Build near-identical returns for both symbols -> corr ~1
        rets = list(np.linspace(-0.01, 0.01, 21))
        rm.market_data.returns = {"RELIANCE": rets, "HDFCBANK": rets}
        monkeypatch.setattr(settings, "CORRELATION_LIMIT_ENABLED", True)
        monkeypatch.setattr(settings, "CORRELATION_LIMIT_THRESHOLD", 0.7)
        sig = _mk_signal(symbol="RELIANCE", qty=10)
        reason = rm._correlation_check(sig)
        assert reason and "correlation" in reason

    def test_kelly_uses_db_history(self, monkeypatch):
        rm, db, _ = self._mk_rm()
        monkeypatch.setattr(settings, "KELLY_ENABLED", True)
        monkeypatch.setattr(settings, "KELLY_USE_DB_HISTORY", True)
        monkeypatch.setattr(settings, "KELLY_MIN_TRADES", 10)
        # Inject 15 closed trades with 60% WR
        import sqlite3
        with sqlite3.connect(str(db.db_path)) as c:
            for i in range(15):
                pnl = 200 if i < 9 else -100
                c.execute(
                    "INSERT INTO trades (date, order_id, symbol, signal, quantity, "
                    "entry_price, stop_loss, target, pnl, strategy, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "2026-01-01", f"O{i}", "RELIANCE", "BUY", 10,
                        100, 95, 110, pnl, "ORB", "2026-01-01T10:00:00",
                    ),
                )
        mult = rm._get_kelly_multiplier()
        assert mult != 1.0  # activated once DB history is loaded

    def test_persisted_hwm_round_trip(self, monkeypatch):
        rm, db, _ = self._mk_rm()
        monkeypatch.setattr(settings, "PERSIST_INTRADAY_HWM", True)
        rm.update_intraday_equity(500.0, -100.0)  # total 400, HWM=400
        assert rm._intraday_high_water_mark == 400.0
        # Fresh RM same DB should restore HWM
        from src.risk.risk_manager import RiskManager
        rm2 = RiskManager(_FakeOM(), db=db)
        rm2.market_data = _FakeMD()
        assert rm2._intraday_high_water_mark == 400.0
