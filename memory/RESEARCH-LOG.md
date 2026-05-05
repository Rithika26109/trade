# Research Log

Daily market research, macro observations, and recurring patterns. Most recent first.

---

## 2026-05-05 Midday Update
- Regime remains TREND_DOWN, vol regime LOW, VIX NORMAL (API still unavailable)
- Bot healthy: running in paper mode since 09:05 IST (PID 90522), no premature EOD today
- Trades: 0/7 — all 5 watched stocks have stayed within ORB ranges all session (no breakout)
- ORB ranges locked: RELIANCE 1455–1469, ADANIENT 2450–2489, PNB 107.82–108.84, SBIN 1060–1068, INDUSINDBK 906.55–914.60
- SBIN danger zone: RSI 22–28 (extreme oversold), ADX 53–55 — strong downtrend + RSI < 30 = hard NO-TRADE per rules (no short due to oversold bounce risk; no long against downtrend)
- INDUSINDBK: RSI 35, ST bearish, below VWAP — no setup
- RELIANCE: RSI cooled from 73 (morning) to 43 now, price back inside range, ST flipped bearish — missed the morning opportunity
- Afternoon scanner: TATAPOWER emerging (score 2.31, momentum 3.2, vol 5.0, price 437.45) — not in current watchlist but worth tracking if regime shifts
- Lunch lull in effect (12:00–1:30 PM) — expect thin volume, avoid new entries until 1:30 PM+

## 2026-05-05 Pre-Market Research
- US overnight: SPX -0.41% (7,200.75), NDQ -0.19% (25,067.80), DJIA -1.13% (48,941.90) — broadly negative, geopolitical tensions in Middle East; 10/11 S&P sectors declined
- Asia: SGX Nifty 24,040 (+0.12%, +29.5 pts vs prior close 24,119.3) → flat-to-slight gap-up expected; Nikkei +0.38%; Hang Seng +1.24% — Asia broadly positive despite US weakness
- India VIX: N/A (API unavailable)
- NIFTY regime: STRONG_TREND_DOWN, ATR 1.54%, vol regime LOW — last close 24,119.3 (+0.51%); tension: regime says DOWN but NIFTY closed green yesterday + SGX gap-up
- FII/DII (May 4): DII bought Rs 4,764.16 cr (strong DII support); FII flow not confirmed but prior trend was heavy selling
- USD/INR: 95.09 (+0.18%) — rupee weakening, bullish for IT exporters (TCS, INFY, WIPRO)
- Crude (Brent): $113.41 (-0.90%) — elevated but slightly easing; still bearish India macro, watch RELIANCE, BPCL, ONGC
- Gold: $4,558.20 — stable, mild safe-haven demand; Middle East geopolitical risk ongoing
- Key news: **BINARY EVENTS TODAY — LT (Q4 results), PNB (Q4 results), M&M (Q4), Hero MotoCorp (Q4), Marico (Q4), Coforge (Q4).** LT and PNB are in scanner — HARD AVOID. RBI NBFC framework updated (small entities under Rs 1,000 cr exempted from registration, effective Jul 1 2026). SBIN Central Board meeting May 8 for Q4 results + dividend — event risk this week. TATAPOWER Q4 on May 12 — tradeable today, caution builds mid-week. ITC positive: SMIFS Buy target Rs 340, potential 17% cigarette price hike, call options at Rs 350 strike building.
- Sector focus: Energy mixed (RELIANCE +2.54% May 4, analyst "Strong Buy", but elevated crude and MarketsMojo Sell grade); FMCG positive (ITC building momentum on price hike catalyst); Banking cautious (SBIN upcoming results May 8; ICICIBANK mixed analyst consensus but positive intraday); IT cautious (USD/INR tailwind but US Nasdaq barely moved)
- Watchlist today: RELIANCE (LONG bias, score 2.68, top pick, no event today — require 2+ confirmations), ITC (LONG bias, score 1.77, gap +0.95%, price hike catalyst, SMIFS Buy), ICICIBANK (LONG/neutral, score 1.86, gap +0.07%, no event)
- AVOID: LT (Q4 results TODAY), PNB (Q4 results TODAY), ADANIENT (SL gap-through Rs 18 on May 4, re-entry violation — ban until new week), INDUSINDBK (volatile history, momentum only 0.92 today), SBIN (results May 8 — binary risk this week), KOTAKBANK (gap -1.15%, lowest momentum)
- Open bugs going into session: (1) premature EOD bug unresolved — bot may stop at ~10:35 AM, (2) single-confirmation rule not code-enforced, (3) partial qty exit bug in order_manager.py, (4) already_stopped_today veto not in code

