#!/usr/bin/env python3
"""
validate_plan.py
────────────────
JSON-Schema + business-rule validator for config/daily_plan.json.

Used in two places:
  1. Inside the Claude Routine, right before `git commit`, as a sanity gate.
  2. Inside the local bot at startup, before applying the plan.

Rules enforced beyond the schema:
  - date must be today (IST) or a configurable tolerance
  - risk_overrides never *loosen* settings.py caps
  - watchlist symbols pass the same regex as config.WATCHLIST

Exit code 0 = valid, 1 = invalid. Prints error lines to stderr.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

try:
    import jsonschema
except ImportError:
    jsonschema = None  # type: ignore

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "config" / "daily_plan.schema.json"

_SYMBOL_RE = re.compile(r"^[A-Z0-9&\-]{1,20}$")


def _load_settings_caps() -> dict[str, float]:
    """Read caps from config/settings.py without importing the full module
    (which would need Kite env vars). We grep the constants."""
    settings_file = REPO_ROOT / "config" / "settings.py"
    text = settings_file.read_text()
    caps: dict[str, float] = {}
    patterns = {
        "max_trades": r"^MAX_TRADES_PER_DAY\s*=\s*(\d+)",
        "risk_per_trade_pct": r"^RISK_PER_TRADE_PCT\s*=\s*([0-9.]+)",
        "max_open_positions": r"^MAX_OPEN_POSITIONS\s*=\s*(\d+)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, text, re.MULTILINE)
        if m:
            caps[key] = float(m.group(1))
    return caps


def validate(plan: dict[str, Any], *, today_override: str | None = None) -> list[str]:
    """Return list of error messages; empty list = valid."""
    errors: list[str] = []

    # ── JSON Schema ──
    if jsonschema is None:
        errors.append("jsonschema package not installed; cannot validate structure")
        return errors

    schema = json.loads(SCHEMA_PATH.read_text())
    try:
        jsonschema.validate(plan, schema)
    except jsonschema.ValidationError as e:
        errors.append(f"schema: {e.message} (at {'.'.join(str(p) for p in e.path)})")
        return errors  # Bail early — downstream checks assume schema is satisfied

    # ── Date ──
    today = today_override or str(date.today())
    if plan["date"] != today:
        # Allow tomorrow too (routine may fire just past midnight IST edge cases)
        tomorrow = str(date.today() + timedelta(days=1))
        if plan["date"] != tomorrow:
            errors.append(f"date: plan is for {plan['date']}, expected {today}")

    # ── Risk caps never loosened ──
    overrides = plan.get("risk_overrides") or {}
    caps = _load_settings_caps()
    for key, cap in caps.items():
        val = overrides.get(key)
        if val is None:
            continue
        if float(val) > cap:
            errors.append(
                f"risk_overrides.{key}={val} exceeds settings cap {cap}; "
                "plan may only tighten, never loosen"
            )

    # ── Symbols ──
    seen: set[str] = set()
    for item in plan["watchlist"]:
        sym = item["symbol"]
        if not _SYMBOL_RE.match(sym):
            errors.append(f"watchlist: invalid symbol {sym!r}")
        if sym in seen:
            errors.append(f"watchlist: duplicate symbol {sym}")
        seen.add(sym)

    # ── At least one tradeable symbol ──
    tradeable = [w for w in plan["watchlist"] if w["bias"] != "avoid"]
    if not tradeable:
        errors.append("watchlist: every symbol has bias='avoid'; nothing to trade")

    return errors


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("path", nargs="?",
                   default=str(REPO_ROOT / "config" / "daily_plan.json"),
                   help="Path to plan JSON (default: config/daily_plan.json)")
    p.add_argument("--today", help="Override today's date (YYYY-MM-DD) for testing")
    args = p.parse_args()

    plan_path = Path(args.path)
    if not plan_path.exists():
        print(f"ERROR: plan file not found: {plan_path}", file=sys.stderr)
        return 1

    try:
        plan = json.loads(plan_path.read_text())
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON in {plan_path}: {e}", file=sys.stderr)
        return 1

    errors = validate(plan, today_override=args.today)
    if errors:
        print(f"FAIL: {plan_path} has {len(errors)} error(s):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"OK: {plan_path} is valid (date={plan['date']}, "
          f"{len(plan['watchlist'])} symbols)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
