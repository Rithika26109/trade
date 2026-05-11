# Active Trading Strategy

Last updated: 2026-05-11

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

Two columns: the **paper-mode** values currently enforced by `config/settings.py`, and the **live-mode target** values that must be in place before flipping `TRADING_MODE=live`. The `daily_plan.json` `risk_overrides` block can tighten these per session (typical: max_trades=3, risk=1.0%, max_open=2).

| Rule | Paper (enforced) | Live target | Code reference |
|------|------------------|-------------|----------------|
| Max risk per trade | 3.0% | 0.5% | `RISK_PER_TRADE_PCT` |
| Max daily loss | 3.0% | 2.0% | `MAX_DAILY_LOSS_PCT` |
| Max trades per day | 7 | 5 | `MAX_TRADES_PER_DAY` |
| Max open positions | 4 | 2 | `MAX_OPEN_POSITIONS` |
| Min risk/reward (net of costs) | 1.5 | 1.5 | `MIN_RISK_REWARD_RATIO` |
| Target risk/reward | 2.0 | 2.0 | `TARGET_RISK_REWARD_RATIO` |
| Max position size (% of capital) | 40% | 40% | `MAX_POSITION_PCT` |
| Consecutive-loss pause | 2 losses → 10 min | 2 losses → 10 min | `MAX_CONSECUTIVE_LOSSES` |
| Min strategy confirmations | 2 | 2 | `MIN_CONFIRMATIONS` |
| Single-strategy bypass (high conviction) | score ≥ 60 | score ≥ 60 | `HIGH_CONVICTION_SCORE` |
| Stopped-symbol cooldown (same-day SL) | on | on | `STOPPED_SYMBOL_COOLDOWN` |
| Position sizing | `(Capital × risk_pct) / (Entry − SL)` | same | `src/risk/risk_manager.py` |

## When NOT to Trade

- First 15 minutes after open (9:15-9:30) — building the ORB range
- Last 15 minutes before close (3:15-3:30) — bot squares off at 3:15
- India VIX > 25 (HIGH volatility regime)
- After 3 consecutive losses in a day
- Market holidays / truncated sessions
- Binary event stocks (results day, court rulings)

## Target Stocks

Source of truth: `config/settings.py:WATCHLIST` (currently 24 names). Filtered each session by the scanner (`SCANNER_TOP_N`) and the daily plan's `watchlist` / `avoid` entries.

- **Large-cap (NIFTY 50 core):** RELIANCE, TCS, HDFCBANK, INFY, ICICIBANK, SBIN, BHARTIARTL, ITC, KOTAKBANK, LT
- **Sector diversifiers:** AXISBANK, HINDUNILVR, HCLTECH, SUNPHARMA
- **Mid-cap (F&O eligible, high intraday volume):** TATASTEEL, TATAPOWER, PNB, ADANIENT, BANKBARODA, INDUSINDBK, DLF, BPCL, SAIL, ETERNAL