---

## 2026-05-04 Pre-Market Research
- US overnight: SPX +0.08% (7,275.50) — nearly flat, broad-based but muted
- Asia: SGX Nifty 24,208.50 (implies gap UP ~+0.88% vs NIFTY last close 23,997.55); Nikkei +0.38%; Hang Seng -1.28% (negative drag from HK)
- India VIX: N/A (API unavailable)
- NIFTY regime: TREND_DOWN, ATR 1.56%, vol regime LOW — last close 23,997.55 (-0.74%); SGX gap-up creates tension with downtrend
- FII/DII (Apr 30): FII sold Rs 8,047.86 cr, DII bought Rs 3,487.10 cr — sustained FII selling, DII absorbing
- USD/INR: 94.89 (-0.02%) — weak rupee, bullish for IT exporters (INFY, TCS, WIPRO)
- Crude (Brent): $108.10 (-0.06%) — elevated but slightly easing; bearish India macro, watch RELIANCE, BPCL
- Gold: $4,615 (-$16) — stable, mild safe-haven demand
- Key news: KOTAKBANK Q4 FY26 results released May 2 (net profit +10% YoY, NPA improved to 1.20%, provisions -43% — POSITIVE, binary event DONE). TATAPOWER: Rs 6,500 cr investment approved for 10 GW solar manufacturing plant (strong positive catalyst). Ambuja Cements, BHEL, Tata Technologies earnings today — NOT in our watchlist. No binary events for primary watchlist today.
- Sector focus: Power/Renewables POSITIVE (TATAPOWER solar manufacturing, summer demand); Banking mixed-positive (KOTAKBANK clean post-results, ICICIBANK strong Q4 done); IT cautious (USD/INR tailwind but US flat); Energy mixed (RELIANCE profit decline, crude elevated)
- Watchlist today: TATAPOWER (LONG bias, solar catalyst, earnings May 12 — no event today), KOTAKBANK (LONG bias, clean post-results +10% profit, no event today), ICICIBANK (LONG bias, strong Q4 done, watch RSI 40-70)
- AVOID: INDUSINDBK (top scanner but volatile — 3 SL hits in W18, use with extreme caution), RELIANCE (mixed Q4, use only on 2+ confirmation), heavy-event names (BHEL etc — not in watchlist anyway)
- Open bugs going into session: (1) premature EOD bug unresolved — bot may stop at ~10:35 AM, (2) single-confirmation rule not code-enforced, (3) partial qty exit bug in order_manager.py

---

## 2026-05-04 Midday Update (12:00 IST)

- **No trades taken** this morning (9:30–12:00) — bot running clean, no signals met entry criteria
- Open positions: 0 | Orders today: 0
- Bot PIDs confirmed running (35271, 42133) — no premature EOD so far (positive vs Apr 27/29 bugs)
- Afternoon scanner top candidates: HDFCBANK (score 1.47, price 783.5), TCS (score 1.26, price 2438), DLF (score 1.24, price 601.6), LT (score 1.09, price 4122.9)
- Morning watchlist (from pre-market): TATAPOWER, KOTAKBANK, ICICIBANK — none triggered
- NIFTY regime: TREND_DOWN (from pre-market), but SGX gap-up created tension — if NIFTY held above 24,200, regime may have shifted to RANGING or TREND_UP intraday
- Lunch lull in effect (12:00–1:30 PM) — expect low-volume chop; best afternoon setups post-1:30 PM
- Capital: Rs 1,00,012.21 (unchanged — no realized P&L today)

---

## 2026-05-01 Midday Update (12:00 IST)

