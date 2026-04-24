# Trading Bot — Daily Pipeline Checklist

All routines run locally via **launchd** (`~/Library/LaunchAgents/com.trade.*.plist`).
Unlike cron, launchd catches up missed jobs when the Mac wakes from sleep.

---

## Full Schedule (Weekdays)

| Time (IST) | What | launchd agent | Log |
|------------|------|---------------|-----|
| 07:50 | Kite token refresh | `com.trade.token-refresh` | `cron_token.log` |
| 08:03 | /pre-market research | `com.trade.claude-premarket` | `cron_premarket.log` |
| 09:05 | Bot launch (paper) | `com.trade.bot-launch` | `cron_launch.log` |
| 09:15 | Healthcheck | `com.trade.bot-healthcheck` | `cron_healthcheck.log` |
| 09:22 | /market-open review | `com.trade.claude-market-open` | `cron_market_open.log` |
| 12:03 | /midday check-in | `com.trade.claude-midday` | `cron_midday.log` |
| 15:00 | Bot stops new trades | automatic | `bot-YYYY-MM-DD.log` |
| 15:15 | Bot squares off | automatic | `bot-YYYY-MM-DD.log` |
| 15:33 | /daily-summary | `com.trade.claude-daily-summary` | `cron_daily_summary.log` |
| 15:35 | EOD git commit | `com.trade.eod-commit` | `cron_eod.log` |
| 16:07 | /weekly-review (Fri) | `com.trade.claude-weekly-review` | `cron_weekly_review.log` |

---

## Step-by-Step Verification

### 1. Kite Token Refresh (07:50)

**Test manually:**
```bash
.venv/bin/python3 scripts/refresh_kite_token.py --dry-run
```

**Expected:**
```
INFO     | Performing fresh login to Zerodha...
SUCCESS  | Logged in as MTD470
INFO     | [refresh_kite_token] obtained access token JKu1…UA==
dry-run: access_token=JKu1…UA== (length=120)
```

**Telegram:** "✅ 06:30 Token refresh OK (dry-run)"

**Verify auth working:**
```bash
scripts/kite.sh profile
```
Expected: JSON with `"status": "success"` and your user profile.

**Check log:**
```bash
cat logs/cron_token.log
```

**Common failures:**
- `Enter Zerodha password:` → KITE_PASSWORD missing from `config/.env`
- `login failed` → wrong password or Zerodha down
- No log at all → Mac didn't wake or cron not set

---

### 3. Pre-Market Research (08:03)

**Test manually:**
```bash
/opt/homebrew/bin/claude -p "/pre-market" --dangerously-skip-permissions --model sonnet
```

**Telegram:** 2 messages:
1. "🔍 Pre-market: Gemini research complete. Macro + N stocks analyzed."
2. "📋 Pre-market done. Bias: X. Watch: SYM1, SYM2. VIX: Y."

**Test Gemini separately:**
```bash
python3 scripts/gemini_research.py macro
```
Expected: JSON with `"content"` field containing macro briefing.

**Check log:**
```bash
tail -50 logs/cron_premarket.log
```

**Common failures:**
- `Not logged in · Please run /login` → run `claude login` once (one-time fix)
- `GEMINI_API_KEY not set` → add to `config/.env`
- `429 / RESOURCE_EXHAUSTED` → Gemini free tier quota hit. Wait midnight Pacific or new key at aistudio.google.com/apikey

---

### 4. Bot Launch (09:05)

**Test manually:**
```bash
TRADING_MODE=paper .venv/bin/python3 main.py --paper >> logs/bot-$(date +%F).log 2>&1 &
echo "PID: $!"
```

**Check if running:**
```bash
ps aux | grep main.py | grep -v grep
```
Expected: A line with `python main.py --paper`

**Check log:**
```bash
tail -20 logs/bot-$(date +%F).log
```

**Expected log (in order):**
```
TRADING BOT STARTING — Mode: PAPER
Loaded 9711 instruments from NSE (public CSV)
Zerodha connected successfully
Strategy: ORB
[RISK] VIX level set: XX.XX
Scanning 10 stocks...
Selected 5 stocks: [...]
WebSocket skipped (enctoken auth — using polling fallback)
Collecting opening range (15 min)...
TRADING LOOP STARTED
Trades: 0/7 | Open: 0 | ...
```

**Common failures:**
- `Authentication failed` → token not refreshed, run step 2
- `Route not found` on instruments → `market_data.py` not patched (should use public CSV)
- WebSocket reconnect spam → `main.py` not patched (should skip WebSocket)

---

### 5. Healthcheck (09:15)

**Test manually:**
```bash
scripts/healthcheck.sh
```

