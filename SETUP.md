# Setup Guide — Running the Trading Bot

A zero-to-running checklist for installing and operating the bot on a fresh machine. Target: **paper-mode first**, live only after 20+ paper sessions.

---

## 0. Requirements

| | |
|---|---|
| **OS** | macOS, Linux, or Windows (WSL2 recommended for Windows) |
| **Python** | 3.10 or newer (3.13 tested) |
| **RAM** | 2 GB free |
| **Disk** | 500 MB for code + ~50 MB/month of logs |
| **Network** | Stable internet, **static public IP** (required for SEBI live compliance) |
| **Zerodha** | Active trading account + **Kite Connect developer app** (Rs 2,000/month for live) |

---

## 1. Install Python

### macOS
```bash
brew install python@3.13
python3 --version   # should print 3.10+
```

### Ubuntu / Debian
```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip
python3 --version
```

### Windows
1. Download from https://www.python.org/downloads/
2. **Check "Add Python to PATH"** during install
3. Verify in PowerShell: `python --version`

---

## 2. Get the Code

```bash
# Clone (if using git)
git clone <your-repo-url> trading-bot
cd trading-bot

# OR copy the project folder to your target machine
cp -R /path/to/trade ~/trading-bot
cd ~/trading-bot
```

---

## 3. Create a Virtual Environment

Keeps the bot's dependencies isolated from system Python.

```bash
python3 -m venv .venv

# Activate (macOS / Linux)
source .venv/bin/activate

# Activate (Windows PowerShell)
.venv\Scripts\Activate.ps1
```

You should see `(.venv)` at the start of your prompt.

---

## 4. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

This installs `kiteconnect`, `pandas`, `pandas-ta`, `backtesting`, `apscheduler`, `loguru`, `pyotp`, `python-dotenv`, `pytest` and friends.

Verify:
```bash
python3 -c "import kiteconnect, pandas, pandas_ta; print('deps OK')"
```

---

## 5. Create Zerodha Kite Connect App

1. Log in at **https://developers.kite.trade/**
2. Click **"Create new app"**
3. Fill in:
   - **App name:** anything, e.g., `my-intraday-bot`
   - **Redirect URL:** `http://127.0.0.1/` (for personal use)
   - **Postback URL:** leave blank
4. Pay the monthly subscription (required for live; free for 1 day trial)
5. Copy down:
   - `api_key`
   - `api_secret`
6. Enable **TOTP-based 2FA** on your Kite account (Profile → Security → 2FA)
   - When you set it up, Zerodha shows a QR code and a **secret string** (looks like `JBSWY3DPEHPK3PXP`)
   - **Save this secret string.** You will put it in `.env` for auto-login.

---

## 6. Configure Secrets

Create **`config/.env`** (this file is git-ignored; never commit it):

```env
# ── Zerodha ──
KITE_API_KEY=your_api_key_here
KITE_API_SECRET=your_api_secret_here
KITE_USER_ID=AB1234
KITE_TOTP_SECRET=your_totp_secret_here

# ── Trading mode ──
# Start with "paper". Only switch to "live" after 20+ successful paper sessions.
TRADING_MODE=paper

# ── SEBI compliance (April 2026) ──
# 1–20 chars, alphanumeric + underscore. Required in live mode.
ALGO_ID=MYBOT01

# Your registered static public IP. Get it with: curl https://api.ipify.org
# Leave empty to skip the pin check (paper only).
STATIC_IP_EXPECTED=

# ── Optional notifications ──
TELEGRAM_ENABLED=false
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

**Find your public IP:**
```bash
curl https://api.ipify.org
```
Put that value in `STATIC_IP_EXPECTED` once you have a static IP from your ISP (or a cloud VM).

**Lock down the `.env` file** — it contains your API secret and TOTP seed. On macOS/Linux:
```bash
chmod 600 config/.env
```
The bot itself will `chmod 0600` the access-token cache (`config/.access_token`), the trade DB (`data/trades.db`), and the audit log. Never sync `config/` to cloud storage, and the Zerodha password is always prompted at runtime — it is never read from `.env` or process environment.

---

## 7. Verify Installation

```bash
# Run the full test suite — expect 110 passed
python3 -m pytest tests/ -q

