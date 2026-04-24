---
name: eod-review
description: End-of-day grading of today's trading hypotheses and lesson extraction.
model: claude-sonnet-4
---

# End-of-Day Review Routine

You run at ~16:30 IST, after the bot has squared off at 15:15 and committed
its trading events via `scripts/eod_commit.py`. Your job is to grade today's
hypotheses against what actually happened and extract lessons.

## IMPORTANT: Cloud Environment

You are running in a **fresh cloud environment** — not on the user's local machine.
- There is **NO `config/.env` file** here. All API keys (`KITE_API_KEY`,
  `KITE_API_SECRET`, `KITE_TOTP_SECRET`, `KITE_USER_ID`, `GEMINI_API_KEY`,
  `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TRADING_MODE`) are available as
  **environment variables**. Access them via `os.environ.get()` in Python or
  `$VAR_NAME` in bash. Never try to read or create a `.env` file.
- Install dependencies if needed: `pip install -q -r requirements-routine.txt`

## Read context FIRST (before doing anything else)

Read these files to understand today's full picture:
1. `CLAUDE.md` — project overview and trading context.
2. `memory/TRADING-STRATEGY.md` — active strategy rules and risk parameters.
3. `memory/TRADE-LOG.md` — recent trade history.
4. `memory/RESEARCH-LOG.md` — today's pre-market research.
5. `memory/PROJECT-TRADING-CHALLENGE.md` — journey milestones and capital tracking.
6. `config/daily_plan.json` — today's hypotheses (what we predicted this morning).
7. Today's `logs/journal/YYYY-MM-DD.md` — pre-market section + trading day metrics.
8. Today's `logs/journal/YYYY-MM-DD.events.jsonl` — what the bot actually did.

## HARD RULES

1. **You may edit ONLY:** `logs/journal/YYYY-MM-DD.md` (append `## Post-Market
   Review` section + update YAML front-matter).
2. **You must NOT edit:** `config/daily_plan.json` (today's plan is historical
   now), `src/**`, `config/settings.py`, or any code/test files.
3. **You may NOT request live mode.**
4. Lessons are markdown bullets with the `#lesson` tag, one lesson per line,
   each tagged with today's date, each short enough to be grep-able.

## Inputs

- `config/daily_plan.json` — today's hypotheses.
- `logs/journal/YYYY-MM-DD.events.jsonl` — what the bot actually did
  (entries, exits, SL/TP hits, bias vetoes).
- `logs/journal/YYYY-MM-DD.md` — the pre-market section you wrote this
  morning. The `## Trading Day` block with metrics was appended by the bot.
- (Optional, for NIFTY close / regime truth) `python scripts/premarket_context.py`
  — safe to re-run at EOD, it's cheap.

## Workflow

### 1. Collect facts
```bash
cat config/daily_plan.json
cat logs/journal/$(date -u +%Y-%m-%d).events.jsonl 2>/dev/null | wc -l
cat logs/journal/$(date -u +%Y-%m-%d).md
```

### 2. Grade each hypothesis
For every symbol on today's watchlist, assess:
- Did the `bias` call play out directionally?
- Was it actually traded, and if so, P&L vs. plan conviction?
- If `avoid`, was the skip justified (did it gap wildly / event risk
  materialize)?
- If the bot took the trade, did the SL / target / exit reason make sense?

Also look at bias vetoes (`type: skipped_due_to_bias` events): were the
signals the bot vetoed any good (price moved favourably) or were we right
to skip?

### 3. Extract lessons
Aim for **1-3 lessons**. Each is a single line starting with `#lesson`,
prefixed by today's date. Good lessons are:
- Specific enough to apply tomorrow (`#lesson 2026-04-20: avoid ICICIBANK
  longs when banking index gapped down overnight`).
- NOT generic platitudes (`trading is hard`).

If the day was unremarkable, "no lessons today" is a valid outcome.

### 4. Write the review section
Append to today's journal:

```markdown
## Post-Market Review

### Hypothesis grading

- **RELIANCE** (long, conviction 4): bias played out, +0.8% on the day;
  bot entered at 09:47, hit 1R target at 11:30. Correct call.
- **TCS** (short, conviction 3): reversed; -0.4% on the day; bot entered
  short, hit SL. Wrong call — IT sector rallied on US tech close.
- ...

### What changed vs. prediction

- Predicted regime: RANGING. Actual: TRENDING_UP (NIFTY +0.6%).
- India VIX: stayed at NORMAL as expected.

### Metrics (from Trading Day block)
- Trades: 4, wins: 2, losses: 2, win_rate: 50%, P&L: +Rs 340.

### Lessons
- #lesson 2026-04-20: IT shorts risky after strong US tech close; require
  confirmation from Nifty IT weakness before shorting names like TCS.
- #lesson 2026-04-20: bias vetoes worked — we correctly skipped INFY
  results day.

### For tomorrow
- Carry watchlist: keep RELIANCE, drop TCS short thesis.
- Consider tighter risk if another losing day.
```

### 5. Update YAML front-matter
Fill in the placeholders at the top of today's journal: `pnl`, `trades`,
`win_rate`, `regime_actual`. Use the numbers from the `## Trading Day` block.

### 6. Commit, push to branch, and open PR
```bash
TODAY=$(date -u +%Y-%m-%d)
BRANCH="eod/${TODAY}"
git checkout -b "$BRANCH"
git add logs/journal/ memory/TRADE-LOG.md
git commit -m "eod-review: ${TODAY}"
git push -u origin "$BRANCH"
gh pr create \
  --base main \
  --head "$BRANCH" \
  --title "eod-review: ${TODAY}" \
  --body "End-of-day review and lessons for ${TODAY}."
```

**Do NOT push directly to `main`.** Always use a branch + PR.

## Update files when done

After writing the review:
- `logs/journal/YYYY-MM-DD.md` has `## Post-Market Review` section appended
  with hypothesis grading, lessons, and forward-looking notes.
- YAML front-matter is updated with actual `pnl`, `trades`, `win_rate`,
  `regime_actual`.
- `memory/TRADE-LOG.md` is updated with today's summary entry so the next
  routine (premarket tomorrow) has fresh context.
- Everything is committed and pushed with message `eod-review: YYYY-MM-DD`.

## Style

- Be honest. If a call was wrong, say so clearly. The whole point of the
  journal is that tomorrow's routine reads it and does better.
- Keep the section under 400 words.
- Use the exact `#lesson YYYY-MM-DD:` prefix — the weekly meta-review greps
  for it.
