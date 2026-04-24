# Active Trading Strategy

Last updated: 2026-04-24

## Current Mode: PAPER

---

## Primary Strategy: Opening Range Breakout (ORB)

- **Timeframe:** 15-minute candles
- **Setup:** Wait for 9:15-9:30 opening range (high/low of first 15 min)
- **Entry LONG:** Price breaks above opening range high with volume confirmation
- **Entry SHORT:** Price breaks below opening range low with volume confirmation
- **Stop-loss:** Opposite end of the opening range
- **Targets:** 1R (1:1), 2R (1:2), 3R partial ladder
- **Win rate expectation:** 45-55%

## Secondary: RSI + EMA Crossover

- **Timeframe:** 5-minute candles
- **BUY:** 9 EMA crosses above 21 EMA, RSI 40-70, price above VWAP
- **SELL:** 9 EMA crosses below 21 EMA, RSI 30-60 **(HARD RULE: reject if RSI < 30 — oversold bounce risk)**, price below VWAP
- **Stop-loss:** 1.5x ATR from entry
- **Target:** 2x stop distance (1:2 R:R)

## Secondary: VWAP + Supertrend

- **Timeframe:** 5-minute candles
- **BUY:** Price above VWAP + Supertrend turns green
- **SELL:** Price below VWAP + Supertrend turns red
- **Stop-loss:** Supertrend line
- **Target:** 2x risk distance

---

## Risk Parameters

| Rule | Value |
|------|-------|
| Max risk per trade | 1% of capital |
| Max daily loss | 3% of capital |
| Max trades per day | 5 |
| Max open positions | 2 |
| Min risk/reward | 1:2 |
| Position sizing | `(Capital x 1%) / (Entry - SL)` |

## When NOT to Trade

- First 15 minutes after open (9:15-9:30) — building the ORB range
- Last 15 minutes before close (3:15-3:30) — bot squares off at 3:15
- India VIX > 25 (HIGH volatility regime)
- After 3 consecutive losses in a day
- Market holidays / truncated sessions
- Binary event stocks (results day, court rulings)

## Target Stocks

NIFTY 50 large-caps: RELIANCE, TCS, HDFCBANK, INFY, ICICIBANK, KOTAKBANK, HINDUNILVR, ITC, SBIN, BHARTIARTL, LT, AXISBANK, BAJFINANCE, MARUTI, WIPRO, TATAMOTORS

## Market Hours

- **NSE pre-open:** 9:00 - 9:15 AM IST
- **Market open:** 9:15 AM IST
- **Bot active:** 9:30 AM - 3:15 PM IST
- **Market close:** 3:30 PM IST

---

## Lessons Learned

_Updated by /weekly-review and /daily-summary commands. Most recent first._

- **#lesson 2026-04-24:** Exit events not written during EOD square-off — fix exit logger to fire on all exit paths (target, SL, EOD close), not just during active signal processing.
- **#lesson 2026-04-24:** Avoid shorting when RSI < 30 at entry. In STRONG_TREND_DOWN, wait for RSI to bounce to 40-50 before re-entering short — catching a pullback gives better R:R than chasing an already-oversold move.
- **#lesson 2026-04-24:** Track win rate by MULTI confirmation count (1 vs 2 vs 3 strategies agreeing). Hypothesis: 2+ confirmations should produce higher win rates. Data needed.
