#!/usr/bin/env bash
# scripts/kite.sh — Thin curl wrapper for Zerodha Kite Connect REST API
# Usage: ./scripts/kite.sh <command> [args...]
#
# Commands:
#   profile              — User profile (good auth test)
#   account              — Margins and available cash
#   positions            — Current day + net positions
#   holdings             — Delivery holdings
#   quote SYM1,SYM2      — LTP + OHLC for symbols (auto-prefixed NSE:)
#   orders               — Today's order list
#   order BUY|SELL SYM QTY [PRICE] — Place MIS order (market or limit)
#   cancel ORDER_ID      — Cancel an open order
#   telegram MSG          — Send message via Telegram bot
#
# Reads credentials from config/.env and config/.access_token
# Requires: curl, python3 (for JSON pretty-print and token parsing)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Load credentials ──────────────────────────────────────────────

ENV_FILE="$REPO_ROOT/config/.env"
TOKEN_FILE="$REPO_ROOT/config/.access_token"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found. Copy config/.env.example and fill it in." >&2
  exit 2
fi

# Source env vars (handles lines like KEY=value, ignores comments)
# Note: use temp file instead of <(...) — process substitution is unreliable
# with `source` on macOS bash when combined with set -a.
_ENV_TMP=$(mktemp)
grep -v '^\s*#' "$ENV_FILE" | grep -v '^\s*$' > "$_ENV_TMP"
set -a
# shellcheck disable=SC1090
source "$_ENV_TMP"
set +a
rm -f "$_ENV_TMP"

API_KEY="${KITE_API_KEY:-}"
if [[ -z "$API_KEY" ]]; then
  echo "ERROR: KITE_API_KEY not set in $ENV_FILE" >&2
  exit 2
fi

# Parse access_token from JSON file: {"date": "...", "access_token": "..."}
if [[ ! -f "$TOKEN_FILE" ]]; then
  echo "ERROR: $TOKEN_FILE not found. Run: python scripts/refresh_kite_token.py" >&2
  exit 2
fi

ACCESS_TOKEN=$(python3 -c "import json; print(json.load(open('$TOKEN_FILE'))['access_token'])" 2>/dev/null)
if [[ -z "$ACCESS_TOKEN" ]]; then
  echo "ERROR: Could not parse access_token from $TOKEN_FILE" >&2
  exit 2
fi

# ── API setup ─────────────────────────────────────────────────────

BASE_URL="https://kite.zerodha.com/oms"
AUTH_HEADER="Authorization: enctoken ${ACCESS_TOKEN}"
VERSION_HEADER="X-Kite-Version: 3"

# Trading mode (paper = safe, live = requires --confirm for orders)
MODE="${TRADING_MODE:-paper}"

# Telegram config
TG_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TG_CHAT="${TELEGRAM_CHAT_ID:-}"

# ── Helper functions ──────────────────────────────────────────────

pretty_json() {
  python3 -m json.tool 2>/dev/null || cat
}

kite_get() {
  local endpoint="$1"
  curl -s -H "$AUTH_HEADER" -H "$VERSION_HEADER" "${BASE_URL}${endpoint}" | pretty_json
}

kite_post() {
  local endpoint="$1"
  shift
  curl -s -X POST -H "$AUTH_HEADER" -H "$VERSION_HEADER" "$@" "${BASE_URL}${endpoint}" | pretty_json
}

kite_delete() {
  local endpoint="$1"
  curl -s -X DELETE -H "$AUTH_HEADER" -H "$VERSION_HEADER" "${BASE_URL}${endpoint}" | pretty_json
}

# ── Commands ──────────────────────────────────────────────────────

cmd_profile() {
  echo "── User Profile ──"
  kite_get "/user/profile"
}

cmd_account() {
  echo "── Account Margins ──"
  kite_get "/user/margins"
}

cmd_positions() {
  echo "── Positions ──"
  kite_get "/portfolio/positions"
}

cmd_holdings() {
  echo "── Holdings ──"
  kite_get "/portfolio/holdings"
}

cmd_quote() {
  local symbols="$1"
  # Build query string: split on comma, prefix each with NSE:
  local query=""
  IFS=',' read -ra SYMS <<< "$symbols"
  for sym in "${SYMS[@]}"; do
    sym=$(echo "$sym" | tr -d '[:space:]' | tr '[:lower:]' '[:upper:]')
    if [[ -n "$query" ]]; then
      query="${query}&i=NSE:${sym}"
    else
      query="i=NSE:${sym}"
    fi
  done
  echo "── Quote: $symbols ──"
  kite_get "/quote?${query}"
}

