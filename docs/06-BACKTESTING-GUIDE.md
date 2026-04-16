# Backtesting Guide

> **NEVER skip backtesting.** A strategy that looks good in your head can lose money in reality.
> Backtesting = testing your strategy on historical data to see if it would have been profitable.

---

## Why Backtest?

- Validate your strategy BEFORE risking real money
- Find optimal parameters (RSI period, EMA length, stop-loss distance)
- Understand expected win rate, drawdown, and returns
- Identify weaknesses and edge cases

---

## Backtesting Tools

### 1. backtesting.py (RECOMMENDED for this project)
```bash
pip install backtesting
```
- Lightweight, fast, beginner-friendly
- Beautiful interactive HTML reports
- Built-in optimization
- Works with pandas DataFrames

### 2. Backtrader (alternative — more powerful, steeper learning curve)
```bash
pip install backtrader
```

### 3. Freqtrade (full framework — best for crypto)
```bash
pip install freqtrade
```

---

## Backtesting with backtesting.py — Example

```python
from backtesting import Backtest, Strategy
from backtesting.lib import crossover
import pandas as pd
import pandas_ta as ta

class RSI_EMA_Strategy(Strategy):
    # Parameters (can be optimized)
    ema_fast = 9
    ema_slow = 21
    rsi_period = 14
    rsi_lower = 30
    rsi_upper = 70
    
    def init(self):
        close = pd.Series(self.data.Close)
        
        # Calculate indicators
        self.ema_fast_line = self.I(
            lambda x: ta.ema(pd.Series(x), length=self.ema_fast),
            self.data.Close
        )
        self.ema_slow_line = self.I(
            lambda x: ta.ema(pd.Series(x), length=self.ema_slow),
            self.data.Close
        )
        self.rsi = self.I(
            lambda x: ta.rsi(pd.Series(x), length=self.rsi_period),
            self.data.Close
        )
    
    def next(self):
        # Skip if indicators not ready
        if self.rsi[-1] is None:
            return
            
        # Buy signal
        if (crossover(self.ema_fast_line, self.ema_slow_line) and 
            self.rsi[-1] < self.rsi_upper and
            self.rsi[-1] > self.rsi_lower):
            self.buy(sl=self.data.Close[-1] * 0.98)  # 2% stop-loss
        
        # Sell signal
        elif (crossover(self.ema_slow_line, self.ema_fast_line) or
              self.rsi[-1] > self.rsi_upper):
            self.position.close()


# Load historical data
df = pd.read_csv("historical_data.csv", parse_dates=["date"])
df = df.rename(columns={"date": "Date", "open": "Open", "high": "High", 
                          "low": "Low", "close": "Close", "volume": "Volume"})
df = df.set_index("Date")

# Run backtest
bt = Backtest(df, RSI_EMA_Strategy, cash=100000, commission=0.001)
stats = bt.run()
print(stats)

# Generate interactive HTML report
bt.plot()
```

---

## Key Backtest Metrics to Evaluate

| Metric | What It Means | Good Value |
|--------|--------------|------------|
| **Total Return** | Overall profit/loss percentage | > 0% (obviously) |
| **Sharpe Ratio** | Risk-adjusted return | > 1.0 (good), > 2.0 (great) |
| **Max Drawdown** | Largest peak-to-trough decline | < 15-20% |
| **Win Rate** | % of trades that are profitable | > 40% (with good R:R) |
| **Profit Factor** | Gross profit / Gross loss | > 1.5 |
| **Average Trade** | Average P&L per trade | Positive |
| **Number of Trades** | Total trades in period | Enough for statistical significance (>50) |
| **Expectancy** | Expected profit per trade | Positive |

### Example Output
```
Start                     2025-01-01
End                       2025-12-31
Duration                  365 days
Return [%]                18.5
Sharpe Ratio              1.45
Max. Drawdown [%]         -8.2
Avg. Drawdown [%]         -2.1
Win Rate [%]              52.3
Profit Factor             1.82
Num Trades                156
```

---

## Parameter Optimization

