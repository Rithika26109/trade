# Risk Management — The Most Important Part

> **"The goal is survival first, profit second."**
> Even the best strategy will blow up your account without proper risk management.

---

## The Golden Rules

### Rule 1: Never Risk More Than 1-2% Per Trade
If your account has Rs 1,00,000:
- Maximum risk per trade = Rs 1,000 - Rs 2,000
- This is NOT your position size — it's the maximum you can LOSE on that trade
- Example: Buy stock at Rs 100, stop-loss at Rs 95 → Risk = Rs 5/share → Max quantity = 200-400 shares

### Rule 2: Always Use a Stop-Loss — NO EXCEPTIONS
- Every single trade must have a pre-defined stop-loss
- Never move your stop-loss further away (widening losses)
- Use ATR-based stops: Stop = Entry - (1.5 × ATR)

### Rule 3: Risk/Reward Ratio Minimum 1:2
- If you risk Rs 1,000, your target should be at least Rs 2,000 profit
- This means even with 40% win rate, you're still profitable:
  - 10 trades: 4 wins × Rs 2,000 = Rs 8,000 profit
  - 10 trades: 6 losses × Rs 1,000 = Rs 6,000 loss
  - Net: Rs 2,000 profit despite losing 60% of trades!

### Rule 4: Maximum Daily Loss Limit
- Set a hard limit: stop trading for the day after losing 3-5% of capital
- Example: Rs 1,00,000 account → Stop after Rs 3,000-5,000 daily loss
- This prevents emotional "revenge trading" after losses

### Rule 5: Maximum Number of Trades Per Day
- Limit to 3-5 trades per day initially
- More trades ≠ more profit (commission + slippage adds up)
- Quality over quantity

---

## Position Sizing Formula

```
Position Size = (Account Balance × Risk %) / (Entry Price - Stop-Loss Price)
```

**Example:**
- Account: Rs 1,00,000
- Risk per trade: 1% = Rs 1,000
- Stock price: Rs 500
- Stop-loss: Rs 490 (Rs 10 risk per share)
- Position size: Rs 1,000 / Rs 10 = **100 shares**
- Position value: 100 × Rs 500 = Rs 50,000

---

## Stop-Loss Strategies

### Fixed Percentage Stop
- Set stop at X% below entry (e.g., 1-2%)
- Simple but doesn't account for volatility

### ATR-Based Stop (RECOMMENDED)
- Stop = Entry Price - (Multiplier × ATR)
- Multiplier: 1.5 for tight stop, 2.0 for normal, 3.0 for loose
- Adapts to market volatility automatically

### Trailing Stop
- Move stop-loss UP as price moves in your favor
- Example: Price goes from 100 → 110, move stop from 95 → 105
- Locks in profits while letting winners run

### Time-Based Stop
- Exit if trade hasn't moved in your direction within X minutes/hours
- Frees up capital for better opportunities

---

## Circuit Breakers (Auto-Shutdown Conditions)

Your bot MUST stop trading when:

| Condition | Action |
|-----------|--------|
| Daily loss > 3% of capital | Stop all trading for the day |
| 3 consecutive losing trades | Pause for 30 minutes |
| Single trade loss > 2% | Review strategy parameters |
| Daily profit target hit (e.g., 2%) | Consider stopping (lock in gains) |
| Technical error / API failure | Immediately stop and alert |
| Market volatility extreme (VIX > 25) | Reduce position sizes by 50% or stop |

---

## Capital Allocation

### Starting Capital Recommendation
- **Minimum for stocks intraday:** Rs 25,000 - Rs 50,000
- **Comfortable starting amount:** Rs 1,00,000
- **For F&O (futures & options):** Rs 2,00,000+

### Allocation Rules
- Never use more than 50% of your capital on a single trade
- Keep at least 30% as free margin (buffer for adverse moves)
- Start with VERY small positions while testing

---

## Common Mistakes That Blow Up Accounts

1. **No stop-loss** — "It'll come back" → It doesn't → Account wiped
2. **Averaging down** — Buying more of a losing trade → Bigger loss
3. **Over-leveraging** — Using full margin on every trade → One bad day destroys you
4. **Revenge trading** — Lost money, now trying to "win it back" fast → More losses
5. **Ignoring slippage** — Backtests show profit, but real execution costs eat it all
6. **Over-trading** — 20+ trades/day → Commissions and slippage kill profit
7. **Moving stop-loss** — Widening your stop because "it's close to reversing" → Never does

---

## Transaction Costs to Account For

### Zerodha Charges (Equity Intraday)
| Fee | Amount |
|-----|--------|
| Brokerage | Rs 20 per executed order (or 0.03%, whichever is lower) |
| STT (Securities Transaction Tax) | 0.025% on sell side |
| Exchange Transaction | 0.00345% (NSE) |
| GST | 18% on brokerage + exchange charges |
| SEBI Charges | 0.0001% |
| Stamp Duty | 0.003% on buy side |

**Total approximate cost per round trip (buy + sell):** ~0.05-0.1% of trade value

**Example:** Buy + Sell Rs 50,000 worth of stock:
- Brokerage: Rs 20 × 2 = Rs 40
- STT: Rs 12.50
- Other charges: ~Rs 10
- **Total: ~Rs 62 per trade**

This means you need to make at least Rs 62 just to break even on a Rs 50,000 trade!

---

## Risk Management Checklist for Your Bot

```
Before EVERY trade, your bot must verify:
[ ] Position size calculated based on 1-2% risk rule
[ ] Stop-loss price determined (ATR-based or fixed)
[ ] Risk/reward ratio >= 1:2
[ ] Daily loss limit not exceeded
[ ] Maximum trades per day not exceeded
[ ] Sufficient margin available
[ ] Not within first 15 min or last 15 min of market
[ ] No major news events pending
[ ] Current VIX level acceptable

After every trade:
[ ] Update daily P&L tracker
[ ] Log trade details (entry, exit, P&L, reason)
[ ] Check if any circuit breaker conditions met
[ ] Update risk metrics
```