# Run the paper-mode smoke harness — expect "SMOKE OK"
python3 scripts/smoke_paper.py

# Run the pre-flight check — expect PASS on every line
python3 scripts/preflight.py --mode paper
```

If any of these fail, **stop** and fix before proceeding.

---

## 8. Choose Which Stocks to Trade

The bot never trades the whole market. It works off a **watchlist**, then applies a **scanner** that picks the best subset each morning. Both are configurable in `config/settings.py`.

### 8.1 The watchlist — your pool of candidates

Open `config/settings.py` and look for `WATCHLIST`. The default ships with 10 NIFTY-50 large caps:

```python
WATCHLIST = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "SBIN", "BHARTIARTL", "ITC", "KOTAKBANK", "LT",
]
```

**Rules for adding symbols:**
- Use the **NSE tradingsymbol** exactly as Zerodha spells it (e.g., `BAJAJ-AUTO`, `M&M`, `TATAMOTORS`)
- Stick to large caps for intraday. Minimum criteria:
  - Average daily volume ≥ 1 M shares
  - Price between Rs 100 and Rs 5,000 (matches `MIN_PRICE` / `MAX_PRICE`)
  - Available for intraday MIS product at Zerodha
  - Part of NIFTY 500 ideally (better liquidity, tighter spreads)
- Keep the list to **10–25 names**. More than that dilutes the scanner and hits API rate limits.
- **Add one sector at a time.** The sector cap (`MAX_POSITIONS_PER_SECTOR = 1`) means adding 5 banks only ever yields 1 bank trade — redundant watchlist bloat.

**Recommended starter sectors** (pick 1–2 names each):

| Sector | Strong liquid names |
|---|---|
| Banks | HDFCBANK, ICICIBANK, SBIN, KOTAKBANK, AXISBANK |
| IT | TCS, INFY, HCLTECH, WIPRO |
| Energy | RELIANCE, ONGC, NTPC, POWERGRID |
| Auto | TATAMOTORS, M&M, MARUTI, BAJAJ-AUTO |
| FMCG | ITC, HINDUNILVR, NESTLEIND |
| Metals | TATASTEEL, HINDALCO, JSWSTEEL |
| Pharma | SUNPHARMA, DRREDDY, CIPLA |
| Telecom | BHARTIARTL |

After editing, re-run the test suite to make sure nothing regressed:
```bash
python3 -m pytest tests/ -q
```

### 8.2 The scanner — picks today's top-N from your watchlist

Every morning the scanner scores each watchlist name and trades only the top few. The ranking uses five weighted signals:

| Weight | Signal | What it measures |
|---|---|---|
| `SCANNER_VOLUME_WEIGHT` (0.20) | Volume | Today's volume vs 20-day average |
| `SCANNER_VOLATILITY_WEIGHT` (0.20) | Volatility | ATR % — need movement to profit |
| `SCANNER_MOMENTUM_WEIGHT` (0.25) | Momentum | 5-day + 20-day rate of change |
| `SCANNER_RS_WEIGHT` (0.20) | Relative strength | Outperformance vs NIFTY 50 |
| `SCANNER_SECTOR_WEIGHT` (0.15) | Sector strength | Is the stock's sector leading today? |

Tunables in `config/settings.py`:

```python
SCANNER_TOP_N = 5                   # only trade the top 5 ranked names
SCANNER_DROP_CIRCUIT_FROZEN = True  # skip stocks frozen at upper/lower circuit
SCANNER_MIN_TURNOVER_CR = 5.0       # Rs 5 crore/day minimum turnover
SCANNER_MAX_SPREAD_BPS = 5.0        # max bid-ask spread (5 bps = 0.05%)
```

**How to change the selection behaviour:**
- **Trade fewer names** (more focused): set `SCANNER_TOP_N = 3`
- **Trade more names**: set `SCANNER_TOP_N = 8`, and raise `MAX_OPEN_POSITIONS` (default 2)
- **Prefer trending moves**: bump `SCANNER_MOMENTUM_WEIGHT` to 0.35, reduce volatility
- **Prefer breakouts**: bump `SCANNER_VOLATILITY_WEIGHT` to 0.30
- **Ignore small stocks**: raise `SCANNER_MIN_TURNOVER_CR` to 20+
- **Disable the scanner entirely** (trade the top of the watchlist as-is): set `SCANNER_TOP_N = 0`

### 8.3 Filters applied *after* scoring

Even if a stock scores highest, it is dropped when any of these fail:
- Frozen at circuit today (no fills possible)
- Turnover < `SCANNER_MIN_TURNOVER_CR` (illiquid)
- Bid-ask spread > `SCANNER_MAX_SPREAD_BPS` (too wide — slippage kills R:R)
- Price outside `[MIN_PRICE, MAX_PRICE]` band
- Sector already has `MAX_POSITIONS_PER_SECTOR` open trades

### 8.4 Inspect what the scanner picked

After the bot runs (or even during), you can see the scanner's picks in `logs/` — look for lines like:
```
Scanning 10 stocks...
  RELIANCE: score=72.30 (vol=85, atr=68, mom=75, rs=70, sec=60)
  TCS:      score=65.40 ...
