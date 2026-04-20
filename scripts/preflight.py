"""
Pre-Flight Check (Phase 5)
──────────────────────────
Go/no-go gate run immediately before starting the bot. Exits 0 only if
every check passes. Does NOT connect to the broker — those checks live
in main.setup() so they stay close to startup.

Checks:
    1. Market is open today (weekday + not in MARKET_HOLIDAYS).
    2. Python deps importable (kiteconnect, pandas_ta, backtesting).
    3. Required env vars present for current mode.
    4. Kill-switch not engaged.
    5. DB + log dirs writable.
    6. Full pytest suite passes (if --with-tests).
    7. Algo-ID + static-IP validate (paper-lenient, live-strict).

Usage:
    python scripts/preflight.py --mode paper
    python scripts/preflight.py --mode live --with-tests
"""

from __future__ import annotations

import argparse
import importlib
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings
from src.utils import kill_switch
from src.utils.compliance import (
    ComplianceError,
    validate_algo_id,
    validate_static_ip,
)


RED = "\033[91m"
GRN = "\033[92m"
YEL = "\033[93m"
END = "\033[0m"


class Check:
    def __init__(self, name: str):
        self.name = name
        self.ok = False
        self.msg = ""

    def passed(self, msg: str = "OK") -> "Check":
        self.ok = True
        self.msg = msg
        return self

    def failed(self, msg: str) -> "Check":
        self.ok = False
        self.msg = msg
        return self


def _check_market_open() -> Check:
    c = Check("market_open_today")
    return c.passed() if settings.is_market_day() else c.failed("Holiday or weekend")


def _check_imports() -> Check:
    c = Check("python_deps")
    # Hard requirements (runtime bot needs these)
    required = ("kiteconnect", "pandas", "pandas_ta", "numpy")
    missing = []
    for mod in required:
        try:
            importlib.import_module(mod)
        except Exception as e:
            missing.append(f"{mod} ({e.__class__.__name__})")
    if missing:
        return c.failed("missing: " + ", ".join(missing))
    # Soft (backtesting only needed for backtest scripts)
    try:
        importlib.import_module("backtesting")
    except Exception:
        return c.passed("runtime OK (backtesting absent — fine for paper/live)")
    return c.passed()


def _check_env(mode: str) -> Check:
    c = Check("env_vars")
    required = ["KITE_API_KEY", "KITE_API_SECRET", "KITE_USER_ID"]
    if mode == "live":
        required += ["KITE_TOTP_SECRET", "ALGO_ID"]
    missing = [k for k in required if not os.getenv(k) and not getattr(settings, k, "")]
    return c.failed("missing: " + ", ".join(missing)) if missing else c.passed()


def _check_kill_switch() -> Check:
    c = Check("kill_switch")
    if kill_switch.is_engaged():
        return c.failed(f"engaged: {kill_switch.reason() or '<no reason>'}")
    return c.passed()


def _check_writable() -> Check:
    c = Check("writable_dirs")
    errors = []
    for p in [settings.LOG_DIR, settings.TRADE_LOG_DIR, settings.DATA_DIR,
              Path(settings.DB_PATH).parent]:
        try:
            Path(p).mkdir(parents=True, exist_ok=True)
            t = Path(p) / ".preflight_write_test"
            t.write_text("ok")
            t.unlink()
        except Exception as e:
            errors.append(f"{p}: {e}")
    return c.failed("; ".join(errors)) if errors else c.passed()


def _check_compliance(mode: str) -> Check:
    c = Check("sebi_compliance")
    try:
        validate_algo_id(strict=(mode == "live"))
        validate_static_ip(strict=(mode == "live"))
        return c.passed()
    except ComplianceError as e:
        return c.failed(str(e))


def _check_tests() -> Check:
    c = Check("pytest_suite")
    try:
        r = subprocess.run(
            ["python3", "-m", "pytest", "tests/", "-q", "--tb=no"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if r.returncode == 0:
            return c.passed(r.stdout.strip().splitlines()[-1] if r.stdout else "OK")
        return c.failed(r.stdout.strip().splitlines()[-1] if r.stdout else "non-zero exit")
    except subprocess.TimeoutExpired:
        return c.failed("timeout after 300s")
    except Exception as e:
        return c.failed(str(e))


def _emit(c: Check) -> None:
    tag = f"{GRN}PASS{END}" if c.ok else f"{RED}FAIL{END}"
    print(f"  [{tag}] {c.name:<22} {c.msg}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["paper", "live"],
                    default=settings.TRADING_MODE)
    ap.add_argument("--with-tests", action="store_true",
                    help="Also run the full pytest suite")
    args = ap.parse_args()

    print(f"── PRE-FLIGHT ({args.mode.upper()}) ─────────────────────────")
    checks = [
        _check_market_open(),
        _check_imports(),
        _check_env(args.mode),
        _check_kill_switch(),
        _check_writable(),
        _check_compliance(args.mode),
    ]
    if args.with_tests:
        checks.append(_check_tests())

    for c in checks:
        _emit(c)

    all_ok = all(c.ok for c in checks)
    print("─" * 56)
    if all_ok:
        print(f"{GRN}GO — all checks passed.{END}")
        return 0
    print(f"{RED}NO-GO — fix the failing checks above before starting the bot.{END}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
