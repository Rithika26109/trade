"""
Kill-Switch (Phase 4)
─────────────────────
File-based emergency halt. If a sentinel file exists at the configured
path, the bot must:
    1. Stop opening NEW positions immediately.
    2. Attempt to flat all open positions via `force_close_all`.
    3. Cancel any standing SLMs.
    4. Exit with a non-zero status.

Operator flow:
    touch .kill_switch    # halts bot within one cycle
    rm .kill_switch       # resets (bot must be restarted manually)
"""

from __future__ import annotations

from pathlib import Path

from config import settings


def _path() -> Path:
    override = getattr(settings, "KILL_SWITCH_PATH", None)
    if override:
        return Path(override)
    return Path(settings.BASE_DIR) / ".kill_switch" if hasattr(settings, "BASE_DIR") else Path(".kill_switch")


def is_engaged() -> bool:
    return _path().exists()


def engage(reason: str = "manual") -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(reason, encoding="utf-8")


def disengage() -> None:
    try:
        _path().unlink(missing_ok=True)
    except Exception:
        pass


def reason() -> str:
    try:
        return _path().read_text(encoding="utf-8").strip()
    except Exception:
        return ""