Today's watchlist: ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK']
```

Or in the exported audit CSV (`logs/reports/<date>/audit_*.csv`).

### 8.5 Rules of thumb

1. **Start small.** First 5 paper sessions, use the default 10-stock watchlist, `SCANNER_TOP_N = 5`. Don't tune anything.
2. **One change at a time.** Change watchlist OR scanner weights — never both in the same session. You won't know which move helped.
3. **Don't cherry-pick today's hot stock.** That's survivorship bias. Let the scanner earn its score.
4. **Review monthly.** Pull the exported trades CSV, group by symbol, check which ones net-made money and which consistently lost. Drop chronic losers from the watchlist.
5. **No F&O, no penny stocks.** The bot is tuned for cash-segment intraday on NSE large/mid caps only.

---

## 9. Run the Bot (Paper Mode)

Paper mode simulates trades against real market data — no real money moves.

```bash
# Make sure it is a trading day (market-day check will exit early on weekends/holidays)
python3 main.py --paper
```

The bot will:
1. Log in to Zerodha (TOTP auto-submitted)
2. Scan stocks at 9:15 AM IST
3. Collect opening range until 9:30 AM
4. Trade until 3:00 PM (new entries)
5. Flatten everything at 3:15 PM
6. Print a daily report + save to SQLite

Logs stream to `logs/` and trades to `data/trades.db`.

---

## 10. Schedule It to Run Daily (Optional)

### macOS / Linux — cron

Edit your crontab: `crontab -e`

```cron
# Start the bot at 9:10 AM IST every weekday (Mon-Fri)
10 9 * * 1-5 cd /home/you/trading-bot && /home/you/trading-bot/.venv/bin/python main.py --paper >> logs/cron.log 2>&1

