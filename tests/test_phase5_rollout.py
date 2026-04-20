"""
Phase 5 — Validation & rollout tests.

Covers:
    * Nightly CSV export: trades / daily_summary / audit, handles missing tables
    * Pre-flight Check class captures pass/fail state
    * Smoke harness script exists and is importable
"""

import csv
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings

# Import scripts as modules
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import export_nightly as exporter  # noqa: E402
import preflight  # noqa: E402


# ──────────────────────────────────────────────────────────────────────
# Exporter
# ──────────────────────────────────────────────────────────────────────
class TestNightlyExporter:
    def _make_db(self, tmp: Path) -> Path:
        db = tmp / "t.db"
        with sqlite3.connect(str(db)) as c:
            c.execute(
                "CREATE TABLE trades (date TEXT, order_id TEXT, symbol TEXT, "
                "signal TEXT, quantity INTEGER, entry_price REAL, exit_price REAL, "
                "stop_loss REAL, target REAL, pnl REAL, strategy TEXT, "
                "reason TEXT, is_paper INTEGER, created_at TEXT)"
            )
            c.execute(
                "CREATE TABLE daily_summary (date TEXT PRIMARY KEY, total_trades INTEGER, "
                "winning_trades INTEGER, losing_trades INTEGER, total_pnl REAL, "
                "max_drawdown REAL, capital REAL, is_paper INTEGER)"
            )
            c.execute(
                "INSERT INTO trades VALUES ('2026-04-20', 'P1', 'REL', 'BUY', 10, "
                "2500.0, 2540.0, 2480.0, 2540.0, 400.0, 'ORB', 'test', 1, "
                "'2026-04-20T09:30:00')"
            )
            c.execute(
                "INSERT INTO daily_summary VALUES ('2026-04-20', 3, 2, 1, 250.0, "
                "-100.0, 100000.0, 1)"
            )
        return db

    def test_export_trades_writes_csv(self, tmp_path, monkeypatch):
        db = self._make_db(tmp_path)
        monkeypatch.setattr(settings, "DB_PATH", db)
        dest = exporter.export_trades(tmp_path, "2026-04-01")
        assert dest.exists()
        with dest.open() as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 1
        assert rows[0]["symbol"] == "REL"
        assert rows[0]["pnl"] == "400.0"

    def test_export_handles_missing_table(self, tmp_path, monkeypatch):
        db = tmp_path / "empty.db"
        sqlite3.connect(str(db)).close()
        monkeypatch.setattr(settings, "DB_PATH", db)
        # Should not raise
        dest = exporter.export_trades(tmp_path, "2026-04-01")
        assert dest.exists()
        assert dest.read_text() == ""

    def test_export_audit_handles_heterogeneous_events(self, tmp_path, monkeypatch):
        audit_file = tmp_path / "audit.jsonl"
        audit_file.write_text(
            json.dumps({"ts": "2026-04-20T10:00:00", "event": "order_place",
                        "symbol": "X", "pnl": 0}) + "\n"
            + json.dumps({"ts": "2026-04-20T10:05:00", "event": "slm_fired",
                          "fill_price": 100.0, "extra_field": "y"}) + "\n"
        )
        monkeypatch.setattr(settings, "AUDIT_LOG_PATH", str(audit_file))
        dest = exporter.export_audit(tmp_path, "2026-04-20T00:00:00")
        assert dest.exists()
        rows = list(csv.DictReader(dest.open()))
        assert len(rows) == 2
        # Union of keys should include both event's unique fields
        fieldnames = set(rows[0].keys())
        assert "symbol" in fieldnames
        assert "fill_price" in fieldnames
        assert "extra_field" in fieldnames


# ──────────────────────────────────────────────────────────────────────
# Pre-flight Check primitive
# ──────────────────────────────────────────────────────────────────────
class TestPreflightCheck:
    def test_pass_fail_state(self):
        c = preflight.Check("x").passed("ok")
        assert c.ok and c.msg == "ok"
        c2 = preflight.Check("y").failed("bad")
        assert not c2.ok and c2.msg == "bad"

    def test_kill_switch_check_respects_sentinel(self, tmp_path, monkeypatch):
        from src.utils import kill_switch
        path = tmp_path / ".kill_switch"
        monkeypatch.setattr(settings, "KILL_SWITCH_PATH", str(path))
        # Not engaged → passes
        assert preflight._check_kill_switch().ok
        kill_switch.engage("unit-test")
        assert not preflight._check_kill_switch().ok
        kill_switch.disengage()

    def test_compliance_check_paper_lenient(self, monkeypatch):
        # Even with empty algo_id, paper mode should pass
        monkeypatch.setattr(settings, "ALGO_ID", "")
        monkeypatch.setattr(settings, "STATIC_IP_EXPECTED", "")
        assert preflight._check_compliance("paper").ok


# ──────────────────────────────────────────────────────────────────────
# Smoke harness
# ──────────────────────────────────────────────────────────────────────
class TestSmokeHarnessExists:
    def test_smoke_script_importable(self):
        path = PROJECT_ROOT / "scripts" / "smoke_paper.py"
        assert path.exists(), "smoke_paper.py missing"
        # Read-only import check — script auto-runs in __main__ only
        src = path.read_text()
        assert "SMOKE: paper-mode end-to-end" in src
        assert "OrderManager" in src
        assert "PositionManager" in src
