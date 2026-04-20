# Claude Routines Integration — Setup Guide

Your trading bot now has three cloud-scheduled **Claude Routines** that
research, plan, and grade trades; the local bot only **executes** what the
morning plan approves.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Claude Routines (cloud)                          │
│                                                                     │
│  07:30 IST  premarket-plan  →  config/daily_plan.json  →  git push  │
│  16:30 IST  eod-review      →  logs/journal/…md        →  git push  │
│  Sat 10:00  weekly-meta     →  .claude/routines/*      →  git push  │
└─────────────────────────────┬───────────────────────────────────────┘
                              │  git
┌─────────────────────────────┴───────────────────────────────────────┐
│                      Local bot (your machine)                       │
│                                                                     │
│  09:10 IST  `git pull` → load_daily_plan() → apply risk overrides   │
│  09:15-15:15  trade (respecting bias + overrides)                   │
│  15:35 IST  scripts/eod_commit.py → git push events + metrics       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

- GitHub repo for this project (push access from your machine + from Claude).
- **Anthropic Pro plan is sufficient.** This design uses only 2 runs/weekday
  (premarket + eod-review) and 1 run on Saturday (weekly-meta) — well under
  Pro's 5 routine runs/day cap. Upgrade to Max only if you later add an
  intraday mid-session check-in routine.
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

## One-time: create a GitHub App for Claude

1. Go to https://code.claude.com → **Settings → GitHub**.
2. Install the Claude Code GitHub App on your `trade` repo.
3. Under **Branch permissions**, enable **"Allow unrestricted pushes to `main`"**
   (routines will commit `config/daily_plan.json` and `logs/journal/` directly).
4. Copy the repo URL — you'll paste it into each routine's config.

---

## One-time: store secrets in the GitHub repo

Routines read from repo secrets, not a local `.env`. From your machine:

```bash
gh secret set GEMINI_API_KEY   --repo <you>/trade --body "$GEMINI_API_KEY"
gh secret set KITE_API_KEY     --repo <you>/trade --body "$KITE_API_KEY"
# KITE_ACCESS_TOKEN is rotated daily by scripts/refresh_kite_token.py
# — don't set it manually.
```

The routines only need `KITE_API_KEY` + `KITE_ACCESS_TOKEN` (not the full
TOTP stack), because `scripts/premarket_context.py` detects a pre-supplied
token and skips the TOTP flow.

---

## One-time: set up the local kite-token rotator (06:30 IST daily)

The morning routine fires at 07:30 IST, but Kite access tokens expire at
06:00 IST and need an interactive TOTP re-login. `scripts/refresh_kite_token.py`
handles both: it re-logs-in locally (your machine has the TOTP secret) and
pushes the new token into the repo as `KITE_ACCESS_TOKEN` via `gh`.

Test it:
```bash
cd /Users/rithika-18920/Documents/aiaiai/serious/trade
source .venv/bin/activate
python scripts/refresh_kite_token.py --repo <you>/trade --dry-run
```

Install a local cron (`crontab -e`):
```
# Refresh Kite access token at 06:30 IST (= 01:00 UTC) on weekdays
0 1 * * 1-5  cd /Users/rithika-18920/Documents/aiaiai/serious/trade && .venv/bin/python scripts/refresh_kite_token.py --repo <you>/trade >> logs/token-refresh.log 2>&1
```

On macOS, cron works but `launchd` is the native choice. A simple cron entry
above is fine for a personal bot.

---

## One-time: create the three routines

At https://code.claude.com → **Routines → New**:

### 1. `premarket-plan`
- **Schedule:** every weekday at `02:00 UTC` (= 07:30 IST).
- **Repo:** `<you>/trade`, branch `main`.
- **Prompt:** paste contents of [`.claude/routines/premarket.md`](../.claude/routines/premarket.md).
- **Secrets:** `GEMINI_API_KEY`, `KITE_API_KEY`, `KITE_ACCESS_TOKEN`.
- **Working dir:** repo root.

### 2. `eod-review`
- **Schedule:** weekdays at `11:00 UTC` (= 16:30 IST).
- **Prompt:** paste [`.claude/routines/eod_review.md`](../.claude/routines/eod_review.md).
- **Secrets:** `GEMINI_API_KEY`. (No Kite needed — this routine only reads journals.)

### 3. `weekly-meta`
- **Schedule:** Saturday at `04:30 UTC` (= 10:00 IST).
- **Prompt:** paste [`.claude/routines/weekly_meta.md`](../.claude/routines/weekly_meta.md).
- **Secrets:** none.

Each routine gets its own job history; watch the first couple of runs.

---

## One-time: install the extra dep

The bot now requires `jsonschema` for plan validation:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

---

## How to run the bot (unchanged)

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
- [ ] Claude Code GitHub App installed on the repo, `main` push allowed.
- [ ] `GEMINI_API_KEY`, `KITE_API_KEY` stored as repo secrets.
- [ ] `scripts/refresh_kite_token.py --dry-run` succeeded locally.
- [ ] Local cron installed for 06:30 IST rotation.
- [ ] All three routines created in code.claude.com and armed.
- [ ] Bot still runs green in paper mode:
      `TRADING_MODE=paper python main.py`.
- [ ] After first morning run, `config/daily_plan.json` exists and
      `python scripts/validate_plan.py config/daily_plan.json` prints `OK:`.

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
