# Trade Log

Running log of daily trade summaries. Most recent first. Older than 30 days gets archived to `logs/journal/`.

---

## 2026-05-13 (Wednesday) — EOD
- Regime: RANGING (NIFTY ~23,483, +0.44% intraday recovery vs -3.3% Mon-Tue) | VIX: 19.46 (NORMAL)
- Trades: 5 entries | Wins: 0 | Losses: 4 | Win Rate: 0% | P&L: -Rs 469.55
- Paper capital: ~Rs 97,422.25 (drawdown 2.58% from Rs 1,00,000 start)
- Key trades: BUY SAIL @184.33→183.20 -Rs 166.15 (SL, 1-strat VWAP_ST), SELL RELIANCE @1356.0→1360.70 -Rs 95.94 (SL, 1-strat ORB), SELL INFY @1130.5→1135.70 -Rs 136.96 (SL, 1-strat ORB), SELL HCLTECH @1143.2→1145.10 -Rs 70.50 (EOD, 1-strat ORB, partial exit 29/34 shares; duplicate entry bug fired)
- TATAPOWER correctly excluded (gap -6.55% > 2% wide-ORB threshold)
- Notes: All 4 trades were 1-strategy — HIGH_CONVICTION_SCORE bypass (≥60) still firing despite MIN_CONFIRMATIONS=2. 3 SELL entries taken against a recovering NIFTY tape (+0.44% intraday) — all stopped out. HCLTECH duplicate-entry bug (same signal fired 13:30 and 13:32) and partial-exit (29/34 shares) — large orphan position likely. No bias vetoes (all watchlist on `both` bias).

## 2026-05-13 (Wednesday) — Opening
- NIFTY prior close: 23,379.55 (RANGING, -1.83% Tue | 2-day -3.3%)
- Regime: RANGING/NORMAL flat open — SGX had hinted -0.23% gap-down; actual opens confirm flat/RANGING
- TATAPOWER: **-6.55% GAP DOWN** (391.00 open vs 418.40 prev close) — AUTO-EXCLUDE (>2% rule, plan warned "avoid if >2%"); also showing V-bounce recovery intraday (LTP 404)
- SAIL: flat open (+0.12%) but +4% intraday move in first 12 min — watch carefully, ORB may give breakout signal
- Other gaps: RELIANCE -0.19%, HDFCBANK +0.21%, ITC +0.43%, HCLTECH +0.04%, HINDUNILVR +0.13%, INFY -0.32% — all within noise
- Bot status: RUNNING ✓ — collecting ORB range 09:15-09:30, scanning starts 09:30
- Risk overrides: max_trades=3, risk=1.0%, max_open=2 (tightened given 2-day drawdown + Fed hawkish)
- Watchlist (8→7 effective): HDFCBANK, RELIANCE, SAIL, HINDUNILVR, ITC, HCLTECH, INFY (TATAPOWER excluded)

---

## 2026-05-12 (Tuesday) — Opening
- NIFTY prior close: 23,815.85 (RANGING, -1.49% Mon)
- Regime: RANGING/NORMAL | US CPI tonight (post-close, pre-print jitters)
- Key gaps: HDFCBANK -1.14%, RELIANCE -1.06%, SUNPHARMA -1.12%, INFY -0.27%, ITC -0.15%
- Hard avoids: TATAPOWER (Q4 results + analyst call today), BHARTIARTL (Q4 May 13 insider window), PNB (Q4 today + outside NIFTY50)
- Bot status: RUNNING — ORB collection 09:15-09:30
- Plan fix: daily_plan.json was stale (2026-05-11); applied 2026-05-12 plan from branch plan/2026-05-12
- Risk overrides: max_trades=3, risk=1.0%, max_open=2
- Watchlist (7): HDFCBANK, RELIANCE, ITC, SUNPHARMA, INFY, HCLTECH, HINDUNILVR — all `both` bias

---

## 2026-05-11 (Monday) — EOD
- Regime: TREND_DOWN (NIFTY ~23,932, -1.0% on day) | VIX: 18.29 (NORMAL)
- Trades: 0 signal trades | Wins: 0 | Losses: 0 | Win Rate: N/A
- P&L: Rs 0.00 (paper capital: ~Rs 97,891.80, unchanged)
- Key trades: None — 8 signals rejected by 2+ confirmation rule (INFY ORB ×1, HDFCBANK RSI_EMA ×4, RELIANCE ORB/RSI_EMA ×3). TCS orphan (10 shares) reconciled at breakeven (Rs 0).
- Notes: First full session with MIN_CONFIRMATIONS=2 enforced in code — all 8 rejections were clean, no bypass. BHARTIARTL hard block held (Q4 results tomorrow). Predicted TREND_DOWN regime was correct. No-trade day on pre-CPI + TREND_DOWN is correct behavior.

