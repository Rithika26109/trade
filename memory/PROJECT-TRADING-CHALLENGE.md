# Trading Challenge

A structured journey from complete beginner to systematic intraday trader on NSE.

---

## Goal

Learn intraday trading on Indian markets (NSE/BSE) using a systematic, bot-assisted approach with Zerodha Kite Connect. Prioritize learning and capital preservation over profits.

## Challenge Rules

1. Start with Rs 1,00,000 paper capital
2. Paper trade for minimum 20 sessions before considering live
3. Track everything: every trade, every lesson, every emotion
4. Review weekly, adjust monthly
5. Graduate to live only when paper shows consistent profitability (positive expectancy over 50+ trades)
6. Never risk more than 1% per trade, 3% daily max loss
7. Follow the bot's strategy — no emotional overrides

## Milestones

| Phase | Timeline | Goal | Status |
|-------|----------|------|--------|
| Setup | Week 1 | Bot running in paper mode, all routines active | Done (2026-04-24) |
| First trades | Week 2-3 | Complete 10 paper trades, learn the flow | Done (11 trades by 2026-04-30) |
| Baseline | Month 1-2 | 30+ trades, first meaningful win rate data | Done (40 entries by 2026-05-15, 35% win rate, -Rs 3,856.08 net) |
| Refinement | Month 2-3 | Backtest tuning, strategy adjustments | In progress — code-side fixes prioritized (HIGH_CONVICTION bypass, stale-plan gate, partial-qty EOD, post-restart cooldown) |
| Consistency | Month 3-4 | Positive expectancy over 50+ trades | Pending |
| Live decision | Month 5-6 | If ready: start live with smallest position sizes | Pending |

## Capital Tracking

| Metric | Value |
|--------|-------|
| Paper starting balance | Rs 1,00,000 |
| Current paper balance | Rs 96,143.92 |
| High-water mark | Rs 1,00,012.21 |
| Max drawdown | Rs 3,868.29 (3.86%) |
| Sessions completed | 15 trading days + 2 holidays. **W20 (May 11-15):** Mon Rs 0 (0 trades, 8 clean rejections); Tue +Rs 390.96 (3W/0L, 100%); Wed -Rs 469.55 (0W/4L); Thu -Rs 632.72 (1W/4L, only winner was hard-avoid SBIN); Fri -Rs 645.61 (0W/4L, bot crash + post-restart 1-strat entries). W20 net -Rs 1,356.92. Prior sessions: 2026-04-24 — Rs +19.64, 3 trades, 2W/1L; 2026-04-27 — Rs 0; 2026-04-28 — Rs 0; 2026-04-29 — Rs -210.79, 5 trades, 2W/3L; 2026-04-30 — Rs +203.36, 3 trades, 2W/1L; 2026-05-01 — HOLIDAY Maharashtra Day; 2026-05-04 — Rs -685.47, 4 trades, 2W/2L; 2026-05-05 — Rs -1,153.77, 4 trades, 0W/4L; 2026-05-06 — Rs +40.16, 2 trades, 2W/0L; 2026-05-07 — Rs -321.33, 2 trades, 0W/2L; 2026-05-08 — Rs 0, 5 bias vetoes |

## Emotional Check-In Prompts

Use these during /daily-summary to stay honest:

- How do I feel about today's results? Calm, frustrated, excited?
- Did I have any urge to deviate from the strategy?
- Am I tempted to increase position size after a win?
- Am I scared to take the next trade after a loss?
- Did I stick to my rules, or did emotions take over?

---

_Updated by /daily-summary and /weekly-review commands._