- **MARKET HOLIDAY** — Maharashtra Day. NSE/BSE closed. No trading session today.
- Bot correctly detected holiday at 09:18 and exited cleanly: "Market closed today (2026-05-01 — weekend or holiday)."
- Token refresh at 07:50 succeeded. 08:03 run failed (DNS/network error at that time) — non-blocking, 07:50 token was valid.
- Capital: ~Rs 1,00,012 (unchanged from Apr 30 close).
- No action needed. All launchd routines resume tomorrow (May 2, Friday).
- Open items going into May 2: (1) premature EOD bug unresolved, (2) partial qty exit bug in order_manager.py, (3) single-confirmation filter not yet enforced in code.

---

## 2026-04-30 Midday Update (12:05 IST)

- Regime: TREND_DOWN (NIFTY -1.37% to 23,846.75). Vol regime: LOW.
- Bot trades today: 2/5 used. RELIANCE SHORT entered 09:40 (VWAP_ST, 1-strategy only), SL hit 11:30 at 1407.10, -Rs 9.34 (13 qty). RELIANCE BUY entered 11:40 (RSI_EMA, 1-strategy only) — open at 12:05.
- ALERT: Both trades violated Apr 29 lesson (require 2+ strategy confirmations). Bot is still taking single-confirmation entries.
- ALERT: Same-stock re-entry same day (SHORT then LONG RELIANCE) — violates Apr 29 lesson on re-entries after SL.
- Afternoon top scanner: INDUSINDBK score=3.14 (BANNED today — 2 SL hits Apr 29), RELIANCE=2.87, ITC=2.53, ICICIBANK=2.49, BHARTIARTL=2.24.
- ADANIENT still on scanner list despite Q4 results today — manual override remains active.
- Kite quote API: still returning InputException (enctoken limitation, non-blocking).
- Realized P&L: -Rs 9.34 | Unrealized: open RELIANCE BUY qty 21 @ 1405.80 | Risk headroom: ~Rs 2,990 remaining.

## 2026-04-29 Midday Update (12:00 IST)

- Regime: STRONG_TREND_UP (bot confirmed, ADX=49.6 on RELIANCE)
- Bot started at 09:05 — ON TIME. But premature EOD bug fired AGAIN at 10:35 AM (same as 2026-04-27). Bot restarted at 10:36, then again at 11:34. Root cause unresolved — urgent fix needed.
- 3 open paper trades entered at ~11:34 on 3rd bot instance:
  - LONG RELIANCE | 21 qty | Entry 1420.91 | SL 1413.50 | Target 1433.70 | ADX=49.6
  - LONG INFY | 25 qty | Entry 1173.09 | SL 1166.60 | Target 1184.40 | ADX=43.6
  - SHORT TATAPOWER | 65 qty | Entry 455.87 | SL 458.10 | Target 452.05 | RSI=31.0 (borderline rule)
- Unrealized P&L at 11:59: +Rs 50.21 | Realized: Rs 0
- Watchlist: INDUSINDBK (top score 2.86), RELIANCE (2.82), INFY (2.82), TATAPOWER (2.47), ADANIENT (2.31)
- Kite quote API: returning InputException — cannot fetch live prices mid-session
- ⚠️ TATAPOWER short entered with RSI=31.0 — strategy hard rule is RSI < 30 is rejected. This passed but is borderline; watch for oversold bounce.

## 2026-04-28 Midday Update (12:00 IST)

- Regime: RANGING all morning (09:30–12:00), no regime shift
- NIFTY: 24037 (-0.23%), daily regime TREND_DOWN
- VIX: 17.88 (NORMAL)
- Trades: 0 executed — 7 signals rejected by risk filter (R:R < 1.5 across all)
  - Rejections: BHARTIARTL x2 (0.81–0.82), HDFCBANK x3 (0.95–1.18), ICICIBANK (0.96), TCS (1.28)
