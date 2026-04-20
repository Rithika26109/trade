"""
Phase 4 — SEBI compliance & ops tests.

Covers:
    * Algo-ID format validation (strict in live, lenient in paper)
    * Static-IP pin is skipped when not configured
    * Kill-switch engage / disengage / read lifecycle
    * Audit JSONL is append-only, safe-by-default, tolerates bad types
    * OrderManager._broker_call enforces order-rate cap
    * OrderManager writes audit entries on paper order place + close
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings
from src.execution.order_manager import OrderManager
from src.strategy.base import Signal, TradeSignal
from src.utils import audit as audit_mod
from src.utils import kill_switch
from src.utils.compliance import (
    ComplianceError,
    validate_algo_id,
    validate_static_ip,
)


# ──────────────────────────────────────────────────────────────────────
# Algo-ID validation
# ──────────────────────────────────────────────────────────────────────
class TestAlgoIDValidation:
    def test_valid_tag_accepted(self, monkeypatch):
        monkeypatch.setattr(settings, "ALGO_ID", "ALGO01")
        assert validate_algo_id(strict=True) == "ALGO01"

    def test_empty_tag_rejected_strict(self, monkeypatch):
        monkeypatch.setattr(settings, "ALGO_ID", "")
        with pytest.raises(ComplianceError):
            validate_algo_id(strict=True)

    def test_empty_tag_ok_paper(self, monkeypatch):
        monkeypatch.setattr(settings, "ALGO_ID", "")
        assert validate_algo_id(strict=False) == ""

    def test_invalid_chars_rejected_strict(self, monkeypatch):
        monkeypatch.setattr(settings, "ALGO_ID", "ALGO 01!")
        with pytest.raises(ComplianceError):
            validate_algo_id(strict=True)

    def test_too_long_tag_rejected_strict(self, monkeypatch):
        monkeypatch.setattr(settings, "ALGO_ID", "A" * 21)
        with pytest.raises(ComplianceError):
            validate_algo_id(strict=True)


# ──────────────────────────────────────────────────────────────────────
# Static-IP pin
# ──────────────────────────────────────────────────────────────────────
class TestStaticIPCheck:
    def test_not_configured_returns_none(self, monkeypatch):
        monkeypatch.setattr(settings, "STATIC_IP_EXPECTED", "")
        assert validate_static_ip(strict=True) is None


# ──────────────────────────────────────────────────────────────────────
# Kill-switch
# ──────────────────────────────────────────────────────────────────────
class TestKillSwitch:
    def test_engage_disengage(self, monkeypatch):
        path = Path(tempfile.mkdtemp()) / ".kill_switch"
        monkeypatch.setattr(settings, "KILL_SWITCH_PATH", str(path))

        assert not kill_switch.is_engaged()
        kill_switch.engage("unit-test-reason")
        assert kill_switch.is_engaged()
        assert kill_switch.reason() == "unit-test-reason"
        kill_switch.disengage()
        assert not kill_switch.is_engaged()


# ──────────────────────────────────────────────────────────────────────
# Audit log
# ──────────────────────────────────────────────────────────────────────
class TestAuditLog:
    def test_append_jsonl(self, monkeypatch, tmp_path):
        log_path = tmp_path / "audit.jsonl"
        monkeypatch.setattr(settings, "AUDIT_LOG_PATH", str(log_path))

        audit_mod.audit("unit_test", a=1, b="two")
        audit_mod.audit("unit_test2", symbol="X")

        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 2
        rec0 = json.loads(lines[0])
        assert rec0["event"] == "unit_test"
        assert rec0["a"] == 1
        assert rec0["b"] == "two"
        assert "ts" in rec0
        assert "algo_id" in rec0

    def test_non_serializable_is_coerced(self, monkeypatch, tmp_path):
        log_path = tmp_path / "audit.jsonl"
        monkeypatch.setattr(settings, "AUDIT_LOG_PATH", str(log_path))

        class Weird:
            def __repr__(self):
                return "<Weird>"

        # Should NOT raise
        audit_mod.audit("weird", obj=Weird())
        rec = json.loads(log_path.read_text().strip())
        assert rec["obj"] == "<Weird>"


# ──────────────────────────────────────────────────────────────────────
# OrderManager: rate limiter + audit integration
# ──────────────────────────────────────────────────────────────────────
class _DummyKite:
    pass


class TestOrderRateLimiter:
    def test_broker_call_is_rate_limited(self, monkeypatch):
        monkeypatch.setattr(settings, "ORDER_RATE_LIMIT_PER_SEC", 4)
        monkeypatch.setattr(settings, "TRADING_MODE", "paper")
        om = OrderManager(kite=None)
        calls = {"n": 0}

        def _f():
            calls["n"] += 1
            return "ok"

        start = time.monotonic()
        # 8 calls with a 4/sec cap => >= 1.0 s elapsed
        for _ in range(8):
            om._broker_call("lbl", _f)
        elapsed = time.monotonic() - start

        assert calls["n"] == 8
        assert elapsed >= 0.9, f"Rate limiter did not throttle (elapsed={elapsed:.2f}s)"


class TestOrderManagerAuditIntegration:
    def test_paper_order_place_and_close_emit_audit(self, monkeypatch, tmp_path):
        log_path = tmp_path / "audit.jsonl"
        monkeypatch.setattr(settings, "AUDIT_LOG_PATH", str(log_path))
        monkeypatch.setattr(settings, "TRADING_MODE", "paper")

        om = OrderManager(kite=None)
        om.is_paper = True

        sig_ = TradeSignal(
            signal=Signal.BUY,
            symbol="RELIANCE",
            price=2500.0,
            quantity=5,
            stop_loss=2480.0,
            target=2540.0,
            reason="test",
            strategy="ORB",
        )
        order = om.place_order(sig_, exchange="NSE")
        assert order is not None

        om.close_position(order, exit_price=2530.0, reason="test_exit")

        lines = log_path.read_text().strip().splitlines()
        events = [json.loads(l)["event"] for l in lines]
        assert "order_place" in events
        assert "order_close" in events
