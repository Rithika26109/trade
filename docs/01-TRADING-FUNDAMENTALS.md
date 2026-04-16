# Trading Fundamentals for Beginners

## What is Day Trading / Intraday Trading?

Day trading (called "intraday trading" in India) means buying and selling stocks **within the same trading day**. You never hold positions overnight. In India, the market is open **9:15 AM to 3:30 PM IST** (NSE/BSE).

**Goal:** Profit from small price movements that happen throughout the day.

---

## Key Concepts You Must Know

### 1. Stock Exchanges (India)
| Exchange | Full Name | What It Trades |
|----------|-----------|----------------|
| **NSE** | National Stock Exchange | Stocks, F&O, Currency, Commodities |
| **BSE** | Bombay Stock Exchange | Stocks, F&O, Currency |

- **NIFTY 50** — Top 50 companies on NSE (index)
- **SENSEX** — Top 30 companies on BSE (index)
- **BANK NIFTY** — Banking sector index (very popular for intraday)

### 2. Order Types
| Order Type | What It Does |
|------------|-------------|
| **Market Order** | Buy/sell immediately at current price |
| **Limit Order** | Buy/sell only at a specific price or better |
| **Stop-Loss (SL)** | Auto-sell if price drops to a level (protects you from big losses) |
| **Stop-Loss Market (SL-M)** | Like SL but executes at market price when triggered |
| **Cover Order (CO)** | Order + mandatory stop-loss (lower margin required) |
| **Bracket Order (BO)** | Order + stop-loss + target price (auto-exits at profit or loss) |

### 3. Product Types in Zerodha
| Code | Name | Meaning |
|------|------|---------|
| **MIS** | Margin Intraday Square-off | Intraday only — auto-squared off by 3:20 PM |
| **CNC** | Cash and Carry | Delivery — hold stocks overnight/long term |
| **NRML** | Normal | For F&O positions carried overnight |

### 4. Key Trading Terms
- **Bid/Ask (Offer):** Bid = highest price buyer will pay. Ask = lowest price seller will accept.
- **Spread:** Difference between bid and ask price.
- **Volume:** Number of shares traded — high volume = more liquidity = easier to trade.
- **Liquidity:** How easily you can buy/sell without affecting the price.
- **Volatility:** How much the price moves — more volatility = more opportunity AND more risk.
- **Margin:** Borrowed money from broker to trade larger positions. Zerodha offers up to 5x margin for intraday.
- **Square Off:** Closing your position (selling what you bought, or buying back what you sold).

### 5. Candlestick Charts (How to Read Price)
Each "candle" shows 4 prices for a time period:
- **Open:** Price at start of period
- **High:** Highest price during period
- **Low:** Lowest price during period
- **Close:** Price at end of period

```
    Green Candle (Price went UP)     Red Candle (Price went DOWN)
    
         |  ← High                        |  ← High
        ┌┴┐                              ┌┴┐
        │ │ ← Close (top)                │ │ ← Open (top)
        │ │                              │ │
        │ │ ← Open (bottom)              │ │ ← Close (bottom)
        └┬┘                              └┬┘
         |  ← Low                         |  ← Low
```

### 6. Support and Resistance
- **Support:** Price level where stock tends to stop falling (buyers step in)
- **Resistance:** Price level where stock tends to stop rising (sellers step in)
- When price **breaks through** support or resistance with volume, it often continues in that direction (breakout)

---

## Technical Indicators (What Your Bot Will Use)

### RSI (Relative Strength Index)
- Measures if a stock is **overbought** or **oversold**
- Scale: 0 to 100
- **Above 70** = Overbought (might fall soon) → Consider SELL
- **Below 30** = Oversold (might rise soon) → Consider BUY
- Period: Usually 14 candles

### MACD (Moving Average Convergence Divergence)
- Shows trend direction and momentum
- **MACD Line** = 12-period EMA minus 26-period EMA
- **Signal Line** = 9-period EMA of MACD Line
- **Buy Signal:** MACD crosses ABOVE signal line
- **Sell Signal:** MACD crosses BELOW signal line

### EMA (Exponential Moving Average)
- Smoothed average of recent prices (gives more weight to recent prices)
- Common periods: 9, 20, 50, 200
- **Price above EMA** = Uptrend
- **Price below EMA** = Downtrend
- **Golden Cross:** Short EMA crosses above long EMA → Bullish
- **Death Cross:** Short EMA crosses below long EMA → Bearish

### Bollinger Bands
- 3 lines: Middle (20 SMA), Upper (+2 std dev), Lower (-2 std dev)
- Price touching **upper band** = potentially overbought
- Price touching **lower band** = potentially oversold
- **Squeeze** (bands narrow) = big move coming

### VWAP (Volume Weighted Average Price)
- Average price weighted by volume — very popular for intraday
- **Price above VWAP** = Bullish bias
- **Price below VWAP** = Bearish bias
- Institutional traders use VWAP as benchmark

### ATR (Average True Range)
- Measures volatility — used to set stop-loss distances
- Higher ATR = more volatile = wider stop-loss needed
- Common: 1.5x ATR for stop-loss distance

---

## Indian Market Trading Sessions

| Time (IST) | Session | What Happens |
|-------------|---------|-------------|
| 9:00 - 9:08 | Pre-open | Orders collected, opening price determined |
| 9:08 - 9:12 | Order matching | Orders matched to set opening price |
| 9:12 - 9:15 | Buffer | Transition to normal trading |
| **9:15 - 3:30** | **Normal Trading** | **Regular buy/sell** |
| 3:20 | MIS Square-off | Zerodha auto-closes intraday positions |
| 3:30 - 3:40 | Post-close | Closing price calculated |

**Important:** Your bot should:
- Start monitoring at 9:15
- Avoid trading in first 15 minutes (too volatile/unpredictable)
- Stop opening new positions by 3:00 PM
- Ensure all positions closed by 3:15 PM (before auto square-off)
