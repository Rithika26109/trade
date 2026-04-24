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

echo "--- [$(date '+%Y-%m-%d %H:%M:%S')] CRON START: /$CMD (model=$MODEL, pid=$$) ---"

/opt/homebrew/bin/claude -p "/$CMD" --dangerously-skip-permissions --model "$MODEL" "$@"
EXIT_CODE=$?

echo "--- [$(date '+%Y-%m-%d %H:%M:%S')] CRON END: /$CMD (exit=$EXIT_CODE) ---"

exit $EXIT_CODE
