# 🐂 Bull

**Bull** is an automated intraday trading bot for Indian equity markets (NSE/BSE), built on top of the Zerodha Kite Connect API. It combines multi-strategy signal generation, strict risk management, and SEBI-compliant execution — with a paper-trading mode so you can validate everything before putting real capital on the line.

---

## Features

- **Multi-strategy engine** — Opening Range Breakout (ORB), RSI + EMA crossover, VWAP + Supertrend, with a confluence orchestrator that ranks and filters signals.
- **Market-regime aware** — Detects trending vs. ranging conditions and adapts strategy selection.
- **Risk-first execution** — Per-trade risk caps (1–2%), daily loss limits (3%), max 5 trades/day, position sizing, and a kill switch.
- **Paper + live modes** — Same code path, simulated fills in paper mode against real market data.
- **Compliance built-in** — Algo-ID tagging, rate limiting, order audit trail (SEBI April 2026 ready).
- **Full observability** — SQLite trade log, CSV exports, JSONL audit log, Telegram notifications, daily journal.
- **Scheduled automation** — cron + cloud healthchecks handle daily token refresh, startup, EOD commit, and review.
- **Backtesting suite** — `backtesting.py` integration plus walk-forward and Monte Carlo validation.

---

## Quick Start

### 1. Install

```bash
git clone <your-repo-url> bull
cd bull
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp config/.env.example config/.env
# Fill in Kite API key/secret, Telegram token, etc.
```

See [docs/SETUP.md](docs/SETUP.md) for full environment setup (Kite app registration, TOTP, IP whitelisting).

### 3. Backtest

```bash
python backtest/run_backtest.py
```

### 4. Run in paper mode

```bash
python main.py --paper
```

### 5. Go live (only after thorough paper testing)

```bash
python main.py --live
```

---

## Project Structure

```
bull/
├── main.py                    # Entry point — orchestrates the trading day
├── config/                    # Settings, daily plan schema
├── src/
│   ├── auth/                  # Kite login + TOTP
│   ├── data/                  # REST + WebSocket market data
│   ├── indicators/            # TA indicators, regime detection
│   ├── scanner/               # Universe filtering, liquidity checks
│   ├── strategy/              # ORB, RSI+EMA, VWAP+ST, orchestrator
│   ├── risk/                  # Position sizing, daily caps, kill switch
│   ├── execution/             # Order + position management
│   └── utils/                 # Logger, notifier, audit, DB, compliance
├── backtest/                  # Backtest runner, walk-forward, Monte Carlo
├── scripts/                   # Cron jobs, token refresh, EOD commit, smoke tests
├── tests/                     # Unit + integration tests
├── memory/                    # Persistent trading memory (strategy, trade log, research)
├── logs/                      # Trade journal, reports, audit trail
└── docs/                      # All documentation
```

---

## Documentation

| Doc | What's inside |
|---|---|
| [01-TRADING-FUNDAMENTALS.md](docs/01-TRADING-FUNDAMENTALS.md) | Trading basics, terminology, indicators |
| [02-TRADING-STRATEGIES.md](docs/02-TRADING-STRATEGIES.md) | ORB, RSI+EMA, MACD+BB, VWAP+Supertrend details |
| [03-ZERODHA-KITE-API-GUIDE.md](docs/03-ZERODHA-KITE-API-GUIDE.md) | Kite Connect API reference |
| [04-RISK-MANAGEMENT.md](docs/04-RISK-MANAGEMENT.md) | Risk rules, position sizing, circuit breakers |
| [05-TECH-STACK-AND-ARCHITECTURE.md](docs/05-TECH-STACK-AND-ARCHITECTURE.md) | Architecture, lifecycle, config |
| [06-BACKTESTING-GUIDE.md](docs/06-BACKTESTING-GUIDE.md) | Backtesting methodology and metrics |
| [07-REALISTIC-EXPECTATIONS.md](docs/07-REALISTIC-EXPECTATIONS.md) | Returns, tax, safety checklist |
| [08-HOW-TO-USE.md](docs/08-HOW-TO-USE.md) | Day-to-day operating guide |
| [09-CLAUDE-ROUTINES-SETUP.md](docs/09-CLAUDE-ROUTINES-SETUP.md) | Automated routines + cron setup |
| [10-ZERODHA-KITE-CONNECT-DEEP-DIVE.md](docs/10-ZERODHA-KITE-CONNECT-DEEP-DIVE.md) | Kite API internals |
| [SETUP.md](docs/SETUP.md) | First-time setup |

---

## Tech Stack

- **Python 3.10+**
- **Broker:** Zerodha Kite Connect (`pykiteconnect`)
- **Data & TA:** pandas, numpy, pandas-ta
- **Backtesting:** backtesting.py
- **Scheduling:** APScheduler + cron
- **Logging:** loguru
- **Auth:** pyotp (TOTP auto-login)
- **DB:** SQLite
- **Notifications:** python-telegram-bot

---

## Daily Lifecycle

| Time (IST) | What happens |
|---|---|
| 06:30 | `scripts/refresh_kite_token.py` rotates the Kite access token |
| 09:05 | `scripts/run_bot.sh` writes heartbeat, starts `caffeinate`, execs `main.py --paper` |
| 09:15 | Market opens — bot collects opening range |
| 09:20 | Cloud healthcheck verifies heartbeat |
| 09:30 | Strategy loop goes active |
| 15:15 | Bot stops taking new entries |
| 15:20 | Square off all open positions |
| 15:35 | `scripts/eod_commit.py` pushes journal + metrics |
| 16:30 | Cloud routine grades the day |

---

## Risk Rules (defaults)

- **Max risk per trade:** 1–2% of capital
- **Max daily loss:** 3% (bot stops trading for the day)
- **Max trades/day:** 5
- **Stop-loss:** mandatory on every trade
- **Sector exposure cap:** configurable per-sector ceiling
- **Kill switch:** flat-all + halt on repeated errors or loss breach

Edit [config/settings.py](config/settings.py) to tune these.

---

## Shell Wrapper

`scripts/kite.sh` — fast Kite REST calls without booting Python:

```bash
scripts/kite.sh profile                    # Auth test
scripts/kite.sh account                    # Margins and cash
scripts/kite.sh positions                  # Current positions
scripts/kite.sh quote RELIANCE,TCS         # LTP + OHLC
scripts/kite.sh orders                     # Today's orders
scripts/kite.sh order BUY INFY 10          # Place MIS order
scripts/kite.sh cancel ORDER_ID            # Cancel
scripts/kite.sh telegram "Deployed ✅"      # Send Telegram message
```

---

## Testing

```bash
pytest                         # Run all tests
pytest tests/test_risk_manager.py -v
pytest -k phase3               # Run phase-tagged suites
```

---

## Safety & Compliance

- **SEBI April 2026:** Algo-ID required for all algorithmic orders, static IP whitelisting enforced. Bull tags every order with an Algo-ID and rate-limits to stay under 10 orders/sec.
- **Secrets:** Never committed. All API keys live in `.env` (gitignored).
- **Pre-flight:** `scripts/preflight.py` runs sanity checks before market open.
- **Smoke test:** `scripts/smoke_paper.py` validates the full pipeline in paper mode.

---

## Disclaimer

Bull is a personal trading tool. Intraday trading carries substantial risk of loss. Past performance (including backtests) does not guarantee future results. You are solely responsible for any trades placed through this bot. Always paper-trade thoroughly before deploying real capital, and never risk money you cannot afford to lose.

---

## License

Private / personal use.
