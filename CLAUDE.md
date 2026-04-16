# Trading Bot Project — CLAUDE.md

## Project Overview
Building an automated intraday (day trading) bot for Indian stock markets (NSE/BSE) using Python and Zerodha Kite Connect APIs. The user is a complete beginner in trading.

## Tech Stack
- **Language:** Python 3.10+
- **Broker API:** Zerodha Kite Connect (`pykiteconnect`)
- **Data:** pandas, numpy
- **Indicators:** pandas-ta (preferred over ta-lib for easier installation)
- **Backtesting:** backtesting.py
- **Scheduling:** APScheduler
- **Logging:** loguru
- **Auth:** pyotp (for TOTP auto-login)
- **Config:** python-dotenv (.env for secrets)
- **Database:** SQLite (trade logs)
- **Notifications:** python-telegram-bot (optional)

## Key Architecture Decisions
- Modular structure: auth, data, strategy, execution, risk, scanner, utils
- Strategy pattern: base class with pluggable strategy implementations
- Paper trading mode built-in (simulated execution with real data)
- All config in `config/settings.py`, secrets in `config/.env`
- Trade logs stored in SQLite + CSV for analysis

## Trading Context
- **Market:** NSE/BSE (India)
- **Market Hours:** 9:15 AM - 3:30 PM IST
- **Bot Active Window:** 9:30 AM - 3:15 PM IST
- **Primary Strategies:** Opening Range Breakout (ORB), RSI+EMA Crossover, VWAP+Supertrend
- **Risk Rules:** 1-2% max risk per trade, 3% max daily loss, max 5 trades/day
- **Target Stocks:** NIFTY 50 large-caps (RELIANCE, TCS, HDFCBANK, INFY, ICICIBANK, etc.)

## SEBI Compliance (April 2026)
- Algo-ID required for all algorithmic orders
- Static IP whitelisting required
- Personal use under 10 orders/second is fine via Zerodha
- Keep order frequency reasonable

## Development Rules
- NEVER commit API keys or secrets — always use .env
- Always implement stop-losses on every trade
- Paper trade before live trading
- Log every trade with entry, exit, P&L, and reason
- Test risk management edge cases thoroughly
- Handle API errors gracefully (rate limits, network issues, market holidays)

## Documentation
All project research and guides are in `docs/`:
- `01-TRADING-FUNDAMENTALS.md` — Trading basics, terminology, indicators
- `02-TRADING-STRATEGIES.md` — Strategy details (ORB, RSI+EMA, MACD+BB, VWAP+ST)
- `03-ZERODHA-KITE-API-GUIDE.md` — Full Kite Connect API reference
- `04-RISK-MANAGEMENT.md` — Risk rules, position sizing, circuit breakers
- `05-TECH-STACK-AND-ARCHITECTURE.md` — Project structure, lifecycle, config
- `06-BACKTESTING-GUIDE.md` — How to backtest, metrics, pitfalls
- `07-REALISTIC-EXPECTATIONS.md` — Returns expectations, tax, safety checklist

## Commands
```bash
# Install dependencies
pip install -r requirements.txt

# Run backtest
python backtest/run_backtest.py

# Run bot (paper mode)
TRADING_MODE=paper python main.py

# Run bot (live mode) — only after thorough paper testing
TRADING_MODE=live python main.py
```
