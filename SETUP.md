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

## 8. Run the Bot (Paper Mode)

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

## 9. Schedule It to Run Daily (Optional)

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

## 10. Daily Operations

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

## 11. Going Live (DO NOT SKIP THE PAPER STAGE)

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

## 12. Troubleshooting

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

## 13. Backup Checklist

Back these up regularly (they contain your history, not credentials):
- `data/trades.db`
- `logs/audit/audit.jsonl`
- `logs/reports/` (exported CSVs)

**Never back up `config/.env`** to any shared location. Ever.

---

## 14. Directory Map (for reference)

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
