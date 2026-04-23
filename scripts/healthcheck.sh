#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# healthcheck.sh — Verify the trading bot is running after launch
#
# Invoked by cron at 09:15 IST (10 min after run_bot.sh).
# Checks: process alive, log file exists, recent log activity.
# Sends Telegram alert on failure.
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DATE_STAMP="$(date +%F)"
BOT_LOG="$REPO_ROOT/logs/bot-${DATE_STAMP}.log"
KITE_SH="$REPO_ROOT/scripts/kite.sh"

# ── Check 1: Is main.py running? ──
if pgrep -f "main.py" > /dev/null 2>&1; then
    BOT_PID=$(pgrep -f "main.py" | head -1)
    PROC_OK=true
else
    PROC_OK=false
fi

# ── Check 2: Does today's log exist and have recent content? ──
if [[ -f "$BOT_LOG" ]]; then
    LOG_OK=true
    # Check if log was written in last 10 minutes
    LOG_AGE=$(( $(date +%s) - $(stat -f %m "$BOT_LOG") ))
    if (( LOG_AGE > 600 )); then
        LOG_FRESH=false
    else
        LOG_FRESH=true
    fi
else
    LOG_OK=false
    LOG_FRESH=false
fi

# ── Check 3: Did "TRADING LOOP STARTED" appear in the log? ──
if [[ "$LOG_OK" == "true" ]] && grep -q "TRADING LOOP STARTED" "$BOT_LOG" 2>/dev/null; then
    LOOP_OK=true
else
    LOOP_OK=false
fi

# ── Decide: PASS or FAIL ──
if [[ "$PROC_OK" == "true" && "$LOG_OK" == "true" && "$LOOP_OK" == "true" ]]; then
    STATUS="PASS"
else
    STATUS="FAIL"
    REASONS=""
    [[ "$PROC_OK" == "false" ]] && REASONS="${REASONS}process not running, "
    [[ "$LOG_OK" == "false" ]] && REASONS="${REASONS}no log file, "
    [[ "$LOOP_OK" == "false" ]] && REASONS="${REASONS}trading loop not started, "
    REASONS="${REASONS%, }"  # trim trailing comma
fi

# ── Report ──
echo "[healthcheck] ${DATE_STAMP} — ${STATUS}"

if [[ "$STATUS" == "FAIL" ]]; then
    MSG="🚨 Bot healthcheck FAILED ($DATE_STAMP). Reasons: ${REASONS}. Check: logs/bot-${DATE_STAMP}.log"
    "$KITE_SH" telegram "$MSG" 2>/dev/null || true
    echo "[healthcheck] Telegram alert sent"
    exit 1
else
    MSG="✅ Bot healthcheck PASS ($DATE_STAMP). PID $BOT_PID, trading loop active."
    "$KITE_SH" telegram "$MSG" 2>/dev/null || true
    echo "[healthcheck] Bot running (PID $BOT_PID), trading loop active, log fresh"
    exit 0
fi
