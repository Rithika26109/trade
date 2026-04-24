# Weekly Review

Weekly performance summaries and meta-learning. Most recent first.

---

## Entry Format

```
## Week YYYY-Www (Mon DD - Fri DD Mon)
- Days traded: N
- Total P&L: Rs +/-X
- Win rate: X% (W wins / T total)
- Best day: YYYY-MM-DD (Rs +X)
- Worst day: YYYY-MM-DD (Rs -X)
- Strategy breakdown: ORB W/T, RSI+EMA W/T, VWAP+ST W/T
- Regime prediction accuracy: N/N correct
- Promoted lessons: ...
- Changes made: ...
```

---

## Running Statistics

| Metric | Value |
|--------|-------|
| Weeks completed | 1 |
| Cumulative P&L | Rs +19.64 (paper) |
| Overall win rate | 67% (2W / 3T) |
| Best strategy | RSI+EMA (MULTI) — only strategy used so far |
| Total trades | 3 (paper) |
| Sessions completed | 1 |

---

## Improvement Goals

_Active targets for self-improvement. Updated weekly._

1. **Fix exit logger bug** — exits must write to JSONL on all exit paths (target, SL, EOD). Blocker for accurate metrics.
2. **Add position reconciliation on startup** — query Kite for open positions on restart, re-attach tracking.
3. **Run full 9:30-3:15 session** — boot before market open, run entire day.
4. **Enforce RSI < 30 filter** — hard-reject SELL signals when RSI < 30 at entry.

---

<!-- Weekly summaries will be prepended here by /weekly-review command -->

## Week 2026-W17 (Mon Apr 20 - Fri Apr 24) — First Trading Week

- Days traded: 1 (Fri Apr 24; Thu Apr 23 attempted, failed on API auth)
- Total P&L: Rs +19.64 (paper)
- Win rate: 67% (2W / 3T closed)
- Best day: 2026-04-24 (Rs +19.64, 3 trades, first successful session)
- Worst day: 2026-04-23 (Rs 0, API auth blocked all trading)
- Strategy breakdown: MULTI(RSI+EMA) 2W/3T net +19.64; ORB 0/0; VWAP+ST 0/0
- Regime prediction accuracy: 1/1 (STRONG_TREND_DOWN correct on Apr 24)
- Key finding: RSI entry quality directly impacts outcomes — RSI 40-50 zone produced wins, RSI 25.9 entry lost
- Bugs found: (1) Exit logger doesn't write to JSONL on EOD square-off, (2) bot restarts orphan positions (no reconciliation), (3) journal YAML metrics all zeros despite real trades
- Promoted lessons: RSI < 30 filter rule, exit logger must fire on all exit paths, track win rate by MULTI confirmation count
- What worked: Regime engine correctly called STRONG_TREND_DOWN, all short signals aligned, cron automation operational
- Infrastructure: Bot fully operational, first session ran 13:49-15:02 IST (partial day)
- Next week goals: Fix exit logger, add position reconciliation, run full 9:30-3:15 session, enforce RSI<30 filter
