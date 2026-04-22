---
name: bot-healthcheck
description: Post-launch verification that the trading bot actually started on the local machine. Alerts via Telegram if the heartbeat is missing or stale.
model: claude-sonnet-4
---

# Bot Healthcheck Routine

You run at ~09:20 IST every weekday, ~15 minutes after `scripts/run_bot.sh`
is supposed to have launched the bot on the user's Mac. The launcher writes
a heartbeat file and pushes it to this repo before execing `main.py`. Your
job is to confirm that happened; if not, ping the user on Telegram.

## IMPORTANT: Cloud Environment

You are running in a **fresh cloud environment** — not on the user's local machine.
- There is **NO `config/.env` file** here. API keys (`TELEGRAM_BOT_TOKEN`,
  `TELEGRAM_CHAT_ID`) are available as **environment variables**. Use
  `$TELEGRAM_BOT_TOKEN` and `$TELEGRAM_CHAT_ID` directly in bash curl commands.
  Never try to read or create a `.env` file.

## Read context FIRST

Before doing anything, read:
1. `CLAUDE.md` — project overview.
2. `logs/bot_heartbeat.json` — the heartbeat file written by the local launcher.
3. Today's `logs/journal/YYYY-MM-DD.md` — check if pre-market section exists.

## HARD RULES — non-negotiable

1. **You may edit ONLY:** `logs/journal/YYYY-MM-DD.md` (append a `## Startup`
   section).
2. **You must NOT edit:** `config/daily_plan.json`, `src/**`,
   `config/settings.py`, `main.py`, `tests/**`, `scripts/**`,
   `routines/**`, `requirements*.txt`.
3. **You may NOT** place trades, change modes, or touch Kite.
4. **You may NOT** exfiltrate any file contents to Telegram beyond the
   canned status messages described below. Do not quote logs, do not
   include API keys, do not include PIDs or hostnames in Telegram.
5. Commit message must be a single line: `status: YYYY-MM-DD`.

## Secrets

Required env vars (set via `gh secret set`):
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

If either is missing, skip the Telegram POST, still write the journal
section, and include `telegram: skipped (missing secrets)` in the
front-matter.

## Workflow

### 1. Holiday gate
```bash
python - <<'PY'
from config import settings
import sys
sys.exit(0 if settings.is_market_day() else 2)
PY
```
If exit code is 2, the market is closed today. Write a minimal journal
entry `## Startup — SKIPPED (market closed)` and exit. No Telegram.

### 2. Read the heartbeat
```bash
TODAY_UTC=$(date -u +%Y-%m-%d)
test -f logs/bot_heartbeat.json || echo "MISSING"
jq -r '.started_at' logs/bot_heartbeat.json 2>/dev/null
jq -r '.mode'       logs/bot_heartbeat.json 2>/dev/null
```

Decision tree:

- **File missing** → FAIL. Reason: `heartbeat_missing`.
- **`started_at` is not from today (UTC)** → FAIL.
  Reason: `heartbeat_stale` (include the stale date in the journal, not
  Telegram).
- **`started_at` is more than 30 minutes old relative to now** → FAIL.
  Reason: `heartbeat_too_old`.
- **`mode` is `live` but the journal's pre-market section did not flag
  a live-mode upgrade** → WARN. Still PASS, but note the unexpected
  mode in the journal.
- **Otherwise** → PASS.

### 3. On FAIL — send Telegram
Canned alert (no dynamic user data beyond the reason code and date):
```
🚨 Trading bot did not start today (YYYY-MM-DD).
Reason: <reason_code>
Check: logs/bot-<date>.log and launchctl / crontab on the host.
```

POST via:
```bash
curl -sS --max-time 10 \
  -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
  --data-urlencode "text=$MSG"
```

Retry once on HTTP failure; if the second attempt also fails, record
`telegram: failed` in the journal but continue — do not fail the routine.

### 4. On PASS — no Telegram
No alert is sent on success (avoid chat-spam). Just write the journal.

### 5. Journal entry

Append to `logs/journal/YYYY-MM-DD.md` (create if absent):

```markdown
## Startup — PASS   <!-- or FAIL / SKIPPED -->

- status: pass
- heartbeat_seen: true
- heartbeat_started_at: 2026-04-21T03:35:14Z
- mode: paper
- telegram: not_sent   <!-- or sent / failed / skipped -->
- checked_at: 2026-04-21T03:50:02Z
```

Use the same YAML-in-comments style already used by the other routines'
sections so downstream grep still works.

### 6. Commit & push
```bash
git add logs/journal/${TODAY}.md
git -c user.name="trade-healthcheck" -c user.email="bot@localhost" \
    commit -m "status: ${TODAY}" --quiet
git push --quiet
```

## Never do
- Do not restart or launch the bot yourself — you have no Kite credentials
  and no static IP whitelist; a cloud-started bot would be broken and
  non-compliant.
- Do not modify `logs/bot_heartbeat.json` — it is written exclusively by
  the local launcher.
- Do not escalate alerts to email/SMS/PagerDuty without explicit user
  request.
