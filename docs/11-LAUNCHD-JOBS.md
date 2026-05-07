# Launchd Jobs Reference

Quick-reference for all scheduled jobs in this project. Read this before running jobs manually.

All jobs use **macOS launchd** (not cron). Plist files live in `~/Library/LaunchAgents/com.trade.*.plist`.
Times below are **IST** (the user's local timezone). Weekdays 1–5 = Mon–Fri.

## Where times are configured

Each job's schedule is set in its **plist file's `StartCalendarInterval`** key.

```
~/Library/LaunchAgents/com.trade.<job-name>.plist
```

Edit the `<key>Hour</key>` and `<key>Minute</key>` integers inside `StartCalendarInterval`,
then reload the job:

```bash
launchctl unload ~/Library/LaunchAgents/com.trade.<job-name>.plist
launchctl load   ~/Library/LaunchAgents/com.trade.<job-name>.plist
```

## Job table

| Time (IST) | Job (label) | Plist | What it does | Log |
|------------|-------------|-------|--------------|-----|
| 08:30 Mon–Fri | `com.trade.token-refresh` | `com.trade.token-refresh.plist` | Rotates Kite access token, pushes to GitHub secret `KITE_ACCESS_TOKEN` | `logs/cron_token.log` |
| 08:35 Mon–Fri | `com.trade.claude-premarket` | `com.trade.claude-premarket.plist` | Runs `/pre-market` routine via Claude (morning research + Telegram briefing) | `logs/cron_premarket.log` |
| 09:05 Mon–Fri | `com.trade.bot-launch` | `com.trade.bot-launch.plist` | Starts the trading bot (`scripts/run_bot.sh` → `main.py --paper`) | `logs/cron_launch.log` |
| 09:15 Mon–Fri | `com.trade.bot-healthcheck` | `com.trade.bot-healthcheck.plist` | Verifies bot is running; Telegram alert on failure | `logs/cron_healthcheck.log` |
| 09:22 Mon–Fri | `com.trade.claude-market-open` | `com.trade.claude-market-open.plist` | Runs `/market-open` routine via Claude (opening bell review) | `logs/cron_market_open.log` |
| 12:03 Mon–Fri | `com.trade.claude-midday` | `com.trade.claude-midday.plist` | Runs `/midday` routine via Claude (mid-session check) | `logs/cron_midday.log` |
| 15:33 Mon–Fri | `com.trade.claude-daily-summary` | `com.trade.claude-daily-summary.plist` | Runs `/daily-summary` routine via Claude (EOD review) | `logs/cron_daily_summary.log` |
| 15:35 Mon–Fri | `com.trade.eod-commit` | `com.trade.eod-commit.plist` | Commits + pushes journal/metrics (`scripts/eod_commit.py`) | `logs/cron_eod.log` |
| 16:07 Fri only | `com.trade.claude-weekly-review` | `com.trade.claude-weekly-review.plist` | Runs `/weekly-review` routine via Claude using Opus | `logs/cron_weekly_review.log` |

`com.trade.claude-debug.plist` and `com.trade.test-simple.plist` are **test plists** — ignore.

## How to run a job manually (kickstart)

This is the canonical "run it now" command — used when a scheduled job missed its window
(e.g. Mac was asleep / offline, or you want to re-run after fixing something):

```bash
launchctl kickstart -k gui/$(id -u)/<job-label>
```

The `-k` flag kills any in-progress instance first. Examples:

```bash
launchctl kickstart -k gui/$(id -u)/com.trade.token-refresh
launchctl kickstart -k gui/$(id -u)/com.trade.claude-premarket
launchctl kickstart -k gui/$(id -u)/com.trade.bot-launch
launchctl kickstart -k gui/$(id -u)/com.trade.claude-market-open
launchctl kickstart -k gui/$(id -u)/com.trade.claude-midday
launchctl kickstart -k gui/$(id -u)/com.trade.claude-daily-summary
launchctl kickstart -k gui/$(id -u)/com.trade.eod-commit
launchctl kickstart -k gui/$(id -u)/com.trade.claude-weekly-review
launchctl kickstart -k gui/$(id -u)/com.trade.bot-healthcheck
```

`kickstart` returns immediately — the job runs in the background. **Always tail the
log to verify it actually ran**:

```bash
tail -30 logs/cron_<name>.log
```

For Claude routines, look for `--- CRON START` and `--- CRON END (exit=0)` markers.
A `CRON START` without a matching `CRON END` means the job stalled (often network).

## Verifying a job is loaded / scheduled

```bash
# Is it registered with launchd?
launchctl list | grep com.trade

# Full status (last exit code, next run, PID if running)
launchctl print gui/$(id -u)/com.trade.<job-label>
```

## Underlying scripts

The plists are thin wrappers — the real work lives in:

- `scripts/refresh_kite_token.py` — token refresh
- `scripts/run_bot.sh` — bot launcher (writes heartbeat, runs `caffeinate`, execs `main.py --paper`)
- `scripts/healthcheck.sh` — bot liveness check + Telegram alert
- `scripts/run_claude_cron.sh <routine-name>` — generic Claude routine runner; reads `.claude/routines/<routine-name>.md`
- `scripts/eod_commit.py` — git commit + push of EOD artifacts

So you can also bypass launchd and run any job directly, e.g.:

```bash
.venv/bin/python3 scripts/refresh_kite_token.py --repo Rithika26109/trade
/bin/bash scripts/run_claude_cron.sh pre-market
/bin/bash scripts/run_claude_cron.sh market-open
/bin/bash scripts/run_claude_cron.sh midday
/bin/bash scripts/run_claude_cron.sh daily-summary
MODEL=opus /bin/bash scripts/run_claude_cron.sh weekly-review
.venv/bin/python3 scripts/eod_commit.py
```

Direct execution streams output to your terminal instead of `logs/cron_*.log`.

## Editing a schedule

1. Edit `~/Library/LaunchAgents/com.trade.<job-name>.plist`.
2. Update `<key>Hour</key>` / `<key>Minute</key>` inside `StartCalendarInterval`.
3. Reload:
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.trade.<job-name>.plist
   launchctl load   ~/Library/LaunchAgents/com.trade.<job-name>.plist
   ```
4. Confirm:
   ```bash
   launchctl print gui/$(id -u)/com.trade.<job-name> | grep -E "next|state"
   ```

## Why launchd, not cron

Launchd runs **missed jobs** when the Mac wakes from sleep — cron silently skips them.
Critical for a trading box that may sleep overnight.

## Notes for AI instances running these jobs

- **Always check the log tail before assuming a job ran.** A fresh `cron_*.log`
  modification time only proves *something* ran — look for the `CRON END (exit=0)`
  marker (Claude routines) or success log lines (Python scripts).
- **Network gating**: `run_claude_cron.sh` and `refresh_kite_token.py` both wait
  for network before starting and log `WAITING FOR NETWORK / NETWORK BACK` markers.
- **Order matters in the morning**:
  1. Token refresh (08:30) must succeed before the bot launches.
  2. Premarket (08:35) is informational — can run late, but should finish before
     09:15 market open.
  3. Bot launch (09:05) needs a valid token from step 1.
- If you re-run premarket after 08:30, expect it to take 3–8 minutes. The bot
  launches at 09:05 regardless.
- See [09-CLAUDE-ROUTINES-SETUP.md](09-CLAUDE-ROUTINES-SETUP.md) for full routine
  internals and [10-DAILY-PIPELINE-CHECKLIST.md](10-DAILY-PIPELINE-CHECKLIST.md)
  for the daily flow.