**Expected (bot running):**
```
[healthcheck] 2026-04-23 — PASS
[healthcheck] Bot running (PID XXXX), trading loop active, log fresh
```
**Telegram:** "✅ Bot healthcheck PASS (date). PID XXXX, trading loop active."

**Expected (bot NOT running):**
```
[healthcheck] 2026-04-23 — FAIL
[healthcheck] Telegram alert sent
```
**Telegram:** "🚨 Bot healthcheck FAILED (date). Reasons: ..."

**Check log:**
```bash
cat logs/cron_healthcheck.log
```

---

### 6. Market Open Review (09:22)

**Test manually:**
```bash
/opt/homebrew/bin/claude -p "/market-open" --dangerously-skip-permissions --model sonnet
```

**Telegram:** "Opening Bell Summary (date): Positions X. Capital Rs Y. ..."

**Check log:**
```bash
tail -50 logs/cron_market_open.log
```

---

### 7. Midday Check-In (12:03)

**Test manually:**
```bash
/opt/homebrew/bin/claude -p "/midday" --dangerously-skip-permissions --model sonnet
```

**Telegram:** 2 messages:
1. "⏳ Midday check-in starting..."
2. "📊 Midday: Positions: X | P&L: Y"

**Check log:**
```bash
tail -50 logs/cron_midday.log
```

---

### 8. Daily Summary (15:33)

**Test manually:**
```bash
/opt/homebrew/bin/claude -p "/daily-summary" --dangerously-skip-permissions --model sonnet
```

**Check log:**
```bash
tail -50 logs/cron_daily_summary.log
```

---

### 9. EOD Git Commit (15:35)

**Check log:**
```bash
cat logs/cron_eod.log
```

---

### 10. Weekly Review — Fridays (16:07)

**Test manually:**
```bash
/opt/homebrew/bin/claude -p "/weekly-review" --dangerously-skip-permissions --model opus
```

**Check log:**
```bash
tail -100 logs/cron_weekly_review.log
```

---

## Quick Health Checks

**All-in-one setup verify:**
```bash
launchctl list | grep com.trade               # All launchd agents loaded
/opt/homebrew/bin/claude -p "say hello" --model sonnet  # Claude CLI logged in
scripts/kite.sh profile                       # Kite auth working
python3 scripts/gemini_research.py macro      # Gemini API working
ps aux | grep main.py | grep -v grep          # Bot process running
scripts/healthcheck.sh                        # Full healthcheck
```

**Check all cron logs at once:**
```bash
for f in logs/cron_*.log; do echo "=== $f ==="; tail -3 "$f"; echo; done
```

**Today's bot log:**
```bash
tail -20 logs/bot-$(date +%F).log
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| No token refresh log | Mac asleep, launchd catches up on wake | Open lid before 07:50 or let launchd retry |
| `Enter Zerodha password:` in token log | KITE_PASSWORD not in .env | Add to `config/.env` |
| `Not logged in` in premarket log | Claude CLI not authed | Run `claude login` (one-time) |
| `GEMINI_API_KEY not set` | Missing from .env | Add to `config/.env` |
| `429 / RESOURCE_EXHAUSTED` | Gemini quota hit | Wait midnight Pacific or new key |
| `Route not found` on instruments | Old market_data.py | `load_instruments` should use public CSV |
| `Bad Request` on quotes/LTP | enctoken limitation | `get_ltp` should fallback to historical candles |
| WebSocket reconnect spam | enctoken limitation | `main.py` should skip WebSocket when `access_token` is empty |
| `command not found: python` | Only python3 exists | Use `python3` in all scripts and commands |
| Bot not running at 9:15 | run_bot.sh failed | Check `logs/cron_launch.log` |
| No trades all day | No signals / bearish regime | Check bot log for regime and HOLD entries |
| `tqdm` missing | Scanner dependency | `pip3 install tqdm` and `.venv/bin/pip install tqdm` |

---

## launchd Management

```bash
# List all trading agents
launchctl list | grep com.trade

# Manually trigger an agent
launchctl start com.trade.token-refresh

# Reload after editing a plist
launchctl unload ~/Library/LaunchAgents/com.trade.token-refresh.plist
launchctl load   ~/Library/LaunchAgents/com.trade.token-refresh.plist

