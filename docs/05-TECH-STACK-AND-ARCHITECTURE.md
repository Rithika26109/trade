# Tech Stack & Bot Architecture

---

## Recommended Tech Stack

### Core
| Component | Library | Purpose |
|-----------|---------|---------|
| Language | **Python 3.10+** | Primary language (70% of quant devs use Python) |
| Broker API | **pykiteconnect** | Zerodha Kite Connect official Python client |
| Data Analysis | **pandas** | DataFrames for OHLCV data manipulation |
| Math/Numerics | **numpy** | Fast numerical computations |
| Technical Indicators | **pandas-ta** | 130+ indicators (easier to install than ta-lib) |
| Backtesting | **backtesting.py** | Lightweight backtesting framework |
| Scheduling | **APScheduler** | Job scheduling (run bot at market open) |
| Logging | **loguru** | Better logging than built-in logging module |
| TOTP | **pyotp** | Auto-generate login OTP codes |
| Config | **python-dotenv** | Manage API keys via .env file |
| Database | **SQLite** | Store trade logs, P&L data locally |

### Optional / Advanced
| Component | Library | Purpose |
|-----------|---------|---------|
| Dashboard | **Streamlit** | Simple web UI for monitoring |
| Notifications | **python-telegram-bot** | Send trade alerts to your phone |
| ML/AI | **scikit-learn** | Machine learning for strategy optimization |
| Visualization | **plotly** | Interactive charts for analysis |
| Alternative indicators | **ta-lib** | Faster, but harder to install (C dependency) |

### Install Command
```bash
pip install kiteconnect pandas numpy pandas-ta backtesting apscheduler loguru pyotp python-dotenv
```

---

## Project Structure

```
trade/
├── config/
│   ├── .env                    # API keys (NEVER commit this)
│   └── settings.py             # Bot configuration (strategy params, limits)
│
├── src/
│   ├── __init__.py
│   ├── auth/
│   │   ├── __init__.py
│   │   └── login.py            # Zerodha authentication + auto-TOTP
│   │
│   ├── data/
│   │   ├── __init__.py
│   │   ├── market_data.py      # Fetch OHLCV, LTP, quotes
│   │   └── websocket.py        # Real-time tick data via WebSocket
│   │
│   ├── strategy/
│   │   ├── __init__.py
│   │   ├── base.py             # Base strategy class
│   │   ├── orb.py              # Opening Range Breakout strategy
│   │   ├── rsi_ema.py          # RSI + EMA crossover strategy
│   │   └── vwap_supertrend.py  # VWAP + Supertrend strategy
│   │
│   ├── execution/
│   │   ├── __init__.py
│   │   ├── order_manager.py    # Place, modify, cancel orders
│   │   └── position_manager.py # Track open positions
│   │
│   ├── risk/
│   │   ├── __init__.py
│   │   ├── risk_manager.py     # Position sizing, daily limits
│   │   └── stop_loss.py        # Stop-loss management (fixed, ATR, trailing)
│   │
│   ├── scanner/
│   │   ├── __init__.py
│   │   └── stock_scanner.py    # Scan for tradeable stocks daily
│   │
│   └── utils/
│       ├── __init__.py
│       ├── logger.py           # Logging setup
│       ├── notifier.py         # Telegram/email notifications
│       └── db.py               # SQLite trade log database
│
├── backtest/
│   ├── run_backtest.py         # Run backtests on historical data
│   └── results/                # Backtest result reports
│
├── logs/
│   └── trades/                 # Daily trade logs (CSV/JSON)
│
├── data/
│   └── historical/             # Cached historical data
│
├── tests/
│   ├── test_strategy.py
│   ├── test_risk.py
│   └── test_orders.py
│
├── docs/                       # This documentation
│
├── main.py                     # Entry point — starts the bot
├── requirements.txt
├── .gitignore
└── README.md
```

---

## Bot Lifecycle (How It Runs Daily)

