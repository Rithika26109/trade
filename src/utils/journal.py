"""
src/utils/journal.py
────────────────────
Thin helpers for the Claude-Routines integration:
  - emit_event(): append a JSONL line to logs/journal/YYYY-MM-DD.events.jsonl
  - append_section(): append a markdown section to today's journal

The routines (pre-market, EOD review, weekly meta) consume these files. The
bot produces the events file during the trading day and relies on
scripts/eod_commit.py to append a metrics section and git push at EOD.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from config import settings

JOURNAL_DIR: Path = settings.BASE_DIR / "logs" / "journal"


def _today_str() -> str:
    return settings.now_ist().date().isoformat()


def _ensure_dir() -> None:
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)


def emit_event(event_type: str, **fields: Any) -> None:
    """Append a single JSONL event for today. Never raises — trading must not
    be blocked by a journal-write error."""
    try:
        _ensure_dir()
        event = {
            "ts": datetime.now(settings.IST).isoformat(timespec="seconds"),
            "type": event_type,
            **fields,
        }
        path = JOURNAL_DIR / f"{_today_str()}.events.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, default=str) + "\n")
    except Exception:
        # Logging failure must not propagate into the trading loop.
        pass


def append_section(heading: str, markdown: str) -> None:
    """Append a new section to today's journal. Idempotent per heading."""
    try:
        _ensure_dir()
        path = JOURNAL_DIR / f"{_today_str()}.md"
        existing = path.read_text(encoding="utf-8") if path.exists() else f"# Journal — {_today_str()}\n"
        if heading in existing:
            return
        new = existing.rstrip() + f"\n\n## {heading}\n\n{markdown.strip()}\n"
        path.write_text(new, encoding="utf-8")
    except Exception:
        pass
