# Claude Routines Integration — Setup Guide

Your trading bot now has three cloud-scheduled **Claude Routines** that
research, plan, and grade trades; the local bot only **executes** what the
morning plan approves.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Claude Routines (cloud)                          │
│                                                                     │
│  07:30 IST  premarket-plan  →  config/daily_plan.json  →  git push  │
│  09:20 IST  bot-healthcheck →  logs/journal/…md        →  Telegram? │
│  16:30 IST  eod-review      →  logs/journal/…md        →  git push  │
│  Sat 10:00  weekly-meta     →  .claude/routines/*      →  git push  │
└─────────────────────────────┬───────────────────────────────────────┘
                              │  git
┌─────────────────────────────┴───────────────────────────────────────┐
│                      Local bot (your machine)                       │
│                                                                     │
│  06:30 IST  cron → refresh_kite_token.py (access token rotation)    │
│  09:05 IST  cron → scripts/run_bot.sh                               │
│             ├── writes logs/bot_heartbeat.json → git push           │
│             ├── caffeinate -i (keep Mac awake ~6h40m)               │
│             └── exec main.py --paper                                │
│  09:10 IST  main.setup() → `git pull` → load_daily_plan()           │
│  09:15-15:15  trade (respecting bias + overrides)                   │
│  15:35 IST  scripts/eod_commit.py → git push events + metrics       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

- GitHub repo for this project (push access from your machine + from Claude).
- **Anthropic Pro plan is sufficient.** This design uses 3 runs/weekday
  (premarket + bot-healthcheck + eod-review) and 1 run on Saturday
  (weekly-meta) — under Pro's 5 routine runs/day cap. Upgrade to Max only
  if you later add an intraday mid-session check-in routine.
- Gemini API key (free tier works for v1).
- `gh` CLI installed & authenticated on your local machine
  (`brew install gh && gh auth login`).
- Existing `config/.env` with Kite credentials fully set.

---

## One-time: push the repo to GitHub

```bash
cd /Users/rithika-18920/Documents/aiaiai/serious/trade
git init              # if not already
git add -A
git commit -m "initial: trading bot + claude routines integration"
# Create the repo on GitHub, then:
git remote add origin git@github.com:<you>/trade.git
git branch -M main
git push -u origin main
```

**Double-check** `config/.env` is in `.gitignore` — it must **never** be
committed.

```bash
grep -q "^config/.env$" .gitignore || echo "config/.env" >> .gitignore
grep -q "^config/.access_token$" .gitignore || echo "config/.access_token" >> .gitignore
```

---

## One-time: connect GitHub to Claude Code

Routines need two distinct things from GitHub:
1. **Clone + push access** (required for all routines — scheduled or event).
2. **Webhook delivery** (only required for GitHub-event triggers — we don't use these).

Since all 4 routines below use **scheduled triggers**, you only need #1. The
Claude GitHub App (#2) is NOT required for this setup.

### Step 1 — grant clone/push access (`/web-setup`)

In any Claude Code CLI session, run:
```
/web-setup
```
Follow the OAuth prompt. This connects your GitHub account to cloud Claude
Code sessions so routines can clone the repo and push branches as you.

### Step 2 — allow non-`claude/` branch pushes (per routine)

By default, cloud sessions can only push to branches prefixed `claude/`.
Our routines push to `plan/`, `status/`, `eod/`, `meta/` — so you must
toggle **"Allow unrestricted branch pushes"** on the `trade` repo for each
routine:

1. Go to https://claude.ai/code/routines
2. Click each routine → pencil (edit) icon
3. Under **Repositories**, enable **"Allow unrestricted branch pushes"** for
   `Rithika26109/trade`
4. Save

Do this for all 4 routines.

### (Optional) Step 3 — GitHub App

Only install if you later add a GitHub-event trigger (e.g. "review every new
PR"). The install prompt appears inline when you add that trigger type — no
need to hunt for it in `claude.ai/settings`.

---

## One-time: set secrets on the cloud environment

Routines read env vars from the **cloud environment** attached to them
(e.g. `trade_bull`), **not** from GitHub repo secrets. Set them at
https://claude.ai/code/environments → your env → **Environment variables**.

**Required** (for all routines):
- `GEMINI_API_KEY` — premarket research via Gemini
- `KITE_API_KEY`, `KITE_API_SECRET` — Kite Connect client
- `KITE_USER_ID`, `KITE_PASSWORD`, `KITE_TOTP_SECRET` — auto-TOTP login

**Required** (for `bot-healthcheck` only):
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

**Do NOT set** `KITE_ACCESS_TOKEN` on the cloud environment. Each routine
does a fresh TOTP login at start via `src/auth/login.py::ZerodhaAuth`, so
a stale value in env would be actively harmful (the code falls through to
TOTP login only when the env var is absent).

### No cloud token-refresh routine needed

Earlier drafts of this doc described a separate 06:30 token-refresh
routine. That's no longer needed because each routine logs in fresh via
TOTP on startup. The local `scripts/refresh_kite_token.py` + 06:30 cron is
still useful for the **local bot** (which re-uses a cached token file
across the day), but irrelevant to cloud routines.

---

## One-time: create the four routines

Create at https://claude.ai/code/routines → **New routine**, or via the CLI
(`/schedule` in any Claude Code session), or via the `schedule` skill which
calls the `RemoteTrigger` API directly.

Cron expressions are in **UTC**. IST = UTC + 5:30.

### 1. `premarket-plan`
- **Schedule:** `0 2 * * 1-5` (02:00 UTC = 07:30 IST, weekdays).
- **Repo:** `Rithika26109/trade`, default branch `main`, unrestricted pushes ON.
- **Model:** `claude-opus-4-7` (research-heavy).
- **Prompt:** thin bootstrap pointing at [`.claude/routines/premarket.md`](../.claude/routines/premarket.md) — the routine reads it and follows instructions.
- **Secrets required on the cloud environment:** `GEMINI_API_KEY`, `KITE_API_KEY`, `KITE_API_SECRET`, `KITE_USER_ID`, `KITE_PASSWORD`, `KITE_TOTP_SECRET` (TOTP auto-login).

### 2. `bot-healthcheck`
- **Schedule:** `50 3 * * 1-5` (03:50 UTC = 09:20 IST, weekdays).
- **Model:** `claude-sonnet-4-6`.
- **Prompt:** bootstrap pointing at [`.claude/routines/healthcheck.md`](../.claude/routines/healthcheck.md).
- **Secrets:** `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
- Alerts via Telegram only on failure; silent on PASS.

### 3. `eod-review`
- **Schedule:** `0 11 * * 1-5` (11:00 UTC = 16:30 IST, weekdays).
- **Model:** `claude-sonnet-4-6`.
- **Prompt:** bootstrap pointing at [`.claude/routines/eod_review.md`](../.claude/routines/eod_review.md).
- **Secrets:** none strictly required (reads journals only); `GEMINI_API_KEY` optional.

### 4. `weekly-meta`
- **Schedule:** `30 4 * * 6` (04:30 UTC Sat = 10:00 IST Sat).
- **Model:** `claude-opus-4-7`.
- **Prompt:** bootstrap pointing at [`.claude/routines/weekly_meta.md`](../.claude/routines/weekly_meta.md).
- **Secrets:** none.

### About secrets on the cloud environment

Unlike the old GitHub-Actions-style flow, routines read secrets from the
**cloud environment** attached to the routine (not from `gh secret`).
Configure them at https://claude.ai/code/environments → your env
(e.g. `trade_bull`) → **Environment variables**. The routine prompts
read them via `os.environ.get()` or `$VAR`.

The existing `gh secret set` values on the repo are still useful for any
GitHub-Actions workflows and for the local bot's token-refresh flow —
keep them. The cloud environment values are a separate mirror consumed
only by routines.

Each routine has its own run history at https://claude.ai/code/routines —
watch the first couple of runs.

---

## One-time: install the extra dep

The bot now requires `jsonschema` for plan validation:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Auto-running the bot (local cron)

Claude routines live in the cloud and cannot host a 6-hour live trading
process (short job runtimes, no Kite WebSocket, no static-IP whitelisting
for SEBI compliance). The bot itself therefore runs **locally on your
Mac**, launched daily by `cron`.

### One-time: install the launcher cron

[`scripts/run_bot.sh`](../scripts/run_bot.sh) is the launcher. It writes a
heartbeat file to `logs/bot_heartbeat.json` and pushes it to the repo
(so the cloud `bot-healthcheck` routine can see it), starts `caffeinate -i`
to keep the Mac awake through market hours, and then execs `main.py` in
**paper mode**. Promoting to live mode is an intentional manual edit of
this script.

Add to `crontab -e` (matches the existing UTC convention used by the
token-refresh cron):
```
# Launch trading bot at 09:05 IST (= 03:35 UTC) on weekdays
35 3 * * 1-5  cd /Users/rithika-18920/Documents/aiaiai/serious/trade && scripts/run_bot.sh >> logs/cron.log 2>&1
```

### Sanity test on a weekend

```bash
bash scripts/run_bot.sh
```
Expected: heartbeat file written + committed + pushed, `caffeinate`
started, `main.py` runs and exits immediately via
`settings.is_market_day()` since the market is closed. `logs/bot-<date>.log`
should contain the shutdown line.

### Caveats

- **MacBook lid closed / battery power:** `caffeinate -i` blocks idle
  sleep but does **not** stop clamshell sleep. If the Mac lives closed,
  either keep it on AC with an external display, or run on an
  always-on mini / server.
- **System timezone:** the cron line above assumes the Mac's system
  clock is UTC (which is `cron`'s default interpretation). If your
  system is on IST, rewrite to `5 9 * * 1-5` and also rewrite the
  token-refresh cron (`0 1` → `30 6`) to match, or you'll end up
  off by 5h30m.
- **Mid-day crash:** the 09:20 healthcheck catches startup failures
  only. For crashes later in the session, `main.py` already sends a
  `🚨 Bot crashed` Telegram alert from its own error handler.
- **To disable auto-run:** comment out the cron line. Everything else
  (manual runs, routines, token refresh) keeps working unchanged.

## How to run the bot manually (unchanged)

```bash
TRADING_MODE=paper python main.py
```

On startup you'll see new log lines:
```
[PLAN] git pull: Fast-forward  (or "up to date")
[PLAN] Loaded daily_plan.json: 7 tradeable symbol(s), 1 avoid, overrides={...}
[RISK] Override: max_trades = 3 (cap=5)
[PLAN] Using plan watchlist (7 symbols)
```

And during the day:
```
[PLAN] Vetoed SELL on INFY (bias=long)
```

If no plan exists (routine hasn't run yet, or `git pull` failed), the bot
falls back to the static `WATCHLIST` in `config/settings.py` and default
settings caps — exactly the old behaviour.

---

## First-day checklist

- [ ] Repo pushed to GitHub with `config/.env` gitignored.
- [ ] `/web-setup` run once from Claude Code CLI (grants clone/push to cloud).
- [ ] **"Allow unrestricted branch pushes"** toggled ON for `Rithika26109/trade`
      on EACH of the 4 routines (required — they push to `plan/`, `status/`,
      `eod/`, `meta/` branches, not `claude/`-prefixed).
- [ ] `GEMINI_API_KEY`, `KITE_API_KEY`, `KITE_API_SECRET`, `KITE_USER_ID`,
      `KITE_PASSWORD`, `KITE_TOTP_SECRET` set on the cloud **environment**
      (claude.ai/code/environments) — NOT just repo secrets. Routines do
      fresh TOTP login on startup.
- [ ] `KITE_ACCESS_TOKEN` is NOT set on the cloud env (any stale value would
      bypass fresh login — keep it unset).
- [ ] `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` set on the cloud environment
      (used by `bot-healthcheck`).
- [ ] `scripts/refresh_kite_token.py --dry-run` succeeded locally.
- [ ] Local cron installed for 06:30 IST token rotation.
- [ ] Local cron installed for 09:05 IST bot launch (`scripts/run_bot.sh`).
- [ ] `bash scripts/run_bot.sh` on a weekend produced a heartbeat commit.
- [ ] All four routines created in code.claude.com and armed
      (premarket-plan, bot-healthcheck, eod-review, weekly-meta).
- [ ] Bot still runs green in paper mode:
      `TRADING_MODE=paper python main.py`.
- [ ] After first morning run, `config/daily_plan.json` exists and
      `python scripts/validate_plan.py config/daily_plan.json` prints `OK:`.
- [ ] After first 09:20 healthcheck, `logs/journal/<today>.md` contains a
      `## Startup — PASS` section.

---

## Troubleshooting

**Plan was committed but bot ignored it.**
Run `python scripts/validate_plan.py config/daily_plan.json`. If it
prints errors, the plan is invalid; the bot's plan-loader logged why it
was rejected (see `logs/trading.log` for `[PLAN]` lines).

**Routine keeps failing to push.**
Check the Claude routine's job log. Most common: GitHub App doesn't have
write permission on `main`, or the branch-protection settings block pushes.

**Kite token refresh keeps failing.**
Run manually: `python scripts/refresh_kite_token.py --repo <you>/trade`.
99% of failures are TOTP mismatches — check system time is NTP-synced.

**I don't want the bot to auto-pull on startup.**
Comment out the `git_pull()` line in `main.py setup()`. The bot will use
whatever plan is already on disk.

---

## What the bot can NEVER do via routines

These are hard guarantees; the routine prompts forbid them and the
`plan_loader` re-checks:
- Route-to live mode (only `TRADING_MODE=live` env does that, and routines
  can't set env on your machine).
- Loosen risk caps above `config/settings.py` values.
- Place orders directly (Kite is read-only from the routines — premarket
  context script doesn't carry order-placing code).
- Touch `src/**`, `config/settings.py`, `main.py`, or tests.

The only self-modifying path is `weekly-meta` editing
`.claude/routines/premarket.md` — and that file never affects the running
bot, only future routine runs.
