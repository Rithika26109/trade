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