- Bot: healthy, on time, scanning every 5 min
- Top afternoon candidates: INFY (score 3.05), TCS (2.39), ICICIBANK (2.06)
- Pattern: RANGING market generating sub-1.5 R:R setups — correct to skip, not a bot bug
- Note: No-trade morning is valid behavior — do not override risk filters

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
- **Bot late-start misses ORB window** — session started 13:49 (Apr 24), no ORB data captured. Full 9:30 start needed.
- **Premature EOD bug systematically kills ORB strategy (W18):** Bug fired at ~10:35 AM on Apr 27 and Apr 29 (3 times across week). After bot restart, opening range window is gone, so all entries fall to RSI+EMA / VWAP+ST. Result: ORB ran 0 trades in W18 despite being the primary strategy. Fix `wind-down` time comparison in commit 943a95b.
- **Daily regime mispredicts intraday reversals (W18):** 1/4 accuracy — pre-market correctly identified TREND_DOWN at the daily level but intraday price action reversed UP on Apr 28, 29, 30. Daily regime alone is not a reliable directional bias for intraday entries.
- **R:R filter is the strongest discipline guardrail (W18):** On Apr 28 (RANGING), 7 signals were correctly rejected for sub-1.5 R:R. On Apr 27, all signals rejected for poor R:R. The filter saved capital on weak setups even when other rules (2+ confirmation, binary-event block) failed.
- **Rule violations cluster on profitable days (W18):** Apr 30 had 67% win rate and +Rs 203 P&L but violated 3 rules (single-confirmation x3, binary-event trade, partial qty exits). Profit reinforces the rule break — explicit code enforcement needed.

---

<!-- Daily research entries will be prepended here by /pre-market command -->

## 2026-04-30 Pre-Market Research
- US overnight: SPX/NDQ placeholders (Gemini API returned no real-time data) — use Apr 29 context: SPX ~7138 (-0.49%), NDQ ~24663 (-0.90%), tech weakness
- Asia: GIFT Nifty not confirmed; NIFTY prior close 24,177.65 (+0.76% recovery from Apr 29 lows of ~23,995)
- India VIX: N/A (API unavailable)
- NIFTY regime: TREND_DOWN, ATR 1.55%, vol regime LOW — yesterday closed up +0.76% (24,177.65), short-term bounce within downtrend
- Scanner top 5: INFY (2.58, IT), INDUSINDBK (2.56, Banking), RELIANCE (2.44, Energy), SAIL (2.37, Metals), TATAPOWER (2.35, Power)
- Key news: ADANIENT Q4 FY26 results TODAY (binary event, AVOID). TATAPOWER earnings May 12 (no event today, tradeable). KOTAKBANK results ~May 3 (avoid). INFY post-results ADR -5.49% + analyst PT cut (TD Cowen to $13) — mixed despite Q4 beat. TCS strong (25.3% margins, AI revenue $2.3B). ICICIBANK strong Q4 done (profit +8.5%, NPA 0.33%).
- Sector focus: IT cautious (INFY post-result hangover, wait RSI 40-60); Banking mixed (ICICIBANK tradeable, HDFCBANK FII selling → avoid); Power/Renewables positive (TATAPOWER tailwinds — heat wave demand + renewables); Energy mixed (RELIANCE profit -12.6% Q4, Jio IPO LT positive)
- Watchlist today: RELIANCE (scan 2.44, caution bias, wait 2+ confirmations), TATAPOWER (scan 2.35, LONG bias, power demand tailwind, no event risk), ICICIBANK (scan 2.14, LONG bias, clean Q4)
- AVOID: ADANIENT (earnings today — binary risk), HDFCBANK (FII selling, mixed), INFY (analyst downgrade + ADR drop — wait for RSI to confirm 40-60 before entry), INDUSINDBK (SL hit yesterday + re-entry rule applies)

