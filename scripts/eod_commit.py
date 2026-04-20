#!/usr/bin/env python3
"""
eod_commit.py
─────────────
Run by main.py in its finally/shutdown block (after _end_of_day). Writes a
metrics block into today's journal markdown, then commits + pushes so the
16:30 IST `eod-review` routine can read fresh events.

Idempotent — safe to call twice. No-ops if git is unavailable.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent
IST = ZoneInfo("Asia/Kolkata")
JOURNAL_DIR = REPO_ROOT / "logs" / "journal"


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(
            cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=30
        )
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as e:
        return 1, f"{type(e).__name__}: {e}"


def _load_events(date_str: str) -> list[dict]:
    events_path = JOURNAL_DIR / f"{date_str}.events.jsonl"
    if not events_path.exists():
        return []
    out: list[dict] = []
    for line in events_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _summarize(events: list[dict]) -> dict:
    entries = [e for e in events if e.get("type") == "entry"]
    exits = [e for e in events if e.get("type") == "exit"]
    vetoed = [e for e in events if e.get("type") == "skipped_due_to_bias"]
    pnls = [float(e.get("pnl", 0)) for e in exits if e.get("pnl") is not None]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    total_pnl = sum(pnls) if pnls else 0.0
    return {
        "trades": len(entries),
        "exits": len(exits),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (len(wins) / len(exits) * 100) if exits else 0.0,
        "total_pnl": total_pnl,
        "gross_profit": sum(wins) if wins else 0.0,
        "gross_loss": sum(losses) if losses else 0.0,
        "bias_vetoes": len(vetoed),
    }


def write_trading_day_section(date_str: str) -> Path:
    """Append a '## Trading Day' block to the day's journal with metrics."""
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    path = JOURNAL_DIR / f"{date_str}.md"
    events = _load_events(date_str)
    summary = _summarize(events)

    lines = [
        "",
        "## Trading Day",
        "",
        f"```yaml",
        f"date: {date_str}",
        f"trades: {summary['trades']}",
        f"exits: {summary['exits']}",
        f"wins: {summary['wins']}",
        f"losses: {summary['losses']}",
        f"win_rate_pct: {summary['win_rate']:.2f}",
        f"total_pnl: {summary['total_pnl']:.2f}",
        f"gross_profit: {summary['gross_profit']:.2f}",
        f"gross_loss: {summary['gross_loss']:.2f}",
        f"bias_vetoes: {summary['bias_vetoes']}",
        f"events_file: logs/journal/{date_str}.events.jsonl",
        f"```",
        "",
        "_Metrics above are auto-computed at EOD; post-market review follows._",
        "",
    ]

    existing = path.read_text() if path.exists() else f"# Journal — {date_str}\n"
    # Avoid duplicating the block if this script ran twice
    if "## Trading Day" in existing:
        return path
    path.write_text(existing + "\n".join(lines))
    return path


def git_commit_push(date_str: str, *, push: bool = True) -> int:
    rc, out = _run(["git", "rev-parse", "--is-inside-work-tree"])
    if rc != 0:
        print(f"[eod_commit] not a git repo, skipping: {out}", file=sys.stderr)
        return 0

    # Only stage journal + scan results — never config/secrets
    _run(["git", "add",
          f"logs/journal/{date_str}.md",
          f"logs/journal/{date_str}.events.jsonl"])

    rc, out = _run(["git", "diff", "--cached", "--quiet"])
    if rc == 0:
        print("[eod_commit] no staged changes")
        return 0

    rc, out = _run(["git", "commit", "-m", f"eod: {date_str}"])
    if rc != 0:
        print(f"[eod_commit] commit failed: {out}", file=sys.stderr)
        return rc

    if push:
        rc, out = _run(["git", "push"])
        if rc != 0:
            print(f"[eod_commit] push failed: {out}", file=sys.stderr)
            return rc

    print(f"[eod_commit] committed and pushed EOD for {date_str}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--date", help="Override date (YYYY-MM-DD)")
    p.add_argument("--no-push", action="store_true",
                   help="Commit but do not push (for local testing)")
    args = p.parse_args()

    date_str = args.date or datetime.now(IST).date().isoformat()
    write_trading_day_section(date_str)
    return git_commit_push(date_str, push=not args.no_push)


if __name__ == "__main__":
    sys.exit(main())