## 2026-05-11 (Monday) — Opening
- NIFTY prior close: 24,176.15 (TREND_DOWN, -0.62% Fri)
- Pre-market gaps: HDFCBANK -1.51%, AXISBANK -0.98%, RELIANCE -0.71%, TATAPOWER -0.26%, INFY -0.15%, ITC +0.49%, SUNPHARMA ~flat
- BHARTIARTL: HARD AVOID (Q4 results Wed May 13)
- Bot status: Running — ORB collection in progress (waiting for 09:30)
- India VIX: API down — using default sizing
- Risk overrides active: max_trades=3, risk_per_trade=1.0%, max_open_positions=2
- Regime note: Crude +3.5% (Brent ~$104.80), US CPI Tue May 12 (keep size small)

---

## 2026-05-08 (Friday) — EOD
- Regime: RANGING (NIFTY 24,195.1, -0.54%) | VIX: 17.04 (NORMAL)
- Trades: 0 | Wins: 0 | Losses: 0 | Win Rate: N/A
- P&L: Rs 0.00 (paper capital: ~Rs 98,213.13, unchanged)
- Key trades: None — 5 SELL signals (2× TCS, 3× HDFCBANK) blocked by long bias; all also single-strategy (1-strat) so 2+ rule would have rejected them too
- Notes: Bias invalidation bug fired third time — TCS "invalidates if breaks below VWAP through 09:45" condition met but bot never updated bias. Scanner selected wrong watchlist at open (BHARTIARTL, ADANIENT, PNB etc) but events file shows TCS/HDFCBANK signals from 10:00 AM — likely corrected after restart. Hard blocks (SBIN, BHARTIARTL) held correctly. Both avoids were right (SBI Q4 volatile; BHARTIARTL insider window).

## 2026-05-08 (Friday) — Opening
- NIFTY open: ~24,295 (gap-down ~0.13% from 24,326 prior close — mild, within noise)
- Regime: RANGING / NORMAL vol | Crude +2.1% (bearish macro) | USD/INR 95.16 (IT tailwind)
- Key gaps: No significant gaps (SGX Nifty -0.13%)
- Bot status: RUNNING (launched 09:05, collecting ORB range, waiting for 09:30)
- Positions at open: CLEAN (none)
- SCANNER ALERT: Bot selected wrong watchlist — BHARTIARTL (HARD BLOCK!), ADANIENT, PNB, ITC, LT, KOTAKBANK instead of daily_plan.json. Allowlist filter still not enforced in code.

---

## 2026-05-05 (Tuesday) — EOD
- Regime: TREND_DOWN (PNB bearish bias) | VIX: ~NORMAL
- Trades: 4 | Wins: 0 | Losses: 4 | Win Rate: 0%
- P&L: -Rs 1,153.77 (paper capital: Rs 98,172.97)
- Key trades: BUY RELIANCE @1464.4→1464.2 -Rs14.21 (EOD, 1-strat, 10 of 27 shares unaccounted), SELL PNB @107.79→108.16 -Rs101.06 (SL, 1-strat, ORB), SELL PNB re-entry @107.73→109.74 -Rs777.16 (SL gap-through, 2-strat ✓), SELL PNB re-entry #2 @107.45→108.07 -Rs261.34 (SL, 1-strat, 3rd consecutive SL)
- Notes: Worst day by P&L. PNB is outside the defined NIFTY 50 universe. 3 PNB re-entries on same stock violated Apr 29 + May 4 lessons. 1 orphaned TCS position (from Apr 24 restart) closed at breakeven today. Partial exit bug: 27→17 on RELIANCE. 3-consecutive-loss stop rule not triggered.

## 2026-05-05 (Tuesday) — Opening
- Watchlist: RELIANCE, ADANIENT, PNB, SBIN, INDUSINDBK
- Opening gaps: RELIANCE -0.48%, ADANIENT -0.12%, PNB -0.09%, SBIN -0.65%, INDUSINDBK -0.20%
- All stocks flat gap-down. No large gaps (> 2%). Market mildly weak at open.
- Bot status: RUNNING — launched 9:15:12, collecting ORB range, scan starts 9:30
- Flag: ADANIENT in watchlist again — had SL gap-through and re-entry violations on May 4. Watch closely.

---

## Entry Format

