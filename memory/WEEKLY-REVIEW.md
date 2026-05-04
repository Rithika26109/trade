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
| Weeks completed | 2 |
| Cumulative P&L | Rs +12.21 (paper) |
| Overall win rate | 55% (6W / 11T) |
| Best strategy | VWAP+ST (1W/2T net +Rs 49 — small sample) |
| Total trades | 11 (paper) |
| Sessions completed | 5 + 1 holiday |

---

## Improvement Goals

_Active targets for self-improvement. Updated weekly._

1. **Fix premature EOD bug** — root-cause `wind-down` time comparison in commit 943a95b. Killed every ORB setup this week; 3 occurrences across W18.
2. **Enforce 2+ confirmation in code** — reject 1-strategy signals at the order path, not just in docs. 8/8 trades this week violated this.
3. **Hard-block binary-event stocks in scanner** — exclude from symbol selection entirely. ADANIENT Q4 traded on Apr 30 despite flag.
4. **Fix partial qty exit bug** — order_manager.py not closing 100% on EOD square-off (RELIANCE 21→13, ADANIENT 12→8 on Apr 30).

---

<!-- Weekly summaries will be prepended here by /weekly-review command -->

## Week 2026-W18 (Mon Apr 27 - Fri May 01) — First Full Week of Live Sessions

- Days traded: 4 sessions + 1 holiday (May 1 Maharashtra Day). Trades only on Apr 29 + Apr 30.
- Total P&L: -Rs 7.43 (paper) — net flat
- Win rate: 50% (4W / 8T)
- Best day: 2026-04-30 (+Rs 203.36, 3 trades, 67% win rate)
- Worst day: 2026-04-29 (-Rs 210.79, 5 trades, 40% win rate)
- Strategy breakdown: ORB 0/0 (never triggered — premature EOD killed window); RSI+EMA ~3W/6T (~-Rs 33); VWAP+ST 1W/2T (+Rs 49)
- Regime prediction accuracy: 1/4 (25%) — daily-bias regime missed intraday reversals on Apr 28, 29, 30
- Bias veto count: 0 across all sessions — mechanism may not be wired into the order path
- Promoted lessons:
  - Premature EOD bug (3rd, 4th, 5th occurrences) — top-priority root-cause fix
  - Single-confirmation entries violated rule on 8/8 trades — needs code enforcement, not docs
  - Binary-event filter is advisory only (ADANIENT traded despite flag)
  - Partial qty exits persist (3 stocks affected this week)
- What worked: Risk management rejected 7 weak R:R signals on Apr 28; max drawdown stayed at 0.21%; no daily loss exceeded 1%
- Key finding: Process discipline broke down even on profitable days. Apr 30 was +Rs 203 *but* violated 3 rules.
- Next week goals: Fix premature EOD bug, enforce 2+ confirmation in code, hard-block binary events in scanner

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