```
                    ┌─────────────────┐
                    │   8:30 AM IST   │
                    │   Bot Starts    │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  1. Authenticate │
                    │  (Login + TOTP) │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  2. Load Config  │
                    │  Strategy params │
                    │  Risk limits     │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  3. Scan Stocks  │
                    │  Select today's  │
                    │  watchlist       │
                    └────────┬────────┘
                             │
                    ┌────────▼─────────┐
                    │  4. Wait for 9:15│
                    │  Market Opens    │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  5. Collect Data  │
                    │  (9:15 - 9:30/45)│
                    │  Opening range    │
                    └────────┬─────────┘
                             │
              ┌──────────────▼──────────────┐
              │  6. MAIN TRADING LOOP       │
              │  (9:30/9:45 - 3:00 PM)      │
              │                             │
              │  ┌─────────────────────┐    │
              │  │ Receive tick data   │◄───┤── WebSocket
              │  └──────────┬──────────┘    │
              │             │               │
              │  ┌──────────▼──────────┐    │
              │  │ Calculate indicators│    │
              │  │ (RSI, EMA, MACD...) │    │
              │  └──────────┬──────────┘    │
              │             │               │
              │  ┌──────────▼──────────┐    │
              │  │ Check strategy      │    │
              │  │ signals (BUY/SELL?) │    │
              │  └──────────┬──────────┘    │
              │             │               │
              │  ┌──────────▼──────────┐    │
              │  │ Risk check          │    │
              │  │ (size, limits, SL)  │    │
              │  └──────────┬──────────┘    │
              │             │               │
              │  ┌──────────▼──────────┐    │
              │  │ Execute order       │    │
              │  │ (if signal valid)   │    │
              │  └──────────┬──────────┘    │
              │             │               │
              │  ┌──────────▼──────────┐    │
              │  │ Monitor positions   │    │
              │  │ Trail stops         │    │
              │  └──────────┬──────────┘    │
              │             │               │
              │  ┌──────────▼──────────┐    │
              │  │ Check circuit       │    │
              │  │ breakers            │    │
              │  └─────────────────────┘    │
              └──────────────┬──────────────┘
                             │
                    ┌────────▼─────────┐
                    │  7. Square Off    │
                    │  (3:00 - 3:15 PM)│
                    │  Close all open   │
                    │  positions        │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  8. End of Day    │
                    │  - Log all trades │
                    │  - Calculate P&L  │
                    │  - Send report    │
                    │  - Save to DB     │
                    └──────────────────┘
```

---

## Configuration File Structure

```python
# config/settings.py

# ── Strategy Settings ──
STRATEGY = "ORB"                    # ORB, RSI_EMA, VWAP_SUPERTREND
TIMEFRAME = "5minute"               # Candle timeframe
ORB_PERIOD_MINUTES = 15             # Opening range period (15 or 30)

# ── Indicator Parameters ──
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
EMA_FAST = 9
EMA_SLOW = 21
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
ATR_PERIOD = 14
ATR_MULTIPLIER = 1.5

# ── Risk Management ──
RISK_PER_TRADE_PCT = 1.0           # Max 1% risk per trade
MAX_DAILY_LOSS_PCT = 3.0           # Stop trading after 3% daily loss
MAX_TRADES_PER_DAY = 7             # Maximum trades in a day
MAX_OPEN_POSITIONS = 2             # Maximum concurrent positions
MIN_RISK_REWARD_RATIO = 2.0        # Minimum 1:2 risk/reward
MAX_POSITION_PCT = 30.0            # Max 30% of capital in one trade

# ── Trading Hours ──
MARKET_OPEN = "09:15"
TRADING_START = "09:30"            # Start after opening range collected
STOP_NEW_TRADES = "15:00"          # No new trades after 3 PM
FORCE_SQUARE_OFF = "15:15"         # Force close everything by 3:15

# ── Stock Selection ──
WATCHLIST = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "SBIN", "BHARTIARTL", "ITC", "KOTAKBANK", "LT"
]
MIN_VOLUME = 1000000               # Minimum daily volume
MIN_PRICE = 100                    # Minimum stock price
MAX_PRICE = 5000                   # Maximum stock price

# ── Notifications ──
TELEGRAM_ENABLED = True
TELEGRAM_BOT_TOKEN = ""            # Set in .env
TELEGRAM_CHAT_ID = ""              # Set in .env
```

---

## Environment Variables (.env)

```env
# Zerodha Kite Connect
KITE_API_KEY=your_api_key_here
KITE_API_SECRET=your_api_secret_here
KITE_TOTP_SECRET=your_totp_secret_here
KITE_USER_ID=your_zerodha_user_id

# Telegram Notifications (optional)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Mode
TRADING_MODE=paper  # "paper" or "live"
```

---

## Development Phases

### Phase 1: Foundation (Week 1-2)
- [ ] Set up project structure
- [ ] Implement Zerodha authentication (auto-login)
- [ ] Fetch market data (historical + real-time)
- [ ] Calculate technical indicators
- [ ] Basic logging

### Phase 2: Strategy + Backtesting (Week 3-4)
- [ ] Implement ORB strategy
- [ ] Build backtesting pipeline
- [ ] Run backtests on 6-12 months historical data
- [ ] Optimize parameters
- [ ] Evaluate: Win rate, max drawdown, Sharpe ratio

### Phase 3: Paper Trading (Week 5-8)
- [ ] Implement order execution (paper mode)
- [ ] Implement risk management
- [ ] Run paper trading for 2-4 weeks minimum
- [ ] Compare paper results with backtest results
- [ ] Fix bugs and edge cases

### Phase 4: Live Trading (Week 9+)
- [ ] Start with MINIMUM capital (Rs 10,000-25,000)
- [ ] Run with very conservative risk settings (0.5% per trade)
- [ ] Monitor for 2 weeks
- [ ] Gradually increase position sizes if profitable
- [ ] Add Telegram notifications
- [ ] Build monitoring dashboard

### Phase 5: Optimization (Ongoing)
- [ ] Add more strategies
- [ ] Implement stock scanner
- [ ] Add ML-based signal filtering
- [ ] Walk-forward optimization
- [ ] Multi-strategy portfolio
