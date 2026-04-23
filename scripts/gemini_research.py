#!/usr/bin/env python3
"""
gemini_research.py
──────────────────
Uses Google Gemini (with grounding / search) to gather market research.
Called by both the local /pre-market command and the cloud premarket routine.

Usage:
  python scripts/gemini_research.py macro          # Global/macro overview
  python scripts/gemini_research.py stocks SYM1,SYM2,SYM3  # Per-stock news
  python scripts/gemini_research.py all SYM1,SYM2  # Both macro + stocks

Output: JSON on stdout. Cached to data/research/YYYY-MM-DD/<key>.json so
re-runs are cheap.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

CACHE_DIR = REPO_ROOT / "data" / "research"


def _today() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def _cache_path(key: str) -> Path:
    return CACHE_DIR / _today() / f"{key}.json"


def _read_cache(key: str) -> dict | None:
    p = _cache_path(key)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return None
    return None


def _write_cache(key: str, data: dict):
    p = _cache_path(key)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, default=str))


def _get_gemini_key() -> str:
    # Try .env first (local), then env var (cloud)
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        try:
            from dotenv import load_dotenv
            load_dotenv(REPO_ROOT / "config" / ".env")
            key = os.environ.get("GEMINI_API_KEY", "")
        except ImportError:
            pass
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set in env or config/.env")
    return key


def _call_gemini(prompt: str, key: str, retries: int = 2) -> str:
    """Call Gemini with Google Search grounding. Retries on 429 rate limits."""
    import random
    import time
    from google import genai
    from google.genai import errors as genai_errors
    from google.genai.types import GenerateContentConfig, Tool, GoogleSearch

    client = genai.Client(api_key=key)
    config = GenerateContentConfig(
        tools=[Tool(google_search=GoogleSearch())],
    )
    for attempt in range(retries + 1):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=config,
            )
            return response.text
        except genai_errors.ClientError as e:
            if e.code == 429 and attempt < retries:
                base_wait = 30 * (2 ** attempt)  # 30s, 60s
                jitter = random.uniform(0, base_wait * 0.3)
                wait = base_wait + jitter
                print(f"[gemini] Rate limited (429), waiting {wait:.0f}s before retry "
                      f"({attempt + 1}/{retries})...", file=sys.stderr)
                time.sleep(wait)
                continue
            raise


def research_macro(key: str) -> dict:
    """Global/macro research for Indian markets."""
    cached = _read_cache("macro")
    if cached:
        return cached

    today = _today()
    prompt = f"""You are a market research analyst for Indian stock markets (NSE/BSE).
Today is {today}. Provide a concise pre-market briefing covering:

1. **US markets overnight**: S&P 500 and Nasdaq closing levels and % change.
   Note if the move was broad-based or sector-concentrated.
2. **Asian markets**: SGX Nifty futures, Nikkei 225, Hang Seng — current levels
   and direction. This signals Indian market opening direction.
3. **USD/INR**: Current rate and recent move. A weaker rupee hurts importers
   but helps IT exporters (TCS, INFY, WIPRO).
4. **Crude oil (Brent)**: Current price. Rising oil is bearish for India
   (net importer). Affects ONGC, RELIANCE, and overall sentiment.
5. **Gold**: Current price. Big moves affect HDFC, jewelry stocks.
6. **India-specific**: Any RBI announcements, FII/DII flow data (yesterday),
   major earnings scheduled today, government policy news.
7. **Key risks**: Any geopolitical events, global macro surprises, or
   event risks that could cause volatility today.

For each data point, include the ACTUAL NUMBER (not just "up" or "down")
and explain WHY it matters for Indian markets in one sentence.

Keep the total response under 500 words. Use bullet points."""

    text = _call_gemini(prompt, key)
    result = {"date": today, "type": "macro", "content": text}
    _write_cache("macro", result)
    return result


def research_stocks(symbols: list[str], key: str) -> dict:
    """Per-stock news research."""
    cache_key = "stocks_" + hashlib.md5(",".join(sorted(symbols)).encode()).hexdigest()[:8]
    cached = _read_cache(cache_key)
    if cached:
        return cached

    today = _today()
    sym_list = ", ".join(symbols)
    prompt = f"""You are a market research analyst for Indian stock markets (NSE/BSE).
Today is {today}. For each of these stocks, find recent news (last 24-48 hours):

Stocks: {sym_list}

For EACH stock, provide:
1. **Recent news**: Earnings results, management changes, regulatory actions,
   sector developments, analyst upgrades/downgrades.
2. **Event risk**: Any binary events today (results announcement, court ruling,
   product launch, AGM). Flag these clearly — they create unpredictable moves.
3. **Sentiment**: Based on news flow, is sentiment positive/negative/neutral?
4. **Trading implication**: One sentence on whether this stock is tradeable
   today or should be avoided.

If no significant news exists for a stock, say "No material news" — don't
fabricate information.

Keep each stock's section to 3-4 bullet points. Be specific with numbers
and dates."""

    text = _call_gemini(prompt, key)
    result = {"date": today, "type": "stocks", "symbols": symbols, "content": text}
    _write_cache(cache_key, result)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Gemini-powered market research")
    ap.add_argument("mode", choices=["macro", "stocks", "all"],
                    help="Research mode")
    ap.add_argument("symbols", nargs="?", default="",
                    help="Comma-separated stock symbols (for stocks/all)")
    args = ap.parse_args()

    try:
        api_key = _get_gemini_key()
    except RuntimeError as e:
        json.dump({"error": str(e)}, sys.stdout)
        return 1

    output = {}

    if args.mode in ("macro", "all"):
        output["macro"] = research_macro(api_key)

    if args.mode in ("stocks", "all"):
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
        if not symbols:
            json.dump({"error": "No symbols provided for stock research"}, sys.stdout)
            return 1
        output["stocks"] = research_stocks(symbols, api_key)

    json.dump(output, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