cmd_orders() {
  echo "── Today's Orders ──"
  kite_get "/orders"
}

cmd_order() {
  local txn_type="${1:-}"
  local symbol="${2:-}"
  local qty="${3:-}"
  local price="${4:-}"

  if [[ -z "$txn_type" || -z "$symbol" || -z "$qty" ]]; then
    echo "Usage: kite.sh order BUY|SELL SYMBOL QTY [PRICE]" >&2
    exit 1
  fi

  txn_type=$(echo "$txn_type" | tr '[:lower:]' '[:upper:]')
  symbol=$(echo "$symbol" | tr '[:lower:]' '[:upper:]')

  # Safety check: require --confirm for live mode
  if [[ "$MODE" == "live" ]]; then
    if [[ "${5:-}" != "--confirm" ]]; then
      echo "SAFETY: Live mode requires --confirm flag." >&2
      echo "  kite.sh order $txn_type $symbol $qty ${price:+$price }--confirm" >&2
      exit 1
    fi
  fi

  local order_type="MARKET"
  local form_data="-d exchange=NSE -d tradingsymbol=${symbol} -d transaction_type=${txn_type} -d quantity=${qty} -d product=MIS -d validity=DAY"

  if [[ -n "$price" && "$price" != "--confirm" ]]; then
    order_type="LIMIT"
    form_data="${form_data} -d order_type=LIMIT -d price=${price}"
  else
    form_data="${form_data} -d order_type=MARKET"
  fi

  # Add SEBI algo tag if set
  local algo_id="${ALGO_ID:-}"
  if [[ -n "$algo_id" ]]; then
    form_data="${form_data} -d tag=${algo_id}"
  fi

  echo "── Place Order: $txn_type $symbol x$qty ($order_type) [mode=$MODE] ──"
  eval kite_post "/orders/regular" "$form_data"
}

cmd_cancel() {
  local order_id="${1:-}"
  if [[ -z "$order_id" ]]; then
    echo "Usage: kite.sh cancel ORDER_ID" >&2
    exit 1
  fi

  # Safety check: require --confirm for live mode
  if [[ "$MODE" == "live" ]]; then
    if [[ "${2:-}" != "--confirm" ]]; then
      echo "SAFETY: Live mode requires --confirm flag." >&2
      echo "  kite.sh cancel $order_id --confirm" >&2
      exit 1
    fi
  fi

  echo "── Cancel Order: $order_id [mode=$MODE] ──"
  kite_delete "/orders/regular/${order_id}"
}

cmd_telegram() {
  local msg="${1:-}"
  if [[ -z "$msg" ]]; then
    echo "Usage: kite.sh telegram \"Your message here\"" >&2
    exit 1
  fi
  if [[ -z "$TG_TOKEN" || -z "$TG_CHAT" ]]; then
    echo "WARNING: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set in $ENV_FILE" >&2
    echo "Message (not sent): $msg"
    exit 0
  fi

  echo "── Sending Telegram ──"
  curl -s -X POST "https://api.telegram.org/bot${TG_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${TG_CHAT}" \
    --data-urlencode "text=${msg}" \
    -d "parse_mode=Markdown" | pretty_json
}

# ── Dispatch ──────────────────────────────────────────────────────

CMD="${1:-help}"
shift || true

case "$CMD" in
  profile)    cmd_profile ;;
  account)    cmd_account ;;
  positions)  cmd_positions ;;
  holdings)   cmd_holdings ;;
  quote)      cmd_quote "${1:-}" ;;
  orders)     cmd_orders ;;
  order)      cmd_order "$@" ;;
  cancel)     cmd_cancel "$@" ;;
  telegram)   cmd_telegram "$*" ;;
  help|*)
    echo "scripts/kite.sh — Zerodha Kite Connect API wrapper"
    echo ""
    echo "Commands:"
    echo "  profile              User profile (auth test)"
    echo "  account              Margins and available cash"
    echo "  positions            Current positions"
    echo "  holdings             Delivery holdings"
    echo "  quote SYM1,SYM2     LTP + OHLC (NSE: auto-prefix)"
    echo "  orders               Today's orders"
    echo "  order BUY|SELL SYM QTY [PRICE]  Place MIS order"
    echo "  cancel ORDER_ID     Cancel an open order"
    echo "  telegram \"MSG\"      Send Telegram message"
    ;;
esac
