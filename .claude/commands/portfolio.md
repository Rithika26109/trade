# /portfolio — Quick Portfolio Snapshot

You are the portfolio analyst for an NSE intraday trading bot (Zerodha Kite Connect).
Give a quick, clean snapshot of the current account and positions.

## Steps

### 1. Check auth
```bash
scripts/kite.sh profile
```
If this fails with a 403 or token error, tell the user to run `python scripts/refresh_kite_token.py` and stop.

### 2. Get account margins
```bash
scripts/kite.sh account
```
Extract and display: available cash, used margin, total equity.

### 3. Get positions
```bash
scripts/kite.sh positions
```
For each open position, note: symbol, side (long/short), quantity, average entry price.

### 4. Get live quotes for open positions
If there are open positions, get current prices:
```bash
scripts/kite.sh quote SYMBOL1,SYMBOL2
```
Calculate unrealized P&L for each position: `(current_price - entry_price) * quantity`.

### 5. Display formatted summary

Show a clean table:

```
Symbol   | Side  | Qty | Entry   | Current | P&L     | % Change
---------|-------|-----|---------|---------|---------|----------
RELIANCE | LONG  |  10 | 2,500   | 2,530   | +Rs 300 | +1.2%
```

Then show totals:
- **Deployed capital:** Rs X
- **Free margin:** Rs X
- **Unrealized P&L:** Rs X
- **Today's realized P&L:** Rs X (from closed positions)

### 6. Risk limit check

Compare against limits from `memory/TRADING-STRATEGY.md`:
- Open positions: N/2 max
- Trades today: N/5 max
- Daily loss so far: Rs X of Rs 3,000 max

### 7. Educational note (keep brief)

If the user has MIS positions, explain briefly: "MIS = intraday margin product. These positions auto-square-off at 3:15 PM if not closed manually."

If no positions: "No open positions. Your capital is fully available."

## Style
- Keep it compact — this is meant for quick repeated checks
- Use tables for readability
- Bold the P&L numbers (green-ish positive, flag negatives)
- No lengthy explanations unless something unusual is happening
