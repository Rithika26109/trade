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
| Weeks completed | 3 |
| Cumulative P&L | -Rs 2,108.20 (paper) |
| Overall win rate | 43% (10W / 23T) |
| Best strategy | VWAP+ST (small sample, 1W/2T net +Rs 49) |
| Total trades | 23 (paper) |
| Sessions completed | 10 + 2 holidays |

---

## Improvement Goals

_Active targets for self-improvement. Updated weekly._

1. **Enforce 2+ confirmation in code, including high-score path** — close the
   high-score bypass loophole that produced losers on May 6 (SUNPHARMA) and
   May 7 (INFY). The MIN_CONFIRMATIONS gate must apply even when conviction
   score is high.
2. **Bias must adapt intraday** — if a `long`-biased stock is below VWAP at
   09:45, demote to `both` automatically. Three sessions of blocked profitable
   counter-trend signals this week (TATAPOWER, TCS, HDFCBANK).
3. **Partial qty EOD square-off bug in `order_manager.py`** — must reconcile
   to 0 open qty at 15:15. Recurred 4× this week (HDFCBANK, SUNPHARMA, RELIANCE).
4. **`already_stopped_today` veto in code** — PNB ×3 on May 5 and ADANIENT ×2
   on May 4 prove the rule is still doc-only after 3 weeks.
5. **Scanner allowlist enforcement** — May 8 bot picked BHARTIARTL/PNB/KOTAKBANK
   despite plan's hard-avoid; out-of-watchlist symbols still slip through.

---

<!-- Weekly summaries will be prepended here by /weekly-review command -->

## Week 2026-W19 (Mon May 04 - Fri May 08) — Worst Week to Date

- Days traded: 5 (no holiday)
- Total P&L: **-Rs 2,120.41** (paper) — 5-session run of red except Wed
- Win rate: 33% (4W / 12T)
- Best day: 2026-05-06 (+Rs 40.16, 2W/0L on partial-only exits)
- Worst day: 2026-05-05 (-Rs 1,153.77, 0W/4L; PNB ×3 SL hits, RELIANCE −1)
- Per-day: Mon −685, Tue −1,154, Wed +40, Thu −321, Fri 0 (5 bias vetoes)
- Strategy breakdown: ORB 2W/4T (mostly EOD partials), RSI+EMA 1W/3T, VWAP+ST 1W/4T, MULTI 0W/1T
- Regime prediction accuracy: 1/5 — daily-anchored regime missed Wed strong-trend-up and Thu gap-up-fade
- Bias veto count: 13 (Wed) + 5 (Fri) — mechanism wired, but the bias itself was the failure mode 3× (TATAPOWER May 6, TCS May 8, HDFCBANK May 8)
- Promoted lessons:
  - Pre-market `long` bias contradicted intraday tape on 3 sessions — heuristic: default to `both` unless catalyst is robust to intraday price action
  - High-score bypass produced 1-strategy losers 2× — MIN_CONFIRMATIONS must apply unconditionally
  - Partial-qty EOD exits remain critical (HDFCBANK 50/51 May 6, 8/44 May 7, SUNPHARMA 6/11 May 6)
  - Banking-cluster Q4 days contaminate cross-bank exposure (May 5, May 8)
- What worked: Hard `avoid` blocks held (SBIN, BHARTIARTL, PNB) — zero events; risk tightening Mon→Tue→Wed preserved capital from a third bad day; ITC-style 2-strategy entries remained directionally clean
- Key finding: Pre-market discipline was high (lessons cited, risks tightened, hard blocks honored). The losses came from code-side gaps the prompt cannot fix — bias-doesn't-adapt, high-score-bypass, partial-qty-exit. Documented rules without enforcement still cost real money.
- Changes this week: Weekly summary written; premarket.md refinements drafted but **not applied** (harness permission policy blocked the write — proposals documented in `logs/journal/weekly/2026-W19.md`)
- Next week goals: Apply the four queued premarket.md refinements; close MIN_CONFIRMATIONS bypass loophole; finally fix partial-qty EOD exit; wire `already_stopped_today` veto into order path

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
