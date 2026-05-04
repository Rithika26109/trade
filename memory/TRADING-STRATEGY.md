# Active Trading Strategy

Last updated: 2026-04-24

## Current Mode: PAPER

---

## Primary Strategy: Opening Range Breakout (ORB)

- **Timeframe:** 15-minute candles
- **Setup:** Wait for 9:15-9:30 opening range (high/low of first 15 min)
- **Entry LONG:** Price breaks above opening range high with volume confirmation
- **Entry SHORT:** Price breaks below opening range low with volume confirmation
- **Stop-loss:** Opposite end of the opening range
- **Targets:** 1R (1:1), 2R (1:2), 3R partial ladder
- **Win rate expectation:** 45-55%

## Secondary: RSI + EMA Crossover

- **Timeframe:** 5-minute candles
- **BUY:** 9 EMA crosses above 21 EMA, RSI 40-70, price above VWAP
- **SELL:** 9 EMA crosses below 21 EMA, RSI 30-60 **(HARD RULE: reject if RSI < 30 — oversold bounce risk)**, price below VWAP
- **Stop-loss:** 1.5x ATR from entry
- **Target:** 2x stop distance (1:2 R:R)

## Secondary: VWAP + Supertrend

- **Timeframe:** 5-minute candles
- **BUY:** Price above VWAP + Supertrend turns green
- **SELL:** Price below VWAP + Supertrend turns red
- **Stop-loss:** Supertrend line
- **Target:** 2x risk distance

---

## Risk Parameters

| Rule | Value |
|------|-------|
| Max risk per trade | 1% of capital |
| Max daily loss | 3% of capital |
| Max trades per day | 5 |
| Max open positions | 2 |
| Min risk/reward | 1:2 |
| Position sizing | `(Capital x 1%) / (Entry - SL)` |

## When NOT to Trade

- First 15 minutes after open (9:15-9:30) — building the ORB range
- Last 15 minutes before close (3:15-3:30) — bot squares off at 3:15
- India VIX > 25 (HIGH volatility regime)
- After 3 consecutive losses in a day
- Market holidays / truncated sessions
- Binary event stocks (results day, court rulings)

## Target Stocks

NIFTY 50 large-caps: RELIANCE, TCS, HDFCBANK, INFY, ICICIBANK, KOTAKBANK, HINDUNILVR, ITC, SBIN, BHARTIARTL, LT, AXISBANK, BAJFINANCE, MARUTI, WIPRO, TATAMOTORS

## Market Hours

- **NSE pre-open:** 9:00 - 9:15 AM IST
- **Market open:** 9:15 AM IST
- **Bot active:** 9:30 AM - 3:15 PM IST
- **Market close:** 3:30 PM IST

---

## Lessons Learned

_Updated by /weekly-review and /daily-summary commands. Most recent first._

- **#lesson 2026-04-24:** Exit events not written during EOD square-off — fix exit logger to fire on all exit paths (target, SL, EOD close), not just during active signal processing.
- **#lesson 2026-04-24:** Avoid shorting when RSI < 30 at entry. In STRONG_TREND_DOWN, wait for RSI to bounce to 40-50 before re-entering short — catching a pullback gives better R:R than chasing an already-oversold move.
- **#lesson 2026-04-24:** Track win rate by MULTI confirmation count (1 vs 2 vs 3 strategies agreeing). Hypothesis: 2+ confirmations should produce higher win rates. Data needed.
- **#lesson 2026-04-27:** Bot launched 3.5h late — check launchd job (`launchctl list | grep trade`, `cron_launch.log`) before each session. A missed morning means missed ORB setups.
- **#lesson 2026-04-27:** Premature EOD bug — bot called END OF DAY at 12:45 PM instead of 3:15 PM. Likely a timezone or startup-time comparison error. Add guard: `assert eod_time > now + 60min` on launch.
- **#lesson 2026-04-27:** No-trade days are correct behavior when all signals have R:R < 1.5 or only 1 strategy confirms. Do not force trades to have something to review.
- **#lesson 2026-04-29:** Premature EOD bug fired 3 times now (Apr 27, Apr 29 ×2). Highest-priority fix: bot calls EOD prematurely ~10:35 AM — likely startup-time comparison error. Root cause: bug from `improve exit timing` commit (943a95b). Investigate `wind-down` logic and EOD time calculation.
- **#lesson 2026-04-29:** Single-strategy confirmation (1 RSI_EMA) win rate = 40% across today's 5 trades. Target is 45-55%. Don't take trades with only 1 strategy confirming — require 2+ for entries.
- **#lesson 2026-04-29:** Avoid re-entering the same stock on the same day after a stop-loss hit unless conviction score is significantly higher. INDUSINDBK re-entry gained only Rs 7.77 and nearly stopped out again.
- **#lesson 2026-04-30:** ADANIENT was flagged as binary event (Q4 results) in pre-market but bot still entered. Add hard binary-event block in the scanner — flagged stocks must be excluded from symbol selection entirely, not just noted in the log.
- **#lesson 2026-04-30:** Partial quantity exits persist (21→13 for RELIANCE, 12→8 for ADANIENT). Investigate ladder/partial-exit logic in order_manager.py — ensure 100% of position closes on EOD square-off.
- **#lesson 2026-04-30:** A profitable day (66.7% win rate, +Rs 203) can still violate rules (single-strategy entries, binary event trade). Process matters more than one good outcome — rules exist to protect from bad-luck days, not just bad-skill days.
- **#lesson 2026-W18 (promoted):** Premature EOD bug recurred 3+ times across the week — kills every ORB setup. ORB is the *primary* strategy and saw zero trades all week. Fixing wind-down time comparison in commit 943a95b is the highest-leverage code change available.
- **#lesson 2026-W18 (promoted):** Documenting a rule is not enforcing it. The 2+ confirmation rule existed in docs after Apr 29 but was violated on 8/8 trades in the same week. Risk filters must reject at the order path, not the post-mortem.
- **#lesson 2026-W18 (promoted):** Pre-market regime is daily-anchored and missed 3/4 intraday reversals this week (25% accuracy). Either decouple intraday regime detection from daily bias, or treat the pre-market regime as one input among many rather than a directional commitment.
- **#lesson 2026-W18 (promoted):** Bias veto count was 0 across the entire week despite stocks that should have triggered it (ADANIENT binary event, INDUSINDBK re-entry). The veto mechanism is likely not wired into the order path — verify before next session.