# Nightly CSV export at 6:00 PM IST
0 18 * * 1-5 cd /home/you/trading-bot && /home/you/trading-bot/.venv/bin/python scripts/export_nightly.py --days 1
```

Make sure your system clock is set to **IST** (`sudo timedatectl set-timezone Asia/Kolkata` on Linux).

### macOS — launchd (alternative)

Create `~/Library/LaunchAgents/com.trading-bot.daily.plist`. (Ask for a template if needed.)

### Windows — Task Scheduler

1. Open **Task Scheduler** → Create Basic Task
2. Trigger: Daily at 09:10, recur Mon–Fri
3. Action: Start a program
   - Program: `C:\path\to\trading-bot\.venv\Scripts\python.exe`
   - Arguments: `main.py --paper`
   - Start in: `C:\path\to\trading-bot`

---

## 11. Daily Operations

### Before every session
```bash
python3 scripts/preflight.py --mode paper --with-tests
```
Must exit 0. If red, do **not** start the bot.

### During the session — emergency halt
```bash
touch .kill_switch
```
The bot will flatten all positions on the next cycle and exit.
Remove with `rm .kill_switch` before the next run.

### After the session
```bash
python3 scripts/export_nightly.py --days 1
# CSVs land in logs/reports/YYYY-MM-DD/
```

Open these in Excel / Google Sheets to review:
- `trades_since_*.csv` — every fill with entry/exit/P&L
- `daily_summary_since_*.csv` — aggregate metrics
- `audit_since_*.csv` — every broker-facing event (placements, SLM lifecycle, reconcile drifts, kill-switch events)

---

## 12. Going Live (DO NOT SKIP THE PAPER STAGE)

Switch to live only after:
- [ ] ≥ 20 paper sessions completed
- [ ] Positive net P&L after realistic costs
- [ ] Zero `reconcile_drift` events in the audit CSV
- [ ] Zero `slm_place_failed` / `slm_lost` events
- [ ] Win rate and R:R on the exported CSVs match your backtest expectations

Then:
1. Register your static IP with Zerodha support (SEBI algo rules, April 2026)
2. Set `STATIC_IP_EXPECTED=<your-ip>` in `.env`
3. Set `TRADING_MODE=live`
4. Set a valid `ALGO_ID`
5. Run preflight in live mode:
   ```bash
   python3 scripts/preflight.py --mode live --with-tests
   ```
6. **Reduce capital** in `config/settings.py` → `INITIAL_CAPITAL` to something you can afford to lose for week 1
7. Launch: `python3 main.py --live`

---

## 13. Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: kiteconnect` | Activate the venv (`source .venv/bin/activate`) and re-run `pip install -r requirements.txt` |
| Login loops / TOTP fails | Re-scan your TOTP QR; make sure `KITE_TOTP_SECRET` has no spaces |
| `ComplianceError: ALGO_ID invalid` | Set a valid `ALGO_ID` in `.env` (1–20 chars, `A-Z`, `a-z`, `0-9`, `_`) |
| Preflight fails `env_vars` | You missed a key in `config/.env` — fill all four Zerodha vars |
| `reconcile_drift` at startup (live) | Log in to Kite web, flatten or square-off manually, then restart |
| Bot refuses to start with exit code 4 | Kill-switch is engaged: `rm .kill_switch` |
| Exit code 3 | Compliance gate failed — read the log line above it |
| Orders placed but never filled | Check market hours, liquidity of the symbol, and your stop/target aren't outside circuit limits |
| `backtesting` import error in preflight | Only needed for backtest scripts; preflight treats it as soft-optional |

---

## 14. Backup Checklist

Back these up regularly (they contain your history, not credentials):
- `data/trades.db`
- `logs/audit/audit.jsonl`
- `logs/reports/` (exported CSVs)

**Never back up `config/.env`** to any shared location. Ever.

---

## 15. Directory Map (for reference)

```
trading-bot/
├── main.py                  # entry point
├── config/
│   ├── settings.py          # all tunables
│   └── .env                 # secrets (create this, never commit)
├── src/                     # bot internals
├── scripts/
│   ├── preflight.py         # pre-run go/no-go
│   ├── smoke_paper.py       # end-to-end sanity
│   └── export_nightly.py    # daily CSV dump
├── backtest/                # backtest runners
├── tests/                   # pytest suite
├── data/trades.db           # created on first run
└── logs/                    # created on first run
```

---

**You're set. Run preflight, run the smoke test, then start paper mode. Review the CSVs every evening for at least a month before even thinking about live.**
