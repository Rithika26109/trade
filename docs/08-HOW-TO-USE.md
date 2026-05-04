# How to Use the Trading Bot — Step by Step Guide

---

## Prerequisites

Before you begin, make sure you have:
1. **Python 3.10 or higher** installed
2. **A Zerodha trading account** with 2FA TOTP enabled
3. **Kite Connect Developer account** (https://developers.kite.trade/)
4. **Basic terminal knowledge** (running commands)

---

## Step 1: Install Dependencies

Open your terminal and navigate to the project:

```bash
cd /Users/rithika-18920/Documents/aiaiai/serious/trade
pip install -r requirements.txt
```

If `pandas-ta` gives trouble, try:
```bash
pip install pandas-ta --no-deps
pip install pandas numpy
```

---

## Step 2: Set Up Your API Keys

### 2a. Get Kite Connect API credentials
1. Go to https://developers.kite.trade/
2. Create a new app (choose "Personal" for free)
3. Note down your **API Key** and **API Secret**
4. Set your redirect URL to `http://127.0.0.1`

### 2b. Get your TOTP Secret
1. In Zerodha, go to My Profile → Security → TOTP
2. When setting up TOTP, you'll see a secret key
3. Save this key — the bot uses it to auto-login

### 2c. Create your .env file
```bash
cp config/.env.example config/.env
```

Edit `config/.env` and fill in your credentials:
```
KITE_API_KEY=your_actual_api_key
KITE_API_SECRET=your_actual_api_secret
KITE_USER_ID=AB1234
KITE_TOTP_SECRET=your_totp_secret
TRADING_MODE=paper
```

**IMPORTANT:** NEVER share your `.env` file or commit it to git!

---

## Step 3: Run a Backtest First

Before any live/paper trading, test the strategy on historical data:

```bash
# Default: ORB strategy on sample data
python backtest/run_backtest.py

# Test RSI+EMA strategy
python backtest/run_backtest.py --strategy RSI_EMA

# Test on specific stock with more data
python backtest/run_backtest.py --symbol RELIANCE --days 90

# With different starting capital
python backtest/run_backtest.py --capital 50000
```

This will:
- Run the strategy on historical data
- Show you metrics (return %, win rate, Sharpe ratio, max drawdown)
- Generate an interactive HTML report in `backtest/results/`

**What to look for:**
- Sharpe Ratio > 1.0 → Good
- Win Rate > 40% (with 1:2 risk/reward) → Good
- Max Drawdown < 15% → Acceptable

---

## Step 4: Paper Trading (5-10 Days)

This is the most important step. Run the bot with fake money to see how it performs in real market conditions.

```bash
# Start paper trading (default mode)
python main.py --paper
```

Or just:
```bash
python main.py
```
(Paper mode is the default)

### What happens:
1. Bot logs into Zerodha (needs real credentials for market data)
2. Scans your watchlist for good stocks
3. Waits for market to open (9:15 AM)
4. Collects opening range (first 15 min)
5. Starts looking for trade signals
6. Places **simulated** trades (no real money)
7. Monitors stop-loss and targets
8. Squares off everything by 3:15 PM
9. Prints a daily report

### Monitor the output:
```
09:15:00 | INFO     | Trading Bot starting — Mode: PAPER
09:15:05 | INFO     | Zerodha connected successfully
09:30:00 | INFO     | [ORB] RELIANCE opening range: High=2680.50, Low=2655.30
09:45:12 | INFO     | [PAPER] BUY RELIANCE | Qty: 37 | Price: 2682.00 | SL: 2655.30 | Target: 2735.40
10:12:45 | INFO     | [PAPER] CLOSED RELIANCE | Entry: 2682.00 | Exit: 2735.40 | P&L: Rs 1976.80
...
15:15:00 | INFO     | ─────── DAILY REPORT ───────
15:15:00 | INFO     |   Total Trades:  3
15:15:00 | INFO     |   Wins:          2
15:15:00 | INFO     |   Losses:        1
15:15:00 | INFO     |   Win Rate:      66.7%
15:15:00 | INFO     |   Total P&L:     Rs +1,245.60
```

### After 5-10 days of paper trading:
- Check your trade logs in `logs/trades/`
- Check the SQLite database at `data/trades.db`
- Look at your daily summaries
- If P&L is consistently positive → ready for Phase B

---

## Step 5: Small Live Trading

**Only after paper trading shows consistent results!**

### 5a. Update .env
```
TRADING_MODE=live
```

### 5b. Start with minimum capital
- Add only Rs 10,000-25,000 to your Zerodha account initially
- Update `config/settings.py`:
  ```python
  RISK_PER_TRADE_PCT = 0.5  # Start with just 0.5% risk (very conservative)
  MAX_TRADES_PER_DAY = 3    # Fewer trades initially
  ```

### 5c. Run live
```bash
python main.py --live
```

### 5d. Monitor closely
- Watch the terminal output
- Check your Zerodha Kite app for actual positions
- Be ready to stop the bot if something goes wrong (Ctrl+C)

---

## Step 6: Scale Up (After Consistent Profits)

After 2-4 weeks of small live profits:
1. Gradually increase capital
2. Increase `RISK_PER_TRADE_PCT` back to 1.0
3. Increase `MAX_TRADES_PER_DAY` to 5
4. Consider adding more strategies

---

## Changing Settings

All settings are in `config/settings.py`:

### Change Strategy
```python
STRATEGY = "RSI_EMA"  # Options: "ORB", "RSI_EMA", "VWAP_SUPERTREND"
```

### Change Risk Settings
```python
RISK_PER_TRADE_PCT = 1.0   # 1% risk per trade
MAX_DAILY_LOSS_PCT = 3.0   # Stop after 3% daily loss
MAX_TRADES_PER_DAY = 5     # Max 5 trades
```

### Change Watchlist
```python
WATCHLIST = [
    "RELIANCE", "TCS", "HDFCBANK",  # Add/remove stocks here
]
```

### Change Timeframe
```python
TIMEFRAME = "5minute"  # Options: minute, 3minute, 5minute, 15minute
```

---

## Setting Up Telegram Alerts (Optional)

Get instant trade alerts on your phone:

### 1. Create a Telegram Bot
1. Open Telegram, search for `@BotFather`
2. Send `/newbot` and follow instructions
3. Copy the bot token

### 2. Get your Chat ID
1. Send a message to your new bot
2. Visit: `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. Find your `chat.id` in the JSON response

### 3. Update .env
```
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_CHAT_ID=987654321
```

### 4. Enable in settings
```python
TELEGRAM_ENABLED = True
```

Now you'll get alerts for every trade entry, exit, and daily reports!

---

## Stopping the Bot

- **Normal stop:** Press `Ctrl+C` — bot will gracefully square off positions and shut down
- **Emergency stop:** Press `Ctrl+C` twice — immediate stop
- **Kill process:** `kill $(pgrep -f "python main.py")`

If the bot crashes mid-trade:
1. Open Zerodha Kite app/web
2. Check Positions tab
3. Manually square off any open MIS positions

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Authentication failed" | Check API key/secret in .env. Make sure TOTP secret is correct |
| "Rate limit exceeded" | Bot is making too many API calls. Increase TIMEFRAME to "15minute" |
| "Instrument not found" | Check symbol spelling. Run with DEBUG logging |
| "Insufficient margin" | Not enough funds in Zerodha for the trade size |
| No trades happening | Check if market is open. Look at logs for strategy signals |
| Bot crashes at startup | Run `pip install -r requirements.txt` again |

### Enable debug logging
In `config/settings.py`:
```python
LOG_LEVEL = "DEBUG"  # Change from "INFO" to "DEBUG"
```

### Check logs
```bash
# Today's bot log
cat logs/bot-$(date +%Y-%m-%d).log

# Today's trade log
cat logs/trades/trades_$(date +%Y-%m-%d).log
```

---

## Daily Routine

Here's what your day should look like:

| Time | Action |
|------|--------|
| **9:00 AM** | Start the bot (`python main.py`) |
| **9:15 AM** | Bot connects and starts collecting data |
| **9:30 AM** | Opening range set, trading begins |
| **During the day** | Check terminal occasionally or rely on Telegram alerts |
| **3:15 PM** | Bot auto-squares off and generates report |
| **Evening** | Review daily report, check trade logs, adjust settings if needed |

---

## File Reference

| File | What it does |
|------|-------------|
| `main.py` | Starts the bot |
| `config/settings.py` | All configurable parameters |
| `config/.env` | Your secret API keys |
| `src/auth/login.py` | Zerodha login + auto TOTP |
| `src/data/market_data.py` | Fetches stock data |
| `src/data/websocket.py` | Real-time price streaming |
| `src/indicators/indicators.py` | RSI, EMA, MACD, etc. |
| `src/strategy/orb.py` | Opening Range Breakout strategy |
| `src/strategy/rsi_ema.py` | RSI + EMA strategy |
| `src/strategy/vwap_supertrend.py` | VWAP + Supertrend strategy |
| `src/execution/order_manager.py` | Places trades (paper & live) |
| `src/execution/position_manager.py` | Tracks open positions |
| `src/risk/risk_manager.py` | Risk rules & position sizing |
| `src/scanner/stock_scanner.py` | Finds best stocks to trade |
| `src/utils/db.py` | SQLite trade database |
| `src/utils/logger.py` | Logging setup |
| `src/utils/notifier.py` | Telegram alerts |
| `backtest/run_backtest.py` | Strategy backtesting |
| `data/trades.db` | Trade history database |
| `logs/` | Daily log files |
