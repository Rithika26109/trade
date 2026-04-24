#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# run_bot.sh — daily launcher for the trading bot
#
# Invoked by cron at 09:05 IST on weekdays. Writes a heartbeat file
# (pushed to GitHub so the cloud "bot-healthcheck" routine can verify
# we started), holds the Mac awake with `caffeinate` for the duration
# of market hours, then execs main.py in paper mode.
#
# Bot mode is hard-coded to PAPER here on purpose — promoting to live
# requires an explicit edit of this file.
# ─────────────────────────────────────────────────────────────────────
set -u

REPO_DIR="/Users/rithika-18920/Documents/aiaiai/serious/trade"
MODE="paper"
LOG_DIR="$REPO_DIR/logs"
DATE_STAMP="$(date +%F)"
BOT_LOG="$LOG_DIR/bot-${DATE_STAMP}.log"
HEARTBEAT="$LOG_DIR/bot_heartbeat.json"

cd "$REPO_DIR" || { echo "cannot cd to $REPO_DIR" >&2; exit 1; }

# Activate venv if present (cron has a bare PATH).
if [ -f ".venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    . ".venv/bin/activate"
fi

mkdir -p "$LOG_DIR"

# ── Prevent double-launch (e.g. manual run while cron is active). ──
PIDFILE="$LOG_DIR/bot.pid"
if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "[run_bot] Already running (pid=$(cat "$PIDFILE")). Aborting." >&2
    exit 0
fi
echo $$ > "$PIDFILE"

# ── Heartbeat: written before anything that might fail, so even if
#    the bot dies during setup, the routine can still see we tried. ──
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
HOSTNAME_SHORT="$(hostname -s 2>/dev/null || hostname)"

cat > "$HEARTBEAT" <<EOF
{
  "started_at": "$STARTED_AT",
  "mode": "$MODE",
  "host": "$HOSTNAME_SHORT",
  "pid": $$,
  "log_file": "logs/bot-${DATE_STAMP}.log"
}
EOF

# Best-effort push. Never fail the launch if git hiccups.
{
    git add "$HEARTBEAT" \
      && git -c user.name="trade-bot" -c user.email="bot@localhost" \
            commit -m "heartbeat: ${DATE_STAMP}" --quiet \
      && git push --quiet
} || echo "[run_bot] heartbeat git push failed (non-fatal)" >&2

# ── Keep the Mac awake for ~6h40m (covers 09:05 → 15:45 IST). ──
# -i: prevent idle sleep. -t seconds (24000 = 6h40m).
caffeinate -i -t 24000 &
CAFFEINATE_PID=$!
trap 'rm -f "$PIDFILE"; kill "$CAFFEINATE_PID" 2>/dev/null || true' EXIT

echo "[run_bot] $(date) launching main.py --${MODE} (caffeinate pid=$CAFFEINATE_PID)" \
    | tee -a "$BOT_LOG"

# exec replaces this shell, so the trap still fires on SIGTERM/SIGINT.
exec python main.py --"${MODE}" >> "$BOT_LOG" 2>&1
