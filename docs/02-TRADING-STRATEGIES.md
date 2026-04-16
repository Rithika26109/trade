# Trading Strategies for the Bot

## Recommended Strategies (Beginner-Friendly, Indian Market)

---

## Strategy 1: Opening Range Breakout (ORB) ★ RECOMMENDED FOR BEGINNERS

**How it works:**
1. Wait for the first 15-30 minutes after market opens (9:15 - 9:45)
2. Note the HIGH and LOW of that period — this is the "opening range"
3. If price breaks ABOVE the high → BUY
4. If price breaks BELOW the low → SELL (short)
5. Set stop-loss at the opposite end of the range

**Why it works:** The first 15-30 min establishes the day's tone. Breakout from this range often leads to a sustained move.

```
Example:
- 9:15-9:45 Range: High = 100, Low = 95
- Price breaks above 100 at 10:00 → BUY at 100.50
- Stop-loss at 95 (the low)
- Target: 100.50 + (100 - 95) = 105.50 (1:1 risk/reward)
```

**Best for:** NIFTY 50 stocks, BANK NIFTY, large-cap liquid stocks
**Timeframe:** 15-minute candles
**Win rate:** ~45-55% but with good risk/reward ratio

---

## Strategy 2: RSI + EMA Crossover

**How it works:**
1. Use 9 EMA and 21 EMA on 5-minute chart
2. Check RSI (14 period)
3. **BUY when:**
   - 9 EMA crosses ABOVE 21 EMA (bullish crossover)
   - RSI is between 40-70 (not overbought)
   - Price is above VWAP
4. **SELL when:**
   - 9 EMA crosses BELOW 21 EMA (bearish crossover)
   - RSI is between 30-60 (not oversold)
   - Price is below VWAP

**Stop-loss:** 1.5x ATR below entry (for buy) or above entry (for sell)
**Target:** 2x the stop-loss distance (1:2 risk/reward)

---

## Strategy 3: MACD + Bollinger Bands

**How it works:**
1. Use Bollinger Bands (20 period, 2 std dev) on 5-minute chart
2. Use MACD (12, 26, 9)
3. **BUY when:**
   - Price touches or crosses below lower Bollinger Band
   - MACD shows bullish crossover (MACD line crosses above signal)
   - Volume is above average
4. **SELL when:**
   - Price touches or crosses above upper Bollinger Band
   - MACD shows bearish crossover
   - Volume is above average

**Stop-loss:** Below the lowest point of the Bollinger Band touch
**Target:** Middle Bollinger Band (20 SMA) or upper band

---

## Strategy 4: VWAP + Supertrend

**How it works:**
1. Use VWAP as primary trend filter
2. Use Supertrend indicator (10, 3) for entry signals
3. **BUY when:**
   - Price is above VWAP
   - Supertrend turns green (buy signal)
4. **SELL when:**
   - Price is below VWAP
   - Supertrend turns red (sell signal)

**Stop-loss:** Supertrend value (it acts as a trailing stop)
**Target:** Trail with Supertrend or take 1:2 risk/reward

---

## Strategy 5: Mean Reversion (Range-Bound Days)

**How it works:**
1. Identify if the day is range-bound (no clear trend)
2. Use Bollinger Bands + RSI
3. **BUY when:** Price at lower Bollinger Band AND RSI < 30
4. **SELL when:** Price at upper Bollinger Band AND RSI > 70
5. Target: Middle band (20 SMA)

**Best for:** Sideways markets, low-volatility days
**Warning:** Don't use on trending days — will result in losses

---

## Strategy Comparison

| Strategy | Difficulty | Win Rate | Risk/Reward | Best Market | Automation Ease |
|----------|-----------|----------|-------------|-------------|-----------------|
| ORB | Easy | 45-55% | 1:1 to 1:2 | Trending | Very Easy |
| RSI + EMA | Medium | 50-60% | 1:2 | Trending | Easy |
| MACD + BB | Medium | 45-55% | 1:1.5 | All | Medium |
| VWAP + Supertrend | Easy | 50-55% | 1:2 | Trending | Easy |
| Mean Reversion | Medium | 55-65% | 1:1 | Sideways | Medium |

---

## Which Stocks to Trade?

### Criteria for Stock Selection
1. **High Liquidity** — Average daily volume > 10 lakh shares
2. **Tight Spread** — Bid-ask spread < 0.05%
3. **Good Volatility** — ATR should be reasonable (not too low, not too high)
4. **Large/Mid Cap** — Avoid penny stocks and small caps for automation

### Recommended Stocks for Intraday Bot (NSE)
**NIFTY 50 Heavyweights (most liquid):**
- RELIANCE, TCS, HDFCBANK, INFY, ICICIBANK
- SBIN, BHARTIARTL, ITC, KOTAKBANK, LT

**BANK NIFTY Components (high volatility, good for intraday):**
- HDFCBANK, ICICIBANK, SBIN, KOTAKBANK, AXISBANK
- INDUSINDBK, BANDHANBNK, FEDERALBNK

**Index Trading (if doing F&O):**
- NIFTY 50 futures/options
- BANK NIFTY futures/options

### Stock Scanner Criteria (Dynamic Selection)
Your bot should scan for stocks daily that match:
- Volume > 150% of 20-day average (unusual activity)
- Price within 1% of key support/resistance
- RSI between 30-40 (potential buy) or 60-70 (potential sell)
- Gap up/down > 1% from previous close

---

## When NOT to Trade

1. **First 15 minutes** — Too volatile, unpredictable
2. **Last 15 minutes** — Risky, approaching square-off
3. **Major news events** — RBI policy, Union Budget, election results
4. **Low-volume days** — Near holidays, Saturday trading sessions
5. **After 3 consecutive losses** — Stop for the day (circuit breaker)
6. **When market is in extreme panic** — VIX > 25 (India VIX)