# Check last exit status
launchctl list com.trade.token-refresh | grep LastExitStatus
```

All plists live in `~/Library/LaunchAgents/com.trade.*.plist`.

## Cloud vs Local — Two Automation Layers

This project has two separate automation layers, kept in different directories:

### Local Layer (`.claude/commands/`) — ACTIVE NOW

Runs on the Mac via launchd + `claude -p "/command"`. Uses `config/.env` for secrets, `scripts/kite.sh` for Kite API, local Python scripts for Gemini research. Interactive — the user can invoke these manually too.

| Command | Schedule | Purpose |
|---------|----------|---------|
| `/pre-market` | 08:03 | Morning research + watchlist |
| `/market-open` | 09:22 | Opening bell review |
| `/midday` | 12:03 | Mid-session check-in |
| `/daily-summary` | 15:33 | End-of-day P&L + lessons |
| `/weekly-review` | Fri 16:07 | Weekly performance recap |

Plus non-Claude scripts: `refresh_kite_token.py` (07:50), `run_bot.sh` (09:05), `healthcheck.sh` (09:15), `eod_commit.py` (15:35).

### Cloud Layer (`.claude/routines/`) — READY, NOT ACTIVE

Designed for Claude cloud triggers (RemoteTrigger API). Each routine runs in a fresh cloud clone — no `.env` file, secrets via environment variables, commits and pushes back to git.

| Routine | Schedule (IST) | Purpose |
|---------|---------------|---------|
| `premarket.md` | 07:30 Mon-Fri | Generate `daily_plan.json` + journal |
| `healthcheck.md` | 09:20 Mon-Fri | Verify bot started via heartbeat file |
| `eod_review.md` | 16:30 Mon-Fri | Deep hypothesis grading |
| `weekly_meta.md` | 10:00 Saturday | Self-improve the premarket routine |

**Why both?** Cloud routines generate artifacts (plans, reviews) and push to git. Local commands read those artifacts and present them to the user interactively. Cloud can't interact with the live Kite session; local can.

### Key Differences

| Aspect | Local (commands) | Cloud (routines) |
|--------|-----------------|-----------------|
| Secrets | `config/.env` | Environment variables |
| Kite API | `scripts/kite.sh` | `$KITE_ACCESS_TOKEN` env var |
| Telegram | `scripts/kite.sh telegram` | Direct `curl` to Telegram API |
| Gemini | `python3 scripts/gemini_research.py` | Same script (reads env vars) |
| Git | No push | Commits + pushes |
| Execution | `claude -p "/command"` via launchd | RemoteTrigger API (cloud) |

---

## Cloud Activation Checklist

When the Claude GitHub App becomes available, follow these steps to enable cloud routines:

1. **Install Claude GitHub App** on `Rithika26109/trade` at https://claude.ai/code/onboarding?magic=github-app-setup

2. **Verify GitHub secrets** are set:
   ```bash
   gh secret list --repo Rithika26109/trade
   ```
   Required: `KITE_ACCESS_TOKEN`, `KITE_API_KEY`, `KITE_API_SECRET`, `KITE_TOTP_SECRET`, `KITE_USER_ID`, `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

3. **Create cloud triggers** via `/schedule` command in Claude Code:
   - `premarket-plan` → 07:30 IST (02:00 UTC) weekdays → `.claude/routines/premarket.md`
   - `bot-healthcheck` → 09:20 IST (03:50 UTC) weekdays → `.claude/routines/healthcheck.md`
   - `eod-review` → 16:30 IST (11:00 UTC) weekdays → `.claude/routines/eod_review.md`
   - `weekly-meta` → 10:00 IST (04:30 UTC) Saturday → `.claude/routines/weekly_meta.md`

4. **Keep local launchd running** — cloud and local are complementary, not replacements:
   - Cloud `premarket-plan` (07:30) generates the plan → local `/pre-market` (08:03) reviews it
   - Cloud `healthcheck` (09:20) verifies bot → local `healthcheck.sh` (09:15) also verifies
   - Cloud `eod-review` (16:30) does deep grading → local `/daily-summary` (15:33) does user briefing

5. **Optional: remove local duplicates** — once cloud is stable, you can remove:
   - Local `healthcheck.sh` agent (cloud healthcheck replaces it)
   - That's it — the other local commands serve a different purpose than the cloud routines

---

## Key Files

| File | Purpose |
|------|---------|
| `.claude/commands/*.md` | Slash command prompts (run by launchd via claude CLI) |
| `.claude/routines/*.md` | Routine prompts (cloud format, ready for RemoteTrigger) |
| `scripts/refresh_kite_token.py` | Daily Kite login + token push |
| `scripts/run_bot.sh` | Bot launcher (heartbeat + caffeinate + main.py) |
| `scripts/healthcheck.sh` | Post-launch bot verification |
| `scripts/gemini_research.py` | Gemini-powered market research |
| `scripts/kite.sh` | Quick Kite REST API calls |
| `scripts/eod_commit.py` | End-of-day git commit |
| `config/.env` | All secrets (API keys, passwords) |
| `config/.access_token` | Cached Kite enctoken (refreshed daily) |
