"""
Nightly CSV Export (Phase 5)
────────────────────────────
Exports trades + daily_summary to CSV for tax/audit/analysis. Also tails
the last N lines of the audit log into a dated CSV so every operational
artefact is reviewable from spreadsheets.

Usage:
    python scripts/export_nightly.py                # today
    python scripts/export_nightly.py --days 30      # last 30 days
    python scripts/export_nightly.py --out ./reports
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings


def _dict_rows(conn: sqlite3.Connection, sql: str, params: tuple) -> list[dict]:
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    except sqlite3.OperationalError:
        # Table missing — treat as empty (fresh install / first run).
        return []


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    # Union of keys across heterogeneous records (e.g., audit events).
    fields: list[str] = []
    seen: set[str] = set()
    for r in rows:
        for k in r.keys():
            if k not in seen:
                seen.add(k)
                fields.append(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def export_trades(out_dir: Path, since: str) -> Path:
    dest = out_dir / f"trades_since_{since}.csv"
    with sqlite3.connect(str(settings.DB_PATH)) as conn:
        rows = _dict_rows(
            conn,
            "SELECT * FROM trades WHERE date >= ? ORDER BY created_at",
            (since,),
        )
    _write_csv(dest, rows)
    return dest


def export_daily_summary(out_dir: Path, since: str) -> Path:
    dest = out_dir / f"daily_summary_since_{since}.csv"
    with sqlite3.connect(str(settings.DB_PATH)) as conn:
        rows = _dict_rows(
            conn,
            "SELECT * FROM daily_summary WHERE date >= ? ORDER BY date",
            (since,),
        )
    _write_csv(dest, rows)
    return dest


def export_audit(out_dir: Path, since_iso: str) -> Path:
    """Convert JSONL audit lines newer than since_iso into flat CSV."""
    dest = out_dir / f"audit_since_{since_iso[:10]}.csv"
    audit_path = Path(getattr(settings, "AUDIT_LOG_PATH", "") or
                       (settings.LOG_DIR / "audit" / "audit.jsonl"))
    if not audit_path.exists():
        dest.write_text("")
        return dest
    rows = []
    with audit_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("ts", "") >= since_iso:
                rows.append(rec)
    _write_csv(dest, rows)
    return dest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=1, help="Lookback window (days)")
    ap.add_argument("--out", type=str, default=None,
                    help="Output dir (default: <BASE_DIR>/logs/reports/<today>)")
    args = ap.parse_args()

    today = date.today()
    since_date = (today - timedelta(days=max(0, args.days - 1))).isoformat()
    since_iso = f"{since_date}T00:00:00"

    out_dir = Path(args.out) if args.out else (
        Path(settings.LOG_DIR) / "reports" / today.isoformat()
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    t = export_trades(out_dir, since_date)
    s = export_daily_summary(out_dir, since_date)
    a = export_audit(out_dir, since_iso)

    print(f"Exported to {out_dir}:")
    print(f"  trades:        {t.name}")
    print(f"  daily_summary: {s.name}")
    print(f"  audit:         {a.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
