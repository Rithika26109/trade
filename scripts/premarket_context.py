#!/usr/bin/env python3
"""
premarket_context.py
────────────────────
Headless pre-market data collector. Invoked by the Claude Routine
(`premarket-plan`) before it picks the day's watchlist.

Emits a single JSON blob on stdout:
  {
    "date": "YYYY-MM-DD",
    "now_ist": "...",
    "nifty": { regime, atr_pct, close, change_pct },
    "vix": { level, regime },
    "scanner": [ { symbol, score, price, volume_score, momentum_score, rs_score,
                   volatility_score, sector, gap_pct }, ... up to 20 ],
    "positions_snapshot": { ... from Kite, empty if auth failed },
    "errors": [ ... ]
  }

Never raises — always exits 0 with whatever context it could gather.
The routine is expected to handle missing fields gracefully in its prompt.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Make sure repo root is importable
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

IST = ZoneInfo("Asia/Kolkata")


def _safe(fn, *, default=None, errors: list[str], label: str):
    try:
        return fn()
    except Exception as e:
        errors.append(f"{label}: {type(e).__name__}: {e}")
        return default


def _scanner_payload(scanner, errors: list[str], limit: int = 20) -> list[dict]:
    """Run StockScanner but short-circuit the top-N cut so the routine sees
    a wider pool (it'll pick its own 5-10 from this)."""
    from config import settings  # noqa: WPS433

    original_top_n = getattr(settings, "SCANNER_TOP_N", 0)
    try:
        settings.SCANNER_TOP_N = 0  # disable cap — we want the full ranked list
        scanner.scan()  # populates internal state but doesn't return scores
    except Exception as e:
        errors.append(f"scanner.scan: {type(e).__name__}: {e}")
    finally:
        settings.SCANNER_TOP_N = original_top_n

    # Re-run the scoring to retrieve full dict objects (scan() returns symbols only)
    watchlist = getattr(settings, "WATCHLIST", [])
    out: list[dict] = []
    for symbol in watchlist:
        try:
            result = scanner._score_stock(symbol)
            if result is None:
                continue
            result["total_score"] = scanner._composite_score(result)
            out.append(result)
        except Exception as e:
            errors.append(f"scanner._score_stock({symbol}): {type(e).__name__}: {e}")
    out.sort(key=lambda x: x.get("total_score", 0), reverse=True)
    return out[:limit]


def build_context() -> dict:
    errors: list[str] = []
    now = datetime.now(IST)
    ctx: dict = {
        "date": now.date().isoformat(),
        "now_ist": now.isoformat(),
        "nifty": None,
        "vix": None,
        "scanner": [],
        "positions_snapshot": {},
        "errors": errors,
    }

    # ── Lazy imports so a missing dep doesn't kill the whole script ──
    try:
        from src.auth.login import ZerodhaAuth
        from src.data.market_data import MarketData
        from src.scanner.stock_scanner import StockScanner
        from src.indicators.indicators import add_all_indicators
        from src.indicators.market_regime import detect_regime, detect_volatility_regime
    except Exception as e:
        errors.append(f"imports: {type(e).__name__}: {e}")
        return ctx

    # ── Kite auth (uses cached token; routine should have KITE_ACCESS_TOKEN env) ──
    kite = None
    try:
        # If the routine set KITE_ACCESS_TOKEN directly, bypass the TOTP flow.
        # Token is an enctoken (from refresh_kite_token.py), needs /oms endpoints.
        access_token = os.environ.get("KITE_ACCESS_TOKEN")
        if access_token:
            from src.auth.login import _make_enctoken_kite
            kite = _make_enctoken_kite(access_token)
            kite.profile()  # verify
        else:
            auth = ZerodhaAuth()
            kite = auth.login()
    except Exception as e:
        errors.append(f"auth: {type(e).__name__}: {e}")
        kite = None

    if kite is None:
        return ctx

    market_data = _safe(lambda: MarketData(kite), errors=errors, label="MarketData")
    if market_data is None:
        return ctx
    _safe(lambda: market_data.load_instruments("NSE"),
          errors=errors, label="load_instruments")

    # ── NIFTY regime ──
    try:
        nifty_df = market_data.get_historical_data("NIFTY 50", interval="day", days=60)
        if nifty_df is not None and not nifty_df.empty and len(nifty_df) >= 20:
            nifty_df = add_all_indicators(nifty_df)
            regime = detect_regime(nifty_df)
            vol_regime = detect_volatility_regime(nifty_df)
            close = float(nifty_df["close"].iloc[-1])
            prev = float(nifty_df["close"].iloc[-2])
            atr_pct = None
            if "atr" in nifty_df.columns and close:
                atr_pct = float(nifty_df["atr"].iloc[-1]) / close * 100
            ctx["nifty"] = {
                "close": close,
                "change_pct": (close - prev) / prev * 100 if prev else None,
                "regime": regime.value if regime else "UNKNOWN",
                "vol_regime": vol_regime.value if vol_regime else "NORMAL",
                "atr_pct": atr_pct,
            }
    except Exception as e:
        errors.append(f"nifty_regime: {type(e).__name__}: {e}")

    # ── India VIX ──
    try:
        vix_map = market_data.get_ltp(["INDIA VIX"], exchange="NSE")
        vix = vix_map.get("INDIA VIX") if isinstance(vix_map, dict) else None
        if vix is not None:
            from config import settings
            level = float(vix)
            if level < settings.VIX_LOW:
                vr = "LOW"
            elif level > settings.VIX_EXTREME:
                vr = "EXTREME"
            elif level > settings.VIX_HIGH:
                vr = "HIGH"
            else:
                vr = "NORMAL"
            ctx["vix"] = {"level": level, "regime": vr}
    except Exception as e:
        errors.append(f"vix: {type(e).__name__}: {e}")

    # ── Scanner ──
    try:
        scanner = StockScanner(market_data)
        ctx["scanner"] = _scanner_payload(scanner, errors, limit=20)
    except Exception as e:
        errors.append(f"scanner_init: {type(e).__name__}: {e}")

    # ── Positions snapshot (helps routine see overnight carry, if any) ──
    try:
        pos = kite.positions()
        if isinstance(pos, dict):
            ctx["positions_snapshot"] = {
                "net": pos.get("net", []),
                "day": pos.get("day", []),
            }
    except Exception as e:
        errors.append(f"positions: {type(e).__name__}: {e}")

    return ctx


def main() -> int:
    try:
        ctx = build_context()
    except Exception:
        # Absolute last-resort: dump a JSON with the traceback and exit 0
        # so the routine can still proceed on what it has.
        ctx = {
            "date": datetime.now(IST).date().isoformat(),
            "fatal_error": traceback.format_exc(),
            "scanner": [],
            "errors": ["fatal exception — see fatal_error field"],
        }
    json.dump(ctx, sys.stdout, default=str, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
