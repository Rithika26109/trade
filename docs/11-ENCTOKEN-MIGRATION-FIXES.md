# Enctoken Migration — What Broke and What Was Fixed

Date: 2026-04-23

## Background

Zerodha removed the API endpoint for the "Authorize" step in their Connect flow. The old `request_token` redirect flow was completely broken. The fix was to switch to **enctoken auth** — extracting the `enctoken` cookie after login + TOTP and using it with `kite.zerodha.com/oms` endpoints.

This fixed authentication but broke several other things because the `/oms` server doesn't support all Kite API endpoints.

---

## What Broke and How It Was Fixed

### 1. `kite.sh` using wrong base URL and auth header

**Problem:** `kite.sh` was calling `api.kite.trade` with `Authorization: token api_key:access_token`. Enctoken auth requires a different URL and header format.

**Error:** `"Incorrect api_key or access_token" (TokenException)`

**Fix in** `scripts/kite.sh`:
```
# Before
BASE_URL="https://api.kite.trade"
AUTH_HEADER="Authorization: token ${API_KEY}:${ACCESS_TOKEN}"

# After
BASE_URL="https://kite.zerodha.com/oms"
AUTH_HEADER="Authorization: enctoken ${ACCESS_TOKEN}"
```

---

### 2. Instruments endpoint broken (`/oms/instruments` → Route not found)

**Problem:** `MarketData.load_instruments()` called `kite.instruments("NSE")` which hit `/oms/instruments/NSE`. The OMS server doesn't serve this endpoint.

**Error:** `Route not found`

**Fix in** `src/data/market_data.py` — `load_instruments()`:
- Changed to download the publicly available CSV from `https://api.kite.trade/instruments/NSE` (no auth needed)
- Falls back to `kite.instruments()` if the public URL fails

---

### 3. Quote/LTP endpoints broken (`/oms/quote` → Bad Request)

**Problem:** `MarketData.get_ltp()` called `kite.ltp()` which hit `/oms/quote/ltp`. The OMS server doesn't support quote endpoints.

**Error:** `Bad Request (InputException)`

**Fix in** `src/data/market_data.py` — `get_ltp()`:
- Tries `kite.ltp()` first
- Falls back to fetching the latest 1-minute historical candle close (which works on `/oms`)

**Note:** `get_quote()` is also broken but callers (`get_prev_close`, `get_circuit_limits`) already had graceful fallbacks — `get_prev_close` falls back to daily historical candles, `get_circuit_limits` returns None.

---

### 4. WebSocket infinite reconnect loop

**Problem:** `KiteTicker` WebSocket requires `api_key` + `access_token` for authentication. With enctoken, `access_token` is set to `""` so the WebSocket connection is rejected every time, causing infinite reconnect attempts that spam the log.

**Error:** `WebSocket connection upgrade failed (400 - BadRequest)` repeated forever

**Fix in** `main.py` — `_start_websocket()`:
- Added check: if `kite.access_token` is empty (enctoken mode), skip WebSocket entirely
- The polling loop in `_run_single_cycle()` handles price checks and exits via `get_ltp()` fallback

---

### 5. `python` command not found (only `python3` exists)

**Problem:** Multiple files used `python` instead of `python3`. On this Mac, only `python3` is installed.

**Error:** `command not found: python`

**Files fixed:**
- `.claude/commands/pre-market.md` — all `python scripts/...` → `python3 scripts/...`
- `main.py` line 656 — EOD commit subprocess call `["python", ...]` → `["python3", ...]`

---

### 6. Claude CLI not logged in

**Problem:** The cron at 8:03 AM runs `claude -p "/pre-market"` but Claude CLI had never been authenticated on this machine.

**Error:** `Not logged in · Please run /login`

**Fix:** One-time `claude login` from the terminal. Persists across sessions.

---

### 7. Missing Python packages

**Problem:** `google-genai`, `python-dotenv`, and `tqdm` were not installed in the system Python or venv.

**Errors:**
- `ModuleNotFoundError: No module named 'google'`
- `ModuleNotFoundError: No module named 'dotenv'`
- Scanner failing silently (missing `tqdm`)

**Fix:**
```bash
pip3 install google-genai python-dotenv tqdm
.venv/bin/pip install tqdm
```

---

### 8. Gemini model deprecated

**Problem:** `scripts/gemini_research.py` used `gemini-2.0-flash` which is being shut down.

**Fix in** `scripts/gemini_research.py`:
- Model: `gemini-2.0-flash` → `gemini-2.5-flash`
- Config: plain dict → `GenerateContentConfig` object
- Error handling: generic `Exception` with string matching → `genai_errors.ClientError` with `e.code == 429`
- Retry: flat 60s waits → exponential backoff (30s, 60s) with 30% random jitter

---

## Endpoints That Work vs Don't Work with Enctoken

| Endpoint | Works on /oms? | Used by |
|----------|---------------|---------|
| `/user/profile` | Yes | kite.sh, login verification |
| `/user/margins` | Yes | kite.sh, capital check |
| `/portfolio/positions` | Yes | kite.sh, position monitoring |
| `/orders` | Yes | kite.sh, order management |
| `/instruments/historical/{token}/{interval}` | Yes | All candle/OHLCV data |
| `/instruments` | **No** (Route not found) | Instrument lookup → fixed with public CSV |
| `/quote` | **No** (Bad Request) | LTP/quotes → fixed with historical fallback |
| `/quote/ltp` | **No** (Bad Request) | LTP → fixed with historical fallback |
| `/quote/ohlc` | **No** (Bad Request) | Not used directly |
| WebSocket (KiteTicker) | **No** (400) | Real-time ticks → skipped, using polling |

---

## Files Changed

| File | What changed |
|------|-------------|
| `src/auth/login.py` | Full rewrite — enctoken auth via login cookies |
| `src/data/market_data.py` | `load_instruments` → public CSV, `get_ltp` → historical fallback |
| `main.py` | Skip WebSocket when enctoken, `python` → `python3` in EOD |
| `scripts/kite.sh` | Base URL → `/oms`, auth header → `enctoken` |
| `scripts/gemini_research.py` | Model 2.5-flash, proper config/error types, exponential backoff |
| `scripts/healthcheck.sh` | New file — post-launch bot verification |
| `scripts/refresh_kite_token.py` | Telegram notifications on success/failure |
| `scripts/premarket_context.py` | Enctoken compatibility for cloud env |
| `.claude/commands/pre-market.md` | `python` → `python3`, Gemini script integration |
| `.claude/commands/market-open.md` | Telegram instructions added |
| `.claude/commands/midday.md` | Telegram instructions added |
| `.claude/routines/premarket.md` | Gemini script integration |
| `config/settings.py` | Added `KITE_PASSWORD` |
| `requirements.txt` | Added `google-genai>=1.0` |
| `requirements-routine.txt` | Changed to `google-genai>=1.0` |