## 2026-04-29 Pre-Market Research
- US overnight: SPX -0.49% (7,138.80), NDQ -0.90% (24,663.80) — tech weakness led by AI/OpenAI valuation concerns; energy/defensives strong
- Asia: GIFT Nifty 24,098 (+31pts, +0.13% vs prior close 23,995) → slight gap-UP opening; Nikkei -1.02%, Hang Seng -0.95% (Asia broadly weak)
- India VIX: unavailable (API) — gap size suggests NORMAL; no panic
- NIFTY regime: TREND_DOWN, ATR 1.58%, vol regime LOW — NIFTY closed at 23,995 (-0.40% prior day), downtrend intact
- FII/DII (Apr 28): FII sold Rs 2,103.74 cr, DII bought Rs 1,712.01 cr — net outflow Rs 391.73 cr; FII selling pressure persists
- USD/INR: 94.52 (+0.34%) — rupee weakening; bullish for IT exporters (TCS, INFY, WIPRO)
- Crude (Brent): $111.67 (+0.37%) — rising, elevated; bearish India macro, watch RELIANCE, BPCL, ONGC
- Gold: $4,602 — stable, mild safe-haven demand (US-Iran, Strait of Hormuz risk)
- Key news: No major India earnings today (clean slate). FOMC decision this week — macro uncertainty. RBI ECL provisioning finalized (Apr 2027 implementation, banking sector neutral near-term). TATAPOWER 52-week high (460), TP Urja subsidiary formed. ADANIENT — Google AI hub Vizag partnership (positive). TCS-Siemens AI MoU extended (positive). TCS court case (Nashik conversion) — hearing May 2 (minor risk). ICICIBANK: 5th straight down session despite strong Q4.
- Sector focus: IT cautiously positive (weak rupee tailwind, but US Nasdaq -0.90% cap upside); Power sector strong (TATAPOWER breakout, summer demand outlook); Adani group positive (AI infra catalyst); Banking mixed (ICICIBANK weak near-term, RBI ECL clarity long-term positive)
- Watchlist today: TATAPOWER (LONG bias, strong mom, 52-week high), ADANIENT (LONG bias, AI catalyst, institutional buying), INFY (watch ORB — gap -0.65%, technical buy signals but FY27 guidance overhang; wait RSI 40-60)
- AVOID: KOTAKBANK (pre-earnings May 2-3, ongoing risk), BANKBARODA/PNB (PSU banks, RBI ECL provisioning uncertainty), TCS (court case May 2 minor overhang)

## 2026-04-28 Pre-Market Research
- US overnight: SPX +0.12% (7,173.91), NDQ +0.20% (24,887.10) — tech-led narrow gain; DJIA -0.13% (mixed breadth)
- Asia: SGX Nifty 24,043 (-0.32% vs 24,119 prior close) → gap-DOWN ~0.3% expected; Nikkei -0.43%, Hang Seng -0.43%
- India VIX: N/A (API unavailable) — estimated NORMAL given contained gap size
- NIFTY regime: STRONG_TREND_DOWN, ATR 1.62%, vol regime LOW — multi-day downtrend intact; gap-down opening likely resumes pressure
- FII/DII: FII sold Rs 944.47 cr (Apr 27), DII bought Rs 3,871.11 cr — DII absorbing FII selling; net bearish flow
- USD/INR: Not confirmed today; prior 94.25 (weak rupee) — bullish for IT exporters if sustained
- Crude (Brent): ~$108.63 +0.37% — elevated and rising; bearish India macro, watch RELIANCE, ONGC; inflationary risk
- Gold: ~$4,692 +0.13% — slight safe-haven demand; US/Iran tensions ongoing (Strait of Hormuz)
- Key news: Maruti Suzuki Q4 results TODAY — auto sector event. KOTAKBANK results May 3 (avoid this week). RBI ECL provisioning from Apr 2027 (banking sector clarity). TCS-Siemens Energy AI partnership (positive TCS sentiment). INFY dropped from top-10 most-valuable after weak FY27 guidance (1.5-3.5% CC).
- Sector focus: IT mixed (TCS strong Q4, INFY weak guidance — sector sentiment net cautious); Banking positive (ICICIBANK, HDFCBANK strong Q4 done); Energy caution (crude high, RELIANCE mixed)
- Watchlist today: TCS (LONG bias, strong earnings, AI partnership), ICICIBANK (LONG bias, clean Q4, analyst upgrades), INFY (CAUTION — weak guidance overhang, scanner top pick but sentiment negative; wait for RSI 40-60 before entry)
- AVOID: KOTAKBANK (pre-earnings May 3, analyst downgrade, investigation), RELIANCE (momentum score low, negative gap -1.11%)

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