```python
# Optimize strategy parameters
stats = bt.optimize(
    ema_fast=range(5, 15, 2),       # Test 5, 7, 9, 11, 13
    ema_slow=range(15, 30, 3),      # Test 15, 18, 21, 24, 27
    rsi_period=range(10, 20, 2),    # Test 10, 12, 14, 16, 18
    rsi_lower=[25, 30, 35],
    rsi_upper=[65, 70, 75],
    maximize="Sharpe Ratio",         # Optimize for risk-adjusted returns
    constraint=lambda p: p.ema_fast < p.ema_slow  # Fast must be < Slow
)

print(stats._strategy)  # Shows optimal parameters
```

---

## Getting Historical Data from Zerodha

```python
from kiteconnect import KiteConnect
import pandas as pd
from datetime import datetime, timedelta

kite = KiteConnect(api_key="xxx")
kite.set_access_token("xxx")

# Get instrument token
instruments = kite.instruments("NSE")
infy = next(i for i in instruments if i["tradingsymbol"] == "INFY")
token = infy["instrument_token"]

# Fetch 1 year of daily data
data = kite.historical_data(
    instrument_token=token,
    from_date=datetime(2025, 1, 1),
    to_date=datetime(2025, 12, 31),
    interval="day"
)

df = pd.DataFrame(data)
df.to_csv("data/historical/INFY_daily_2025.csv", index=False)

# For intraday backtesting, fetch 5-minute data
# Note: Kite allows max 60 days per request for minute data
data_5min = kite.historical_data(
    instrument_token=token,
    from_date=datetime(2025, 10, 1),
    to_date=datetime(2025, 11, 30),
    interval="5minute"
)
```

**Limitation:** Kite historical API allows:
- Minute data: 60 days per request
- 3-minute, 5-minute: 100 days per request
- 15-minute, 30-minute, 60-minute: 200 days per request
- Day data: 2000 days per request

To get more data, make multiple requests with different date ranges.

---

## Backtesting Pitfalls to AVOID

### 1. Overfitting
- **Problem:** Optimizing so heavily on past data that the strategy only works on that specific data
- **Solution:** Use walk-forward analysis — optimize on 70% of data, test on remaining 30%

### 2. Survivorship Bias
- **Problem:** Only testing on stocks that exist today (ignoring delisted ones)
- **Solution:** Include delisted stocks in your data if possible

### 3. Look-Ahead Bias
- **Problem:** Using future data in calculations (e.g., using tomorrow's close for today's signal)
- **Solution:** Ensure indicators only use data available at decision time

### 4. Ignoring Transaction Costs
- **Problem:** Backtest shows 20% return, but 15% gets eaten by commissions/slippage
- **Solution:** Always include realistic commission (0.1%) and slippage (0.05-0.1%)

### 5. Too Few Trades
- **Problem:** Strategy made 10 trades in a year — not statistically significant
- **Solution:** Need at least 50-100 trades for meaningful results

### 6. Curve Fitting
- **Problem:** "I found parameters that give 500% return!" — almost certainly overfit
- **Solution:** If results seem too good to be true, they are. Verify on out-of-sample data.

---

## Walk-Forward Analysis (The Right Way)

```
Historical Data Timeline:
|──────── Training (70%) ────────|── Test (30%) ──|

Step 1: Optimize on Training data → Get best parameters
Step 2: Run those parameters on Test data (unseen)
Step 3: If Test results are ~similar to Training → Strategy is robust
         If Test results are much worse → Strategy is overfit

Advanced: Rolling Walk-Forward
|── Train 1 ──|─ Test 1 ─|
    |── Train 2 ──|─ Test 2 ─|
        |── Train 3 ──|─ Test 3 ─|
```

---

## Paper Trading (After Backtesting)

After your backtest looks good, run the bot in **paper trading mode** for 2-4 weeks:

1. Bot generates signals and "executes" trades, but no real money is used
2. Track all paper trades in a log
3. Compare paper results with backtest results
4. If paper results are within 70-80% of backtest results → Strategy is viable
5. If paper results are significantly worse → Investigate why (slippage? timing? data issues?)

Zerodha doesn't have a built-in paper trading mode, so we'll implement it in code:
- Log trades to a file instead of placing real orders
- Use real-time data for signal generation
- Simulate fill prices with realistic slippage