```
## YYYY-MM-DD (Day)
- Regime: TRENDING_UP/DOWN/RANGING | VIX: X.X (NORMAL/HIGH/LOW)
- Trades: N | Wins: N | Losses: N | Win Rate: X%
- P&L: +/- Rs X
- Key trades: SYMBOL direction +/-Rs X (strategy), ...
- Notes: One-line observation
```

---

## 2026-05-04 (Monday) — Opening
- NIFTY: no direct quote (enctoken auth limitation — using individual stock data)
- Key gaps: INDUSINDBK +1.00%, ITC +0.95% (gap-filling, LTP below prev close), ADANIENT -0.75% (wide ORB range Rs 2382–2457, post-earnings volatility), RELIANCE +0.18%, ICICIBANK +0.07%
- Bot status: Running (started 09:15:10, ORB window 09:15–09:30)
- Watchlist: INDUSINDBK, RELIANCE, ADANIENT, ICICIBANK, ITC
- Flags: ADANIENT wide range (3.1% ORB); ITC gap fade (opened up, reversed below prev close)

<!-- Daily summaries will be prepended here by /daily-summary and /market-open commands -->

## 2026-05-04 (Monday) — EOD
- Regime: STRONG_TREND_UP (ADANIENT) / TREND_DOWN (KOTAKBANK) | VIX: ~NORMAL
- Trades: 4 | Wins: 2 | Losses: 2 | Win Rate: 50%
- P&L: -Rs 685.47 (paper capital: Rs 99,326.74)
- Key trades: BUY ADANIENT @2508.1→2456.7 -Rs 803.51 (SL hit, slippage +Rs 304 beyond SL), SELL KOTAKBANK @373.7→371.85 +Rs 165.51 (EOD, RSI_EMA), SELL ITC @312.3→311.25 +Rs 115.51 (EOD, ORB+VWAP_ST ✓), BUY ADANIENT re-entry @2492.6→2483.9 -Rs 162.98 (EOD, VWAP_ST)
- Notes: Worst day yet. ADANIENT SL gapped through by Rs 18/share (SL 2474.8, exit 2456.7). Three of four entries violated the 2+ confirmation rule. Re-entry on ADANIENT after SL hit violated Apr 29 lesson. Only rule-following trade was ITC (2 confirmations) — profitable. Both wins via EOD square-off, not targets.

## 2026-05-01 (Friday) — MARKET HOLIDAY
- Regime: N/A (Maharashtra Day — NSE/BSE closed)
- Trades: 0 | Wins: 0 | Losses: 0 | Win Rate: N/A
- P&L: Rs 0.00 (paper capital unchanged: Rs 1,00,012.21)
- Key trades: None
- Notes: Bot launched at 09:18, correctly detected holiday and exited in <1s. Git pull at startup failed (503 tunnel) — non-blocking. Resume Fri 2026-05-02.

## 2026-04-30 (Thursday) — EOD
- Regime: TREND_UP (RELIANCE at BUY entry) | VIX: ~NORMAL
- Trades: 3 | Wins: 2 | Losses: 1 | Win Rate: 66.7%
- P&L: +Rs 203.36 (paper capital: Rs 1,00,012.21)
- Key trades: SELL RELIANCE @1407.9→1407.1 -Rs 9.34 (SL hit, VWAP_ST), BUY RELIANCE @1405.8→1418.5 +Rs 153.998 (target, RSI_EMA), BUY ADANIENT @2376.5→2385.4 +Rs 58.70 (exit, VWAP_ST)
- Notes: Profitable day; ADANIENT traded despite binary event (Q4 results) flag — strategy violation but happened to profit. All 3 entries single-strategy (1 confirmation) — violates Apr 29 lesson. Partial qty exits persist (21→13 RELIANCE, 12→8 ADANIENT). ADANIENT exit mislabeled "Stop-loss hit" but P&L was positive — logger bug.

## 2026-04-30 (Thursday) — Opening
- NIFTY prev close: 24,177.65 (TREND_DOWN regime; +0.76% bounce Apr 29 from 23,995 lows)
- Key gaps: Live quote API unavailable (enctoken limitation — non-blocking, bot fetches data internally)
- Bot status: RUNNING (paper, PID 9515, launched 09:05, collecting ORB range 9:15–9:30)
- Watchlist: RELIANCE (score 2.89), INFY (2.88), INDUSINDBK (2.80), ADANIENT (2.58), ICICIBANK (2.38)
- ALERT: ADANIENT has Q4 FY26 results today (binary event) — pre-market says AVOID, but scanner still selected it. Manual override needed if bot attempts ADANIENT entry.
- ALERT: INDUSINDBK had 2 SL hits yesterday — pre-market rule: no re-entry today.
- Regime: TREND_DOWN | VIX: ~NORMAL (18.03 on Apr 28)

