# Research Log

Daily market research, macro observations, and recurring patterns. Most recent first.

---

## Entry Format

```
## YYYY-MM-DD Pre-Market Research
- US overnight: SPX +/-X%, NDQ +/-X%
- Asia: SGX Nifty +/-X%, Hang Seng +/-X%
- India VIX: X.X (NORMAL/HIGH/LOW)
- NIFTY regime: TRENDING_UP/DOWN/RANGING, ATR X%
- FII/DII: FII bought/sold Rs X cr, DII bought/sold Rs X cr
- Key news: headline summary
- Sector focus: which sectors look strong/weak and why
- Watchlist rationale: why these picks today
```

---

## Recurring Patterns

_Patterns observed across multiple sessions. Updated by /weekly-review._

- **RSI entry zone matters for shorts:** RSI 40-50 entries profitable, RSI < 30 entries lose (oversold bounce risk). Sample: 3 trades, Apr 24.
- **STRONG_TREND_DOWN regime produces clean short signals** — all 3 shorts on Apr 24 were directionally correct, only the oversold entry lost.
- **Bot late-start misses ORB window** — session started 13:49, no ORB data captured. Full 9:30 start needed.

---

<!-- Daily research entries will be prepended here by /pre-market command -->

### 2026-04-27 Midday Update (12:03 IST)
- NIFTY: 24,026 (+0.54%) — gap-up held, TREND_DOWN daily regime but intraday green
- VIX: 18.93 (NORMAL) — conditions suitable for trading
- Bot status: 0 open positions, 0 orders placed today — bot active but no signals triggered
- Account: Rs 100 cash (paper mode), Rs 0 deployed, full daily loss headroom intact
- Top scanner picks at midday: INFY (3.05 score, high vol+mom), TCS (2.77), ICICIBANK (2.32)
- INFY: Rs 1,172.9 — continued momentum; pre-market gap-down (-3.27%) may have recovered
- RELIANCE: Rs 1,338.5, gap -1.11% — weakest scanner pick, avoid
- Afternoon outlook: cautious bullish — gap-up held but NIFTY in structural TREND_DOWN; IT sector leading
- Quote API: returning InputException (enctoken scope limitation — market data quota may require Kite Connect subscription)

## 2026-04-27 Pre-Market Research
- US overnight: SPX +0.80% (7,165 ATH), NDQ +1.63% (24,837 ATH) — tech/semis led, broad rally
- Asia: GIFT Nifty 24,045 (+147pts vs Friday close 23,898, gap UP ~0.62%), Nikkei +1.40% (ATH), Hang Seng -0.01% (flat)
- India VIX: N/A (API unavailable), estimated NORMAL based on GIFT Nifty calm gap
- NIFTY regime: TREND_DOWN (historical candles), ATR 1.68%, vol regime LOW — but gap-up opening expected
- FII/DII: FII sold Rs 8,827 cr (Apr 24), DII bought Rs 4,700 cr — continued FII selling, absorbed by DII
- USD/INR: 94.25 (weakest in 5 sessions) — bullish for IT exporters (TCS, INFY, WIPRO), bearish for crude importers
- Crude (Brent): $106.92 +1.51% — elevated and rising, bearish for India macro, watch RELIANCE
- Gold: $4,697 -0.26% — stable
- Key news: INFY Q4 done (Apr 23) — +21% profit but modest FY27 guidance (1.5-3.5% CC); stock gap -3.27%. TCS Q4 done (Apr 9) — strong. ICICIBANK Q4 done (Apr 18) — profit +8.5%, clean NPA 0.33%, analyst upgrades. RELIANCE Q4 (Apr 24) — profit -12.6%, O2C headwinds, mixed. KOTAKBANK results next week (May 2-3). India-NZ FTA signing today.
- Sector focus: IT positive (Nasdaq ATH + weak rupee = tailwind); Banking positive (ICICIBANK strong); Energy caution (RELIANCE mixed, crude high)
- Watchlist today: ICICIBANK (LONG bias, strong Q4, no events), TCS (LONG bias, IT tailwind), INFY (watch ORB — gap down may set up short or reversal, check RSI before entry)
- AVOID: RELIANCE (mixed signals), KOTAKBANK (pre-earnings caution)

## 2026-04-23 Pre-Market Research
- US overnight: SPX +1.05% (7,137.90), NDQ +1.64% (24,657.57) — tech-led rally, megacaps led
- Asia: SGX Nifty 24,210 (slightly below NSE prev close 24,378), Nikkei +0.58%, Hang Seng -0.25%
- India VIX: n/a (Kite token expired; estimated NORMAL based on macro tone)
- NIFTY regime: n/a (token refresh needed; context: SGX Nifty implies slight gap-down)
- FII/DII: Not available for Apr 22; FII sold ~₹35,000 cr HDFCBANK in Q4 (caution)
- USD/INR: 93.79, rupee -0.1% (mildly weak — bullish for IT exporters, bearish for oil importers)
- Crude (Brent): $102.28/bbl +0.36% — elevated; bearish for India macro, watch ONGC/RELIANCE
- Gold: $4744.59/oz +0.10% — stable
- Key news: INFY Q4 results TODAY after market (3:45 PM IST) — AVOID trading INFY today.
  RELIANCE results TOMORROW (Apr 24) — trade with caution. AXISBANK results Sat Apr 25 — caution.
  RBI updated PPI regulations; repo rate held at 5.25% (MPC minutes Apr 22).
  Geopolitical: US-Iran tensions, fragile ceasefire — oil price risk.
- Sector focus: IT watchful (INFY event today, US Nasdaq +1.64% overnight positive but binary risk).
  Banking strong (ICICIBANK beat estimates, positive). HDFCBANK neutral (FII selling).
  Energy caution (crude elevated, RELIANCE results tomorrow).
- Watchlist today: TCS (clean, positive), ICICIBANK (beat, tradeable), HDFCBANK (neutral/monitor)
- AVOID: INFY (results today), RELIANCE (results tomorrow), AXISBANK (results Sat)

---

### 2026-04-23 Midday Update (14:26 IST)
- Kite API: TokenException — cached token is invalid despite refresh script reporting success.
  Positions: 0 open. Orders: 0 placed today. P&L: Rs 0. Trades: 0/5.
- Account cash: Rs 600 available, Rs 0 utilised.
- Scanner: failed (tqdm module missing — run `pip3 install tqdm` to fix).
- Live quotes unavailable (token issue). Manual Kite app check recommended.
- Market context: INFY results 3:45 PM today — AVOID INFY all afternoon.
  RELIANCE results Apr 24 — trade with caution. AXISBANK results Apr 25 — avoid.
- Afternoon outlook: Neutral/unknown — no live NIFTY/VIX data. Lunch-hour lull period (12-1:30 PM).
- Action items: (1) Fix Kite token manually via browser login, (2) pip3 install tqdm, (3) restart bot after 1:30 PM if token fixed.

---

_No research logged yet. Run /pre-market before your first session._