Note: `PNB` and `ETERNAL` are mid-caps outside the strict NIFTY 50 set — they are eligible only when a daily plan explicitly includes them (per #lesson 2026-05-05).

## Market Hours

- **NSE pre-open:** 9:00 – 9:15 AM IST
- **Market open:** 9:15 AM IST
- **Bot launch (launchd):** 9:05 AM IST — sets up state, opens WebSocket/poller, ready for 9:15 ORB window
- **Bot active trading window:** 9:15 AM – 3:15 PM IST
- **Wind-down / no new entries:** 3:00 – 3:15 PM IST
- **EOD square-off:** 3:15 PM IST
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
- **#lesson 2026-05-04:** ADANIENT SL gapped through by Rs 18/share (SL at 2474.8, exit at 2456.7 = Rs 304 extra loss). Post-earnings volatile stocks have wide spreads and gap-through risk. Wide ORB flag (>2%) should auto-exclude a stock from entry, not just log it.
- **#lesson 2026-05-04:** Re-entry on same stock after SL hit occurred again (ADANIENT BUY #1 SL → ADANIENT BUY #2 re-entry 2.5h later). Same stock, same day, same outcome. Veto is NOT enforced in code — add `already_stopped_today` set check in order_manager.py before entry.
- **#lesson 2026-05-04:** All 3 rule-violating trades (single-strategy) lost or barely broke even. The only 2-strategy confirmed trade (ITC SELL: ORB + VWAP_ST) was profitable. Pattern now confirmed across 4 consecutive sessions — 2+ confirmation rule must be enforced at order path, not just documented.
- **#lesson 2026-05-05:** PNB traded 3 consecutive times (all SL hits). `already_stopped_today` set still not in code after 4 sessions of the same lesson. Add to `order_manager.py` before any new feature work — blocks same-stock re-entry after SL hit on the same day.
- **#lesson 2026-05-05:** PNB is not in the defined NIFTY 50 target universe. The scanner is selecting stocks outside the allowlist. Add explicit allowlist filter in orchestrator/scanner so only stocks defined in `config/settings.py` are eligible for entry.
- **#lesson 2026-05-05:** Orphaned position from Apr 24 (TCS qty=12, lost during restart) appeared in today's EOD square-off. On startup, bot must reconcile broker positions vs. internal state rather than assuming a clean slate.
- **#lesson 2026-05-07:** High-score bypass loophole — single-strategy entries leaked through `MIN_CONFIRMATIONS=2` because the `HIGH_CONVICTION_SCORE` escape hatch fired. Every entry must clear MIN_CONFIRMATIONS=2 regardless of score; if you keep the bypass, raise the threshold high enough that it cannot fire on normal tape (or just delete it).
- **#lesson 2026-05-07:** SGX gap framing can fade — re-evaluate regime at 09:45. If NIFTY is within 0.3% of prior close by then, demote any directional regime call to RANGING and tighten further.
- **#lesson 2026-05-08:** Bias-invalidation conditions written in `daily_plan.json` (e.g. "invalidates if breaks below VWAP through 09:45") are not executed in bot runtime. Same non-execution pattern fired for TATAPOWER on May 6 (×13 vetoes) and TCS + HDFCBANK on May 8. Third recurrence — code fix in `plan_loader.py` / orchestrator is now the highest-leverage change after the partial-exit bug.
- **#lesson 2026-05-08:** Even on a 'long' IT tailwind day, individual stocks can break VWAP and stay there if sector noise (SBI Q4 day) suppresses the whole tape. Prefer `bias: both` for all names except the highest-conviction directional setups (conviction 5+), or apply a mandatory bias-flip when VWAP breaks by 09:45.
- **#lesson 2026-05-11:** `HIGH_CONVICTION_SCORE=80` made the single-strategy bypass effectively unreachable — 96 (Fri) + 75 (Mon) signal rejections, best score was 79. Lowered to 60 so realistic confluence scores can clear the gate while still filtering noise. Pair this with a hard rule that the bypass never fires when an obvious code error silently disables a strategy (see next).
- **#lesson 2026-05-11:** `RSI_EMA` crashed mid-session on 6 symbols (`'<=' not supported between float and NoneType`) and the exception was swallowed in the orchestrator at DEBUG level, silently dropping a confluence vote. Strategy errors now coerce to float and HOLD on `None`; consider promoting any strategy exception above DEBUG so a single broken strategy doesn't masquerade as "no signal".
- **#lesson 2026-W19 (promoted):** Pre-market `long`/`short` bias contradicted intraday tape on 3 sessions (TATAPOWER May 6 — 13 SELL signals blocked; TCS + HDFCBANK May 8 — 5 SELL signals blocked). Default to `bias: both` unless catalyst is robust to intraday price action. Reserve directional bias for confirmed multi-day trends, just-resolved binaries, or extreme sector dislocation.
- **#lesson 2026-W19 (promoted):** High-score bypass loophole let 1-strategy entries through MIN_CONFIRMATIONS gate twice (SUNPHARMA May 6, INFY May 7 — both lost). The 2+ confirmation rule must apply unconditionally, regardless of score.
- **#lesson 2026-W19 (promoted):** Banking-cluster Q4 days (May 5 LT/PNB, May 8 SBI/BoB) leak volatility to neighbours with no event of their own. On big-bank-print days, keep at most one bank in the watchlist with `both` bias.
- **#lesson 2026-W19 (promoted):** Partial-qty EOD square-off recurred 4× this week (HDFCBANK 50/51 May 6, 8/44 May 7, SUNPHARMA 6/11 May 6, RELIANCE 27→17 May 5). True position P&L is unknown when most shares orphan overnight in paper mode — fix `order_manager.py` before adding any new feature.
