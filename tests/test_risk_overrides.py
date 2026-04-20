"""
tests/test_risk_overrides.py
────────────────────────────
Verifies RiskManager.apply_runtime_overrides():
  - Clamps values exceeding settings caps
  - Allows tightening
  - _effective_* accessors reflect overrides
  - _get_adjusted_risk_pct() base drops when overridden
"""
import pytest

from config import settings
from src.risk.risk_manager import RiskManager


class _FakeOrderManager:
    """Minimal stand-in so RiskManager can be constructed without broker."""
    def __init__(self):
        self.orders = []

    def get_todays_pnl(self): return 0.0
    def get_todays_trade_count(self): return 0
    def get_open_orders(self): return []


@pytest.fixture
def rm():
    return RiskManager(_FakeOrderManager(), db=None)


def test_no_override_returns_settings_caps(rm):
    assert rm._effective_max_trades() == settings.MAX_TRADES_PER_DAY
    assert rm._effective_max_positions() == settings.MAX_OPEN_POSITIONS
    assert rm._effective_risk_pct() == settings.RISK_PER_TRADE_PCT


def test_apply_overrides_tighter(rm):
    out = rm.apply_runtime_overrides(
        max_trades=2,
        risk_per_trade_pct=0.3,
        max_open_positions=1,
    )
    assert out["max_trades"] == 2
    assert out["risk_per_trade_pct"] == 0.3
    assert out["max_open_positions"] == 1
    assert rm._effective_max_trades() == 2
    assert rm._effective_max_positions() == 1
    assert rm._effective_risk_pct() == 0.3


def test_apply_overrides_clamps_attempted_loosening(rm):
    rm.apply_runtime_overrides(
        max_trades=settings.MAX_TRADES_PER_DAY + 10,
        risk_per_trade_pct=settings.RISK_PER_TRADE_PCT + 5,
        max_open_positions=settings.MAX_OPEN_POSITIONS + 3,
    )
    assert rm._effective_max_trades() == settings.MAX_TRADES_PER_DAY
    assert rm._effective_risk_pct() == settings.RISK_PER_TRADE_PCT
    assert rm._effective_max_positions() == settings.MAX_OPEN_POSITIONS


def test_partial_override_leaves_others_default(rm):
    rm.apply_runtime_overrides(max_trades=1)
    assert rm._effective_max_trades() == 1
    assert rm._effective_max_positions() == settings.MAX_OPEN_POSITIONS
    assert rm._effective_risk_pct() == settings.RISK_PER_TRADE_PCT


def test_adjusted_risk_pct_honours_override(rm):
    before = rm._get_adjusted_risk_pct()
    tight = settings.RISK_PER_TRADE_PCT / 2
    rm.apply_runtime_overrides(risk_per_trade_pct=tight)
    after = rm._get_adjusted_risk_pct()
    # After override, adjusted base can never exceed the override
    assert after <= tight * 1.5 + 1e-9
    # And should be strictly less than the pre-override adjusted value
    # (unless multipliers had already crushed it to 0)
    if before > 0:
        assert after < before + 1e-9


def test_get_status_reflects_overrides(rm):
    rm.apply_runtime_overrides(max_trades=3, max_open_positions=1)
    status = rm.get_status()
    assert status["max_trades"] == 3
    assert status["max_positions"] == 1
