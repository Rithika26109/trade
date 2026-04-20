"""
Security hardening tests
────────────────────────
Covers the April-2026 security review fixes:
    * File permissions on secrets / DB / audit log
    * Notifier secret redaction
    * RateLimiter hard-cap on max_calls
    * Compliance format validation (strict regardless of mode)
    * Watchlist regex validation in settings.validate_config
    * OrderManager refuses to place when kill-switch is engaged
"""

from __future__ import annotations

import os
import stat
import sys
import warnings
from pathlib import Path

import pytest

from config import settings


POSIX_ONLY = pytest.mark.skipif(
    sys.platform.startswith("win"), reason="POSIX-only file-mode assertions"
)


# ──────────────────────────────────────────────────────────────────────
# File permissions
# ──────────────────────────────────────────────────────────────────────
@POSIX_ONLY
class TestFilePermissions:
    def test_db_file_is_0600(self, tmp_path, monkeypatch):
        from src.utils.db import TradeDB

        db_path = tmp_path / "sub" / "trades.db"
        TradeDB(db_path=db_path)
        assert db_path.exists()
        mode = stat.S_IMODE(db_path.stat().st_mode)
        assert mode == 0o600, f"expected 0600, got {oct(mode)}"
        parent_mode = stat.S_IMODE(db_path.parent.stat().st_mode)
        assert parent_mode == 0o700, f"parent expected 0700, got {oct(parent_mode)}"

    def test_audit_file_is_0600(self, tmp_path, monkeypatch):
        from src.utils import audit as audit_mod

        path = tmp_path / "audit" / "audit.jsonl"
        monkeypatch.setattr(settings, "AUDIT_LOG_PATH", str(path))
        audit_mod.audit("unit_test", x=1)
        assert path.exists()
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o600, f"expected 0600, got {oct(mode)}"


# ──────────────────────────────────────────────────────────────────────
# Notifier redaction
# ──────────────────────────────────────────────────────────────────────
class TestNotifierRedaction:
    def test_redact_common_patterns(self):
        from src.utils.notifier import redact

        cases = [
            ("api_key=abc123xyz", "api_key=***"),
            ("access_token: 'ZZZ-Secret-Value'", "access_token=***"),
            ('password="hunter2"', "password=***"),
            ("totp_secret=JBSWY3DPEHPK3PXP", "totp_secret=***"),
        ]
        for inp, expected_fragment in cases:
            out = redact(inp)
            assert "***" in out, f"did not redact: {inp!r} -> {out!r}"
            assert "abc123xyz" not in out
            assert "hunter2" not in out
            assert "JBSWY3DPEHPK3PXP" not in out
            assert "Secret-Value" not in out

    def test_redact_preserves_non_secret_text(self):
        from src.utils.notifier import redact

        safe = "Bot crashed at 10:32 while placing RELIANCE order"
        assert redact(safe) == safe


# ──────────────────────────────────────────────────────────────────────
# RateLimiter hard cap
# ──────────────────────────────────────────────────────────────────────
class TestRateLimiterCap:
    def test_clamps_above_zerodha_cap(self):
        from src.utils.rate_limiter import RateLimiter

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            rl = RateLimiter(max_calls=25, period=1.0)
        assert rl.max_calls == RateLimiter.ZERODHA_HARD_CAP == 10
        assert any("clamping" in str(w.message).lower() for w in caught)

    def test_respects_lower_values(self):
        from src.utils.rate_limiter import RateLimiter

        rl = RateLimiter(max_calls=3, period=1.0)
        assert rl.max_calls == 3


# ──────────────────────────────────────────────────────────────────────
# Compliance: malformed ALGO_ID is always a hard error
# ──────────────────────────────────────────────────────────────────────
class TestComplianceStrictFormat:
    def test_invalid_algo_id_rejected_even_paper(self, monkeypatch):
        from src.utils.compliance import ComplianceError, validate_algo_id

        monkeypatch.setattr(settings, "ALGO_ID", "BAD ID!")
        with pytest.raises(ComplianceError):
            validate_algo_id(strict=False)

    def test_invalid_static_ip_config_rejected(self, monkeypatch):
        from src.utils.compliance import ComplianceError, validate_static_ip

        monkeypatch.setattr(settings, "STATIC_IP_EXPECTED", "not-an-ip")
        with pytest.raises(ComplianceError):
            validate_static_ip(strict=False)


# ──────────────────────────────────────────────────────────────────────
# Watchlist regex validation
# ──────────────────────────────────────────────────────────────────────
class TestWatchlistValidation:
    def test_accepts_default_watchlist(self, monkeypatch):
        # Default watchlist must validate cleanly.
        settings.validate_config()

    def test_rejects_bogus_symbol(self, monkeypatch):
        monkeypatch.setattr(settings, "WATCHLIST", ["RELIANCE", "../../etc/passwd"])
        with pytest.raises(ValueError, match="WATCHLIST"):
            settings.validate_config()

    def test_rejects_lowercase(self, monkeypatch):
        monkeypatch.setattr(settings, "WATCHLIST", ["reliance"])
        with pytest.raises(ValueError, match="WATCHLIST"):
            settings.validate_config()


# ──────────────────────────────────────────────────────────────────────
# Kill-switch is re-checked at order submit
# ──────────────────────────────────────────────────────────────────────
class TestKillSwitchAtSubmit:
    def test_place_order_blocked_when_engaged(self, tmp_path, monkeypatch):
        from src.execution.order_manager import OrderManager
        from src.strategy.base import Signal, TradeSignal
        from src.utils import kill_switch

        ks_path = tmp_path / ".kill_switch"
        monkeypatch.setattr(settings, "KILL_SWITCH_PATH", str(ks_path))

        om = OrderManager(kite=None)
        om.is_paper = True

        sig = TradeSignal(
            symbol="RELIANCE",
            signal=Signal.BUY,
            price=2500.0,
            quantity=1,
            stop_loss=2490.0,
            target=2520.0,
            reason="unit-test",
            strategy="test",
        )

        # Sanity: no kill-switch → order placed.
        assert kill_switch.is_engaged() is False
        assert om.place_order(sig) is not None
        om.orders.clear()

        # Engage → order must be refused.
        kill_switch.engage("unit-test")
        try:
            assert om.place_order(sig) is None
        finally:
            kill_switch.disengage()
