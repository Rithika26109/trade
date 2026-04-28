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
