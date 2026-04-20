"""
tests/test_plan_loader.py
─────────────────────────
Verifies:
  - Missing file → None (no crash)
  - Malformed JSON → None
  - Stale date → None
  - Valid plan with avoid bias filters tradeable list
  - Risk overrides are clamped to settings caps
  - allows_direction() respects bias
"""
import json
from pathlib import Path

import pytest

from config import settings
from src.utils import plan_loader


def _write(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "daily_plan.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _today() -> str:
    return settings.now_ist().date().isoformat()


def test_missing_file_returns_none(tmp_path):
    assert plan_loader.load_plan(tmp_path / "does_not_exist.json") is None


def test_malformed_json_returns_none(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not valid json", encoding="utf-8")
    assert plan_loader.load_plan(p) is None


def test_stale_date_is_rejected(tmp_path):
    p = _write(tmp_path, {
        "date": "1999-01-01",
        "version": 1,
        "watchlist": [{"symbol": "RELIANCE", "bias": "long", "conviction": 3}],
    })
    assert plan_loader.load_plan(p) is None


def test_valid_plan_loads_with_avoid_filtered(tmp_path):
    p = _write(tmp_path, {
        "date": _today(),
        "version": 1,
        "watchlist": [
            {"symbol": "RELIANCE", "bias": "long", "conviction": 4},
            {"symbol": "TCS", "bias": "avoid", "conviction": 1, "notes": "results today"},
            {"symbol": "HDFCBANK", "bias": "both", "conviction": 3},
        ],
    })
    plan = plan_loader.load_plan(p)
    assert plan is not None
    # avoid symbols filtered from tradeable watchlist
    assert plan.watchlist == ["RELIANCE", "HDFCBANK"]
    # but bias map still carries avoid
    assert plan.bias_by_symbol["TCS"] == "avoid"
    assert plan.conviction_by_symbol["RELIANCE"] == 4


def test_risk_overrides_clamp_to_settings_caps(tmp_path):
    # Try to loosen: pass values > settings caps
    p = _write(tmp_path, {
        "date": _today(),
        "version": 1,
        "watchlist": [{"symbol": "RELIANCE", "bias": "long", "conviction": 3}],
        "risk_overrides": {
            "max_trades": settings.MAX_TRADES_PER_DAY + 100,
            "risk_per_trade_pct": settings.RISK_PER_TRADE_PCT + 5,
            "max_open_positions": settings.MAX_OPEN_POSITIONS + 10,
        },
    })
    plan = plan_loader.load_plan(p)
    assert plan is not None
    assert plan.risk_overrides["max_trades"] == settings.MAX_TRADES_PER_DAY
    assert plan.risk_overrides["risk_per_trade_pct"] == settings.RISK_PER_TRADE_PCT
    assert plan.risk_overrides["max_open_positions"] == settings.MAX_OPEN_POSITIONS


def test_risk_overrides_tighter_passes_through(tmp_path):
    p = _write(tmp_path, {
        "date": _today(),
        "version": 1,
        "watchlist": [{"symbol": "RELIANCE", "bias": "long", "conviction": 3}],
        "risk_overrides": {
            "max_trades": 2,
            "risk_per_trade_pct": 0.5,
            "max_open_positions": 1,
        },
    })
    plan = plan_loader.load_plan(p)
    assert plan.risk_overrides["max_trades"] == 2
    assert plan.risk_overrides["risk_per_trade_pct"] == 0.5
    assert plan.risk_overrides["max_open_positions"] == 1


def test_all_avoid_plan_is_rejected(tmp_path):
    # If every single symbol is avoid, there's nothing tradeable — ignore.
    p = _write(tmp_path, {
        "date": _today(),
        "version": 1,
        "watchlist": [
            {"symbol": "RELIANCE", "bias": "avoid", "conviction": 1},
            {"symbol": "TCS", "bias": "avoid", "conviction": 1},
        ],
    })
    assert plan_loader.load_plan(p) is None


def test_allows_direction_respects_bias():
    plan = plan_loader.DailyPlan(
        date=_today(),
        version=1,
        bias_by_symbol={
            "A": "long",
            "B": "short",
            "C": "both",
            "D": "avoid",
        },
    )
    assert plan.allows_direction("A", "BUY") is True
    assert plan.allows_direction("A", "SELL") is False
    assert plan.allows_direction("B", "SELL") is True
    assert plan.allows_direction("B", "BUY") is False
    assert plan.allows_direction("C", "BUY") is True
    assert plan.allows_direction("C", "SELL") is True
    assert plan.allows_direction("D", "BUY") is False
    assert plan.allows_direction("D", "SELL") is False
    # Unknown symbol → permissive
    assert plan.allows_direction("Z", "BUY") is True


def test_malformed_entry_is_skipped_not_fatal(tmp_path):
    p = _write(tmp_path, {
        "date": _today(),
        "version": 1,
        "watchlist": [
            {"symbol": "RELIANCE", "bias": "long", "conviction": 4},
            {"symbol": "BAD", "bias": "nonsense-bias", "conviction": 3},
        ],
    })
    plan = plan_loader.load_plan(p)
    assert plan is not None
    assert "RELIANCE" in plan.watchlist
    # Unknown bias is coerced to "both" (still tradeable), not dropped.
    assert plan.bias_by_symbol.get("BAD") == "both"
