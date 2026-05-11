"""
Allowlist / avoid-list enforcement in Runtime._scan_stocks.

Regression coverage for W19 finding #5: on May 8 2026, the scanner picked
BHARTIARTL (hard-avoid: insider window) and other plan-avoid symbols into
``todays_watchlist`` because the avoid filter was doc-only. These tests
lock the two enforcement gates:

  (a) static universe — symbol must be in settings.WATCHLIST
  (b) per-session avoid — drop bias=avoid symbols from any source
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings
from src.runtime.context import BotContext
from src.runtime.runtime import Runtime
from src.utils.plan_loader import DailyPlan


def _ctx_with_plan(plan: DailyPlan | None) -> BotContext:
    ctx = BotContext(mode="paper")
    ctx.daily_plan = plan
    return ctx


def _plan(watchlist: list[tuple[str, str]]) -> DailyPlan:
    """Build a DailyPlan from a list of (symbol, bias) pairs."""
    plan = DailyPlan(date="2026-05-11", version=1)
    for sym, bias in watchlist:
        plan.bias_by_symbol[sym] = bias
        plan.conviction_by_symbol[sym] = 3
        if bias != "avoid":
            plan.watchlist.append(sym)
    return plan


class TestPlanAvoidFilter:
    """Bias=avoid symbols must never reach todays_watchlist, regardless of source."""

    def test_plan_watchlist_excludes_avoid_symbol(self):
        plan = _plan([
            ("RELIANCE", "both"),
            ("TCS", "long"),
            ("BHARTIARTL", "avoid"),
        ])
        # plan_loader already excludes avoid from .watchlist, so this is the
        # baseline (no scanner involvement).
        ctx = _ctx_with_plan(plan)
        Runtime(ctx)._scan_stocks()
        assert "BHARTIARTL" not in ctx.todays_watchlist
        assert set(ctx.todays_watchlist) == {"RELIANCE", "TCS"}

    def test_scanner_output_filtered_against_plan_avoid(self, monkeypatch):
        """If the plan has empty watchlist but listed avoids, and scanner
        returns one of those avoids, it must still be dropped."""
        plan = _plan([("BHARTIARTL", "avoid"), ("PNB", "avoid")])
        # Empty plan.watchlist forces scanner fallback path
        plan.watchlist = []
        scanner = SimpleNamespace(scan=lambda: ["RELIANCE", "BHARTIARTL", "PNB", "TCS"])
        ctx = _ctx_with_plan(plan)
        ctx.scanner = scanner
        Runtime(ctx)._scan_stocks()
        assert "BHARTIARTL" not in ctx.todays_watchlist
        assert "PNB" not in ctx.todays_watchlist
        assert "RELIANCE" in ctx.todays_watchlist
        assert "TCS" in ctx.todays_watchlist


class TestStaticUniverseFilter:
    """Off-universe symbols (not in settings.WATCHLIST) must be dropped."""

    def test_off_universe_symbol_dropped_from_scanner(self):
        scanner = SimpleNamespace(scan=lambda: ["RELIANCE", "FAKESYMBOL", "TCS"])
        ctx = _ctx_with_plan(None)
        ctx.scanner = scanner
        Runtime(ctx)._scan_stocks()
        assert "FAKESYMBOL" not in ctx.todays_watchlist
        assert "RELIANCE" in ctx.todays_watchlist

    def test_off_universe_symbol_dropped_from_plan(self):
        """Even if a plan somehow lists an off-universe symbol (e.g. typo
        slipped past schema), the universe filter must still drop it."""
        plan = _plan([("RELIANCE", "both"), ("NOTREAL", "both")])
        ctx = _ctx_with_plan(plan)
        Runtime(ctx)._scan_stocks()
        assert "NOTREAL" not in ctx.todays_watchlist
        assert "RELIANCE" in ctx.todays_watchlist


class TestFallbackBehaviour:
    """No plan + no scanner → static fallback, still filtered."""

    def test_no_plan_no_scanner_uses_static(self):
        ctx = _ctx_with_plan(None)
        Runtime(ctx)._scan_stocks()
        assert len(ctx.todays_watchlist) > 0
        assert all(s in settings.WATCHLIST for s in ctx.todays_watchlist)

    def test_empty_after_filter_does_not_crash(self):
        """If every selected symbol is dropped, watchlist is empty (loop is
        then a no-op for the day) and we don't crash."""
        plan = _plan([
            ("BHARTIARTL", "avoid"),
            ("PNB", "avoid"),
        ])
        plan.watchlist = []  # nothing tradeable
        scanner = SimpleNamespace(scan=lambda: ["BHARTIARTL", "PNB"])
        ctx = _ctx_with_plan(plan)
        ctx.scanner = scanner
        Runtime(ctx)._scan_stocks()
        # static fallback kicks in when initial selection is empty, but those
        # entries should pass both gates (universe ok, no avoid match).
        for sym in ctx.todays_watchlist:
            assert sym in settings.WATCHLIST
            assert plan.bias_by_symbol.get(sym) != "avoid"


class TestMay8Regression:
    """Replays the exact May 8 2026 scenario from logs/journal/2026-05-08."""

    def test_may8_bharti_hard_block_held(self):
        # Plan that day hard-avoided BHARTIARTL (insider window pre-Q4)
        plan = _plan([
            ("TCS", "long"),
            ("HDFCBANK", "both"),
            ("BHARTIARTL", "avoid"),
            ("SBIN", "avoid"),
        ])
        # Scanner went rogue and picked the avoid symbols
        scanner = SimpleNamespace(scan=lambda: [
            "BHARTIARTL", "ADANIENT", "PNB", "ITC", "LT", "KOTAKBANK", "SBIN"
        ])
        ctx = _ctx_with_plan(plan)
        ctx.scanner = scanner
        Runtime(ctx)._scan_stocks()

        # Plan watchlist is non-empty, so plan source is used (not scanner).
        # Either way: BHARTIARTL and SBIN must be absent.
        assert "BHARTIARTL" not in ctx.todays_watchlist
        assert "SBIN" not in ctx.todays_watchlist
