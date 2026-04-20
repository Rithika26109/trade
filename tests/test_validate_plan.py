"""
tests/test_validate_plan.py
───────────────────────────
Exercises scripts/validate_plan.py as a module:
  - Valid plan passes
  - Schema violations fail
  - Date mismatch fails
  - Risk overrides exceeding caps fail
  - Duplicate symbols fail
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from config import settings

REPO_ROOT = Path(__file__).resolve().parent.parent

# Load scripts/validate_plan.py as a module (it's not a package).
spec = importlib.util.spec_from_file_location(
    "validate_plan", REPO_ROOT / "scripts" / "validate_plan.py"
)
validate_plan = importlib.util.module_from_spec(spec)
sys.modules["validate_plan"] = validate_plan
spec.loader.exec_module(validate_plan)  # type: ignore[union-attr]


def _today() -> str:
    return settings.now_ist().date().isoformat()


def _base_plan() -> dict:
    return {
        "date": _today(),
        "version": 1,
        "watchlist": [
            {"symbol": "RELIANCE", "bias": "long", "conviction": 4},
            {"symbol": "HDFCBANK", "bias": "both", "conviction": 3},
        ],
    }


def test_valid_plan_passes():
    errors = validate_plan.validate(_base_plan())
    assert errors == [], f"unexpected: {errors}"


def test_missing_required_field_fails():
    bad = _base_plan()
    bad.pop("watchlist")
    errors = validate_plan.validate(bad)
    assert errors
    assert any("watchlist" in e for e in errors)


def test_date_mismatch_fails():
    bad = _base_plan()
    bad["date"] = "2000-01-01"
    errors = validate_plan.validate(bad)
    assert errors
    assert any("date" in e.lower() for e in errors)


def test_risk_override_above_cap_fails():
    bad = _base_plan()
    bad["risk_overrides"] = {
        "max_trades": settings.MAX_TRADES_PER_DAY + 1,
    }
    errors = validate_plan.validate(bad)
    assert errors
    assert any("max_trades" in e for e in errors)


def test_duplicate_symbol_fails():
    bad = _base_plan()
    bad["watchlist"].append(
        {"symbol": "RELIANCE", "bias": "short", "conviction": 2}
    )
    errors = validate_plan.validate(bad)
    assert errors
    assert any("duplicate" in e.lower() or "reliance" in e.lower() for e in errors)


def test_all_avoid_fails():
    bad = _base_plan()
    bad["watchlist"] = [
        {"symbol": "RELIANCE", "bias": "avoid", "conviction": 1},
        {"symbol": "TCS", "bias": "avoid", "conviction": 1},
    ]
    errors = validate_plan.validate(bad)
    assert errors
    assert any("tradeable" in e.lower() or "avoid" in e.lower() for e in errors)


def test_invalid_bias_enum_fails():
    bad = _base_plan()
    bad["watchlist"][0]["bias"] = "sideways"
    errors = validate_plan.validate(bad)
    assert errors


def test_example_fixture_validates():
    """The bundled example plan must be schema-valid (dates may drift)."""
    example = REPO_ROOT / "config" / "daily_plan.example.json"
    data = json.loads(example.read_text())
    # Force today's date so date-freshness check passes
    data["date"] = _today()
    errors = validate_plan.validate(data)
    assert errors == [], f"example plan failed schema: {errors}"
