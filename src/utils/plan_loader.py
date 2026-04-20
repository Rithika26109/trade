"""
src/utils/plan_loader.py
────────────────────────
Loads config/daily_plan.json (produced by the pre-market Claude Routine),
validates it, and applies it to the running bot.

Safe by design:
  - If the plan is missing, stale, or invalid → log a WARN and fall through
    to the bot's default behaviour (static WATCHLIST). Never crashes main.py.
  - Risk overrides are CLAMPED to the caps in config/settings.py. A plan
    can only TIGHTEN; it can never loosen. The validator script also
    enforces this, but this is defence in depth.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config import settings
from src.utils.logger import logger

PLAN_PATH: Path = settings.BASE_DIR / "config" / "daily_plan.json"

_VALID_BIAS = {"long", "short", "both", "avoid"}


@dataclass
class DailyPlan:
    """Parsed and applied version of config/daily_plan.json."""
    date: str
    version: int
    watchlist: list[str] = field(default_factory=list)           # tradeable only (bias != avoid)
    bias_by_symbol: dict[str, str] = field(default_factory=dict)  # includes avoid
    conviction_by_symbol: dict[str, int] = field(default_factory=dict)
    notes_by_symbol: dict[str, str] = field(default_factory=dict)
    regime_hint: dict[str, Any] = field(default_factory=dict)
    risk_overrides: dict[str, float] = field(default_factory=dict)  # clamped
    rationale: str = ""
    lessons_applied: list[str] = field(default_factory=list)
    source_path: str = ""

    def get_bias(self, symbol: str) -> str:
        return self.bias_by_symbol.get(symbol, "both")

    def allows_direction(self, symbol: str, direction: str) -> bool:
        """direction ∈ {'BUY','SELL'}. Matches against per-symbol bias."""
        bias = self.get_bias(symbol)
        if bias == "avoid":
            return False
        if bias == "both":
            return True
        if bias == "long":
            return direction == "BUY"
        if bias == "short":
            return direction == "SELL"
        return True  # unknown bias → permissive fallback


def load_plan(path: Path | None = None) -> DailyPlan | None:
    """Read, validate, and clamp today's plan. Returns None on any failure."""
    plan_path = path or PLAN_PATH
    if not plan_path.exists():
        logger.info(f"[PLAN] No daily plan at {plan_path} — using static WATCHLIST.")
        return None

    try:
        raw = json.loads(plan_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"[PLAN] Could not parse {plan_path}: {e} — using static WATCHLIST.")
        return None

    # ── Basic shape checks (mirror the schema's required fields) ──
    try:
        date_ = str(raw["date"])
        version = int(raw.get("version", 1))
        wl = raw["watchlist"]
        if not isinstance(wl, list) or not wl:
            raise ValueError("watchlist must be a non-empty list")
        if len(wl) > 10:
            raise ValueError(f"watchlist has {len(wl)} entries (max 10)")
    except Exception as e:
        logger.warning(f"[PLAN] Schema shape invalid: {e} — ignoring plan.")
        return None

    today = settings.now_ist().date().isoformat()
    if date_ != today:
        logger.warning(
            f"[PLAN] Plan is dated {date_}, today is {today} — ignoring stale plan."
        )
        return None

    # ── Build DailyPlan, skipping malformed entries rather than failing whole plan ──
    plan = DailyPlan(date=date_, version=version, source_path=str(plan_path))
    for item in wl:
        try:
            sym = str(item["symbol"]).upper()
            bias = str(item.get("bias", "both")).lower()
            if bias not in _VALID_BIAS:
                logger.warning(f"[PLAN] {sym}: unknown bias {bias!r}; defaulting to 'both'.")
                bias = "both"
            plan.bias_by_symbol[sym] = bias
            plan.conviction_by_symbol[sym] = int(item.get("conviction", 3))
            notes = item.get("notes")
            if notes:
                plan.notes_by_symbol[sym] = str(notes)
            if bias != "avoid":
                plan.watchlist.append(sym)
        except Exception as e:
            logger.warning(f"[PLAN] Skipping malformed watchlist entry {item!r}: {e}")

    if not plan.watchlist:
        logger.warning("[PLAN] No tradeable symbols after filtering — ignoring plan.")
        return None

    # ── Clamp risk overrides to settings caps. NEVER loosen. ──
    raw_overrides = raw.get("risk_overrides") or {}
    if isinstance(raw_overrides, dict):
        caps = {
            "max_trades": settings.MAX_TRADES_PER_DAY,
            "risk_per_trade_pct": settings.RISK_PER_TRADE_PCT,
            "max_open_positions": settings.MAX_OPEN_POSITIONS,
        }
        for key, cap in caps.items():
            val = raw_overrides.get(key)
            if val is None:
                continue
            try:
                v = float(val)
            except (TypeError, ValueError):
                continue
            if v <= 0:
                continue  # disallow zero/neg — would make bot inert
            if v > cap:
                logger.warning(
                    f"[PLAN] Clamping risk_overrides.{key}={v} down to settings cap {cap}"
                )
                v = cap
            plan.risk_overrides[key] = v

    plan.regime_hint = raw.get("regime_hint") or {}
    plan.rationale = str(raw.get("rationale") or "")
    plan.lessons_applied = [str(x) for x in (raw.get("lessons_applied") or [])]

    logger.success(
        f"[PLAN] Loaded {plan_path.name}: "
        f"{len(plan.watchlist)} tradeable symbol(s), "
        f"{sum(1 for b in plan.bias_by_symbol.values() if b == 'avoid')} avoid, "
        f"overrides={plan.risk_overrides or 'none'}"
    )
    return plan


def git_pull() -> bool:
    """Best-effort `git pull --ff-only` with a short timeout. Returns success.

    Non-fatal: a pull failure (network, conflict) just means we use whatever
    plan is already on disk — or fall back to static WATCHLIST if that's
    missing too. Never raises.
    """
    import subprocess
    try:
        p = subprocess.run(
            ["git", "-C", str(settings.BASE_DIR), "pull", "--ff-only"],
            capture_output=True, text=True, timeout=15,
        )
        if p.returncode == 0:
            tail = (p.stdout or p.stderr).strip().splitlines()[-1:] or ["(up to date)"]
            logger.info(f"[PLAN] git pull: {tail[0]}")
            return True
        logger.warning(f"[PLAN] git pull non-zero: {p.stderr.strip()}")
        return False
    except Exception as e:
        logger.warning(f"[PLAN] git pull skipped ({type(e).__name__}: {e})")
        return False
