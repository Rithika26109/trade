# Trade Log

Running log of daily trade summaries. Most recent first. Older than 30 days gets archived to `logs/journal/`.

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

<!-- Daily summaries will be prepended here by /daily-summary and /market-open commands -->

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
