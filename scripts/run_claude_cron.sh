#!/usr/bin/env bash
# scripts/run_claude_cron.sh — Wrapper for cron-invoked Claude commands
# Logs entry/exit so we can diagnose silent failures.
#
# Usage: run_claude_cron.sh <command-name> [claude-args...]
#   command-name: the slash command without "/" (e.g. "pre-market", "midday")
#
# Example crontab entry:
#   3 8 * * 1-5 $REPO/scripts/run_claude_cron.sh pre-market >> $LOG/cron_premarket.log 2>&1

set -uo pipefail

CMD="${1:-}"
if [[ -z "$CMD" ]]; then
  echo "Usage: run_claude_cron.sh <command-name>" >&2
  exit 1
fi
shift

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Ensure HOME is set (cron sometimes drops it)
export HOME="${HOME:-/Users/rithika-18920}"

# Model: default sonnet, override with MODEL env var
MODEL="${MODEL:-sonnet}"

# Wait for network before invoking Claude API.
# Resolves api.anthropic.com via DNS; retries every 30s for up to 10 min.
# If still offline after the wait window, give up and let the run fail
# (it will be reported via the existing exit code logging).
wait_for_network() {
  local host="api.anthropic.com"
  local max_wait="${NETWORK_WAIT_SECS:-600}"   # 10 min default
  local interval=30
  local waited=0
  while ! /usr/bin/host -W 5 "$host" >/dev/null 2>&1; do
    if (( waited >= max_wait )); then
      echo "--- [$(date '+%Y-%m-%d %H:%M:%S')] NETWORK WAIT GAVE UP after ${waited}s (host=$host) ---"
      return 1
    fi
    echo "--- [$(date '+%Y-%m-%d %H:%M:%S')] WAITING FOR NETWORK ($host)… slept ${waited}s ---"
    sleep "$interval"
    waited=$(( waited + interval ))
  done
  if (( waited > 0 )); then
    echo "--- [$(date '+%Y-%m-%d %H:%M:%S')] NETWORK BACK after ${waited}s ---"
  fi
  return 0
}

echo "--- [$(date '+%Y-%m-%d %H:%M:%S')] CRON START: /$CMD (model=$MODEL, pid=$$) ---"

wait_for_network || true

# Route specific commands to their full routine file (which writes plan/journal
# and opens a PR) instead of the lightweight briefing slash-command.
# The routine markdown lives at .claude/routines/<file>.md.
ROUTINE_FILE=""
case "$CMD" in
  pre-market)    ROUTINE_FILE="$REPO_ROOT/.claude/routines/premarket.md"
                 MODEL="${MODEL_OVERRIDE:-opus}" ;;  # routine frontmatter prefers opus
  daily-summary) ROUTINE_FILE="$REPO_ROOT/.claude/routines/eod_review.md" ;;
  weekly-review) ROUTINE_FILE="$REPO_ROOT/.claude/routines/weekly_meta.md" ;;
esac

if [[ -n "$ROUTINE_FILE" && -f "$ROUTINE_FILE" ]]; then
  echo "--- [$(date '+%Y-%m-%d %H:%M:%S')] ROUTINE MODE: $ROUTINE_FILE ---"
  ROUTINE_BODY="$(cat "$ROUTINE_FILE")"
  PROMPT="Execute the following routine end-to-end. Follow every step including writing files, validating, committing, pushing, and opening a PR. The .env file is present locally — use it if needed. Do not skip step 7 (commit/push/PR).

---ROUTINE START---
${ROUTINE_BODY}
---ROUTINE END---"
  # SECURITY NOTE: --dangerously-skip-permissions is deliberate for
  # unattended cron — the routines write files, run git, and may invoke
  # `gh` to push branches. Anyone who can edit ROUTINE_FILE controls
  # what runs here, so:
  #   * Treat .claude/routines/*.md as code (PR review, no untrusted edits)
  #   * Keep this script + routine files under restrictive perms
  #   * Never invoke this wrapper with a CMD value that came from an
  #     untrusted source (it controls which routine file is loaded).
  /opt/homebrew/bin/claude -p "$PROMPT" --dangerously-skip-permissions --model "$MODEL" "$@"
else
  /opt/homebrew/bin/claude -p "/$CMD" --dangerously-skip-permissions --model "$MODEL" "$@"
fi
EXIT_CODE=$?

echo "--- [$(date '+%Y-%m-%d %H:%M:%S')] CRON END: /$CMD (exit=$EXIT_CODE) ---"

exit $EXIT_CODE