## 2026-04-29 (Wednesday) — EOD
- Regime: STRONG_TREND_UP (RELIANCE/INFY at entry) | TREND_DOWN (TATAPOWER) | VIX: N/A
- Trades: 5 | Wins: 2 | Losses: 3 | Win Rate: 40%
- P&L: -Rs 210.79 (paper capital: Rs 99,808.85)
- Key trades: BUY RELIANCE @1420.91→1413.10 -Rs 164.01 (SL hit), SELL TATAPOWER @455.87→452.65 +Rs 125.66 (EOD), BUY INDUSINDBK @922.21→917.35 -Rs 155.55 (SL hit), BUY INDUSINDBK re-entry +Rs 7.77 (EOD)
- Notes: All signals single-confirmation (RSI_EMA only). Premature EOD bug fired again at 10:35 — 3rd occurrence, missed ORB window, entries only from 3rd bot restart at 11:34. TATAPOWER qty discrepancy (65 in, 39 closed). INDUSINDBK traded twice.

## 2026-04-29 (Wednesday) — Opening
- NIFTY open: ~24,026 (GIFT Nifty pre-open: +31 pts from 23,995; slight gap-up ~+0.13%)
- Key gaps: INFY -0.65%, TATAPOWER +0.18%, ADANIENT flat, ICICIBANK flat, TCS -0.15%
- Bot status: RUNNING (launched 09:05, ORB range collecting 9:15-9:30, 5 stocks selected)
- Watchlist: INFY (score 3.50, caution on guidance), ADANIENT (2.60, long bias), TCS (2.60, watch), ICICIBANK (2.43, caution), TATAPOWER (2.40, long bias)
- Regime: TREND_DOWN (prior sessions) | Quote API: Bad Request (enctoken — non-blocking)

## 2026-04-28 (Tuesday) — EOD
- Regime: RANGING | VIX: 18.03 (NORMAL, unavailable at open)
- Trades: 0 | Wins: 0 | Losses: 0 | Win Rate: N/A
- P&L: Rs 0.00 (paper capital intact at Rs 1,00,000)
- Key trades: None — all signals rejected (BHARTIARTL R:R 0.61-0.82; HDFCBANK R:R 0.95-1.18; ICICIBANK R:R 0.96; TCS R:R 1.28; BHARTIARTL confluence 34 < 40)
- Notes: Clean ranging day. ORB ranges were tight (ICICIBANK 0.43%, BHARTIARTL 0.76%). Strategies generated signals but R:R consistently sub-1.5 — risk filter correctly blocked all entries. Bot ran on time (09:05-15:00), no premature EOD. Spurious second launch at 15:05 (market already closed — investigate launchd).

## 2026-04-28 (Tuesday) — Opening
- NIFTY open: ~gap-down ~0.3% (SGX Nifty 24,043 vs prior close 24,119); STRONG_TREND_DOWN regime
- Key gaps: SGX Nifty -0.32%. INFY caution (weak FY27 guidance), TCS positive (AI partnership). RELIANCE avoided (score low, negative gap -1.11%)
- Watchlist (bot-selected): INFY, TCS, ICICIBANK, HDFCBANK, BHARTIARTL
- Bot status: RUNNING (paper mode, PID 73404, launched on-time 09:05:03 IST)
- Positions at open: NONE

## 2026-04-27 (Monday) — EOD
- Regime: TREND_UP | VIX: N/A
- Trades: 0 | Wins: 0 | Losses: 0 | Win Rate: N/A
- P&L: Rs 0.00 (paper capital intact at Rs 1,00,000)
- Key trades: None — all signals rejected (KOTAKBANK SELL R:R 0.87-0.90, HDFCBANK BUY R:R 0.71)
- Notes: Infrastructure issues — bot started at 12:42 PM (3.5h late), premature EOD bug at 12:45 PM. No ORB breakouts; all 5 watchlist stocks stayed in range. Risk filter correctly rejected poor R:R signals. No pre-market plan generated.

## 2026-04-27 (Monday) — Opening
- Bot status: RUNNING (paper mode, PID active, log confirmed at 09:15)
- Watchlist (bot-scored): INFY (3.50), TCS (2.84), ICICIBANK (1.84), RELIANCE (1.84), KOTAKBANK (1.79)
- Positions at open: NONE
- Quote API: enctoken limitation — shell quotes unavailable, bot polling directly
- ORB range: Building 09:15-09:30, breakout scan starts 09:30
- Note: circuit_limits API failing (Bad Request) — non-blocking, bot handles scoring via candle data

