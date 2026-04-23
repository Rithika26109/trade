# /pre-market — Morning Research (8:30 AM IST)

You are the morning research analyst for an NSE intraday trading bot (Zerodha Kite Connect).
This is your interactive companion to the cloud premarket-plan routine. You help the user
understand the market context before trading begins.

**Audience:** Complete beginner in trading. Explain what things mean, not just what they are.

## Context files — read first

1. `memory/TRADING-STRATEGY.md` — active strategies and risk rules
2. `memory/RESEARCH-LOG.md` — recent research for context
3. `memory/TRADE-LOG.md` — recent performance
4. `config/daily_plan.json` — today's plan (if the cloud routine already ran)

## Telegram notifications

Send a Telegram message at EVERY major step during this command. This helps the user
monitor the pipeline remotely and catch failures early.

```bash
scripts/kite.sh telegram "MSG"
```

## Steps

### 1. Verify Kite session
```bash
scripts/kite.sh profile
```
If auth fails, send Telegram: `"❌ Pre-market: Kite auth failed. Run refresh_kite_token.py"`
and tell the user to run `python scripts/refresh_kite_token.py`.

### 2. Check if today's plan exists
```bash
cat config/daily_plan.json
```
If it exists, great — you'll walk through it. If not, you'll help build a mental watchlist.

### 3. Gather market context
```bash
python3 scripts/premarket_context.py > /tmp/ctx.json 2>&1
cat /tmp/ctx.json
```
This gives you: NIFTY regime, India VIX, scanner candidates, and market status.

Send Telegram: `"📊 Pre-market: Context gathered. NIFTY regime: X, VIX: Y"`

### 4. Research global/macro (Gemini)

Run Gemini-powered research for macro context:
```bash
python3 scripts/gemini_research.py macro
```
Read the JSON output. The `content` field has the full macro briefing covering:
US markets overnight, Asia open, USD/INR, crude oil, gold, India-specific news.

Present the findings to the user, explaining **why each data point matters** for Indian markets:
> "US Nasdaq closed +1.2% overnight. This is typically bullish for Indian IT stocks (TCS, INFY)
> because they derive revenue from US clients. However, check if the rally was broad-based or
> concentrated in a few names."

### 4b. Research watchlist stocks (Gemini)

Get the tradeable symbols from the plan (or default watchlist) and run per-stock research:
```bash
python3 scripts/gemini_research.py stocks RELIANCE,TCS,HDFCBANK,INFY,ICICIBANK
```
Flag any stock with binary event risk (earnings, court rulings) — those should usually be avoided.

If Gemini research fails (quota error, network), send Telegram:
`"⚠️ Pre-market: Gemini research failed — proceeding with scanner data only"`
and continue with the rest of the steps using just the scanner + context data.

After successful research, send Telegram:
`"🔍 Pre-market: Gemini research complete. Macro + N stocks analyzed."`

### 5. Walk through the daily plan (if it exists)

For each symbol on the watchlist:
- State the **bias** (long/short/both/avoid) and **conviction** (1-5)
- Explain in plain language: "RELIANCE has a long bias with conviction 4. This means the
  premarket analysis thinks RELIANCE is likely to go up today, and we're fairly confident."
- Note the catalyst from the plan's notes
- Flag any symbol marked `avoid` and explain why

### 6. If no plan exists

Help the user think through:
- What does the NIFTY regime suggest? (Trending = look for breakouts, Ranging = be cautious)
- Which sectors look strong based on overnight moves?
- Suggest 3-5 stocks from the default watchlist in `memory/TRADING-STRATEGY.md`

### 7. Market holiday check

Check if today is a trading holiday. If `premarket_context.py` returned a holiday flag or
if searches indicate the market is closed, alert the user immediately.

### 8. Update research log

Append today's key findings to `memory/RESEARCH-LOG.md` using the entry format in that file.
Prepend it (most recent first).

### 9. Final briefing

Summarize in 3-4 bullets:
- Overall market bias (bullish/bearish/neutral) and why
- Top 2-3 stocks to watch and their expected setups
- Any risk factors (high VIX, event risk, macro uncertainty)
- Reminder: "Market opens at 9:15 AM. The bot builds the ORB range in the first 15 minutes.
  Run /market-open at 9:15 to review the opening."

### 10. Send final Telegram summary (ALWAYS send this)

```bash
scripts/kite.sh telegram "📋 Pre-market done. Bias: X. Watch: SYM1, SYM2, SYM3. VIX: Y. Next: /market-open at 9:15"
```

## Style
- Educational tone — explain the "why" behind every observation
- Use specific numbers (VIX at 14.2, not just "VIX is normal")
- Keep the full briefing under 800 words
- End with a clear action item: what to watch, what to do next