## 2026-04-24 (Friday) — EOD CONFIRMED
- Regime: STRONG_TREND_DOWN | VIX: N/A
- Trades: 3 closed (of 5 entries, 2 orphaned during restarts) | Wins: 2 | Losses: 1 | Win Rate: 67%
- P&L: Rs +19.64 (paper) — recovered from bot log; JSONL trade journal empty (exit logger bug)
- Key trades: SELL INFY @1153.52→1155.00 Rs -36.93 (RSI=25.9, oversold entry), SELL RELIANCE @1327.74→1326.80 Rs +20.59 (RSI=42.7), SELL ICICIBANK @1328.94→1327.30 Rs +35.97 (RSI=48.2)
- Notes: Session 1 complete. Bot correctly identified STRONG_TREND_DOWN and fired all SELL signals. All 3 exits via EOD square-off (no target/SL hits). INFY entry violated RSI<30 rule (RSI=25.9). 2 orphaned positions lost during bot restarts (ICICIBANK qty=22, TCS qty=12). Exit logger bug: exits logged to bot log but not JSONL — fix before Monday.

## 2026-04-23 (Thursday)
- Regime: N/A (Quote API unavailable) | VIX: N/A
- Trades: 0 | Wins: 0 | Losses: 0 | Win Rate: N/A
- P&L: Rs 0 (paper capital intact at Rs 1,00,000)
- Key trades: None
- Notes: Setup/debug day — /oms/quote returns Bad Request; pre-market plan not run; no signals generated. Fix quote endpoint routing before next session.

## 2026-04-23 (Thursday) — Opening
- NIFTY open: N/A (quote endpoint unavailable via OMS enctoken auth)
- Key gaps: Unable to fetch via API — manual check recommended
- Capital: Rs 600 equity, Rs 0 utilised, positions FLAT
- Bot status: Token refreshed at 13:23 IST — auth OK. No trading activity recorded yet.
- Quote API: /oms/quote returning "Bad Request" — likely requires api.kite.trade endpoint

_No trades recorded yet. Run /daily-summary after your first trading session._

## 2026-05-06 (Wednesday) — EOD
- Regime: STRONG_TREND_UP (upgraded from RANGING by 11:58 AM) | VIX: NORMAL (API unavailable)
- Trades: 2 | Wins: 2 | Losses: 0 | Win Rate: 100% (partial exits)
- P&L: +Rs 40.16 (paper capital: ~Rs 98,213.13)
- Key trades: BUY SUNPHARMA @1844.3 → 1850.4 +Rs 27.41 (EOD, 5/11 shares, ORB — 1-strat violation), BUY HDFCBANK @782.9 → 795.95 +Rs 12.75 (EOD, 1/51 shares, ORB+VWAP_ST ✓ — 2-strat compliant)
- Notes: TEST unit-test events polluted events file — reported pnl Rs 23,197 is invalid; real P&L is +Rs 40.16. 13 TATAPOWER SELL bias vetoes blocked what would have been profitable shorts (stock below VWAP all morning; long bias was wrong). Partial qty exit bug persists: HDFCBANK 50/51 shares unaccounted, SUNPHARMA 6/11 unaccounted. PNB and SBIN hard blocks held — no events.

## 2026-05-06 (Wednesday) — Opening
- NIFTY expected open: ~+0.9% gap-up (SGX Nifty +205pts +0.85% pre-open)
- Key gaps pre-market: RELIANCE -0.21% (crude tailwind offsets), TATAPOWER -0.08%, BPCL -0.48%, HDFCBANK -0.64%, ICICIBANK -0.54%, AXISBANK -0.56%, INFY -0.08% (NASDAQ+1% tailwind), SUNPHARMA volatile (Organon deal)
- Bot status: RUNNING (paper mode, PID=bot.pid, log=bot-2026-05-06.log confirmed 9:15 AM)
- Watchlist: RELIANCE, TATAPOWER, BPCL, SUNPHARMA, HDFCBANK, ICICIBANK, AXISBANK, INFY (8 symbols)
- Hard blocks: PNB (outside universe), SBIN (results May 8)
- Risk overrides: max_trades=4, risk_per_trade=1.0%, max_positions=2
- ORB range: Collecting 09:15–09:30, breakout scan active from 09:30
- Quote API: enctoken limitation — live quotes via OMS unavailable (bot polls candle API directly)
