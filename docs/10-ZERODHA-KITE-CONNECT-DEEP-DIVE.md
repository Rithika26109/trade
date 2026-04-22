# Zerodha Kite Connect API — Deep Dive

Everything you need to know about what the Kite Connect API can do, how it works, what it costs, and what to watch out for. Written for someone who has never used a broker API before.

---

## Table of Contents

1. [What Even Is Kite Connect?](#1-what-even-is-kite-connect)
2. [Setting Up — The "Website" Question Answered](#2-setting-up--the-website-question-answered)
3. [How Login Works (The Auth Flow)](#3-how-login-works-the-auth-flow)
4. [Everything You Can Do With the API](#4-everything-you-can-do-with-the-api)
5. [Rate Limits — How Much Can You Hit the API?](#5-rate-limits--how-much-can-you-hit-the-api)
6. [Costs](#6-costs)
7. [Common Pitfalls That Waste Hours](#7-common-pitfalls-that-waste-hours)
8. [SEBI Algo Rules (April 2026)](#8-sebi-algo-rules-april-2026)
9. [Quick Reference Cheatsheet](#9-quick-reference-cheatsheet)

---

## 1. What Even Is Kite Connect?

Kite Connect is Zerodha's official API that lets you write code to do anything you'd normally do on the Kite website or app — place orders, check positions, get live prices, pull historical charts, and more.

Think of it like this:
- **Kite web/app** = you click buttons to trade
- **Kite Connect API** = your Python code "clicks those buttons" for you

It uses standard HTTP REST calls + WebSocket for real-time streaming. The official Python library is `pykiteconnect` (`pip install kiteconnect`).

**Official docs:** https://kite.trade/docs/connect/v3/

---

## 2. Setting Up — The "Website" Question Answered

### Step-by-step account creation

1. **You need a Zerodha trading account first.** If you don't have one, sign up at zerodha.com (takes a few days for verification).

2. **Go to https://developers.kite.trade/** and sign up for a developer account.

3. **Click "Create new app."** This is where the confusion starts. It asks you for:

| Field | What to put | Why |
|-------|------------|-----|
| **App name** | Anything. `my-trading-bot` works. | Just a label for your reference |
| **Zerodha Client ID** | Your trading account ID (e.g., `AB1234`) | Links the app to your account |
| **Redirect URL** | `http://127.0.0.1` | **This is the "website" that confused you. See below.** |
| **Description** | Anything. `personal intraday bot` | Just a description |
| **Postback URL** | Leave blank | Optional webhook, you don't need it |

4. **Choose a plan:**
   - **Personal (Free)** — lets you place orders, check positions, margins. NO live market data, NO historical candles.
   - **Connect (Rs 500/month)** — everything. Live streaming, historical candles, the works. **You need this for a trading bot.**

5. **After creating the app**, you get two values:
   - `api_key` — your public app ID (safe to share, but don't)
   - `api_secret` — your private key (**NEVER share this, NEVER commit to git**)

### So what IS the "Redirect URL" / "Website"?

This is the single most confusing part of the setup. Here's what's actually happening:

**You do NOT need a real website.**

When you log into Zerodha through the API, the login happens in a browser. After you enter your username, password, and TOTP code, Zerodha needs to send you back somewhere with a special token. The "Redirect URL" is where it sends you.

For a personal bot running on your laptop, you set it to:
```
http://127.0.0.1
```

That's `localhost` — your own computer. After login, your browser will redirect to something like:
```
http://127.0.0.1?request_token=abc123xyz&action=login&status=success
```

Your bot grabs `request_token=abc123xyz` from that URL and uses it to get an access token. That's it.

**Other options that also work:**
- `http://127.0.0.1:5000/callback` (if you're running a local Flask server to catch it)
- `https://google.com` (you just manually copy the token from the URL bar — ugly but works for testing)

**What the Redirect URL is NOT:**
- NOT a website you need to build
- NOT a website you need to host
- NOT something that needs to be on the internet
- NOT your Zerodha login page

### What about the "Postback URL"?

This is completely different and completely optional. If you set a postback URL, Zerodha will send a POST request to that URL every time one of your orders gets filled, cancelled, or rejected. It's a webhook.

- Must be a publicly accessible HTTPS URL (not localhost)
- You don't need it. Your bot can check order status via polling or WebSocket instead.
- **Leave it blank.**

---

## 3. How Login Works (The Auth Flow)

Kite Connect uses an OAuth-style login. This happens once per day.

### The flow, step by step

```
Step 1: Your bot opens this URL in a browser
        https://kite.zerodha.com/connect/login?v=3&api_key=YOUR_API_KEY

Step 2: You (or your bot) enters username + password + TOTP code

Step 3: Zerodha redirects the browser to your Redirect URL with a request_token
        http://127.0.0.1?request_token=XXXXXX&action=login&status=success

Step 4: Your bot extracts the request_token and exchanges it for an access_token
        POST https://api.kite.trade/session/token
        Body: api_key, request_token, checksum (SHA-256 of api_key + request_token + api_secret)

Step 5: You get back an access_token. Use this for ALL API calls the rest of the day.
        Header: Authorization: token YOUR_API_KEY:YOUR_ACCESS_TOKEN
```

### In Python

```python
from kiteconnect import KiteConnect

kite = KiteConnect(api_key="your_api_key")

# Step 1: get the login URL
print(kite.login_url())
# Opens: https://kite.zerodha.com/connect/login?v=3&api_key=...

# Step 4: after you get the request_token from the redirect
data = kite.generate_session("the_request_token", api_secret="your_api_secret")
kite.set_access_token(data["access_token"])

# Done! Now you can use the API
print(kite.profile())
```

### Token lifetimes

| Token | Lifetime | Notes |
|-------|----------|-------|
| **request_token** | ~2-3 minutes | One-time use. Grab it fast. |
| **access_token** | Until 6:00 AM IST next day | This is your daily pass. Invalidated if you log out of Kite web/app. |
| **refresh_token** | Same as access_token | Can renew via `kite.renew_access_token()` |

**Key fact: You must log in every single day.** The access token expires at 6 AM IST daily. There is no way around this — it's a regulatory requirement.

### TOTP (the 2FA code)

Since October 2021, TOTP (Time-based One-Time Password) is mandatory for all Kite Connect logins. This is the 6-digit code from Google Authenticator or Authy.

When you set up TOTP on your Zerodha account, you see a QR code AND a text secret (looks like `JBSWY3DPEHPK3PXP`). **Save that text secret.** Your bot can generate the 6-digit code from it:

```python
import pyotp
totp = pyotp.TOTP("JBSWY3DPEHPK3PXP")  # your TOTP secret
code = totp.now()  # "482917" — the same code your authenticator app shows
```

### Automating daily login

Zerodha officially says: "Traders must log in manually at least once a day." But for a bot, people commonly automate it using:

1. **Selenium/requests + pyotp** — simulate the browser login, auto-fill credentials and TOTP, extract the request_token from the redirect URL.
2. **Semi-manual** — log in manually each morning, paste the request_token, let the bot handle the rest.

Method 1 is what most serious bots use. It works, but occasionally breaks when Zerodha updates their login page HTML.

---

## 4. Everything You Can Do With the API

### 4A. Get Live Market Prices (Quotes)

Pull current prices for any stock, index, or derivative.

| Endpoint | What you get | Max instruments per call |
|----------|-------------|------------------------|
| `kite.ltp("NSE:INFY")` | Last traded price only | 1,000 |
| `kite.ohlc("NSE:INFY")` | Open, High, Low, Close + LTP | 1,000 |
| `kite.quote("NSE:INFY")` | Everything: LTP, OHLC, volume, 5-level market depth, OI, circuit limits | 500 |

**Format:** Always use `EXCHANGE:SYMBOL` — e.g., `NSE:RELIANCE`, `BSE:TCS`, `NFO:NIFTY24APRFUT`.

```python
# Single stock
quote = kite.ltp("NSE:INFY")
print(quote["NSE:INFY"]["last_price"])  # 1452.30

# Multiple stocks at once
quotes = kite.quote("NSE:INFY", "NSE:RELIANCE", "NSE:TCS")
for symbol, data in quotes.items():
    print(f"{symbol}: {data['last_price']}, Vol: {data['volume']}")
```

**Full quote fields include:**
- `last_price`, `last_quantity`, `last_trade_time`
- `ohlc` → `open`, `high`, `low`, `close` (today's values)
- `volume`, `average_price`
- `buy_quantity`, `sell_quantity` (total bid/ask quantities)
- `depth` → `buy[0..4]`, `sell[0..4]` (5-level order book with price, quantity, orders)
- `oi` (open interest, for F&O)
- `lower_circuit_limit`, `upper_circuit_limit`
- `net_change` (absolute change from previous close)

### 4B. Historical Candle Data

Pull OHLCV candles for backtesting or analysis. **Requires the Connect plan (Rs 500/month).**

**Available timeframes:** `minute`, `3minute`, `5minute`, `10minute`, `15minute`, `30minute`, `60minute`, `day`

**Important:** There is NO weekly or monthly timeframe. You must aggregate day candles yourself.

```python
from datetime import date

data = kite.historical_data(
    instrument_token=408065,      # INFY's instrument token (not the symbol!)
    from_date=date(2026, 4, 1),
    to_date=date(2026, 4, 22),
    interval="5minute",
    oi=False                      # set True for F&O open interest
)
# Returns: [{"date": datetime, "open": 1450, "high": 1455, "low": 1448, "close": 1452, "volume": 123456}, ...]
```

**How much data can you pull in one request?**

| Interval | Max days per request |
|----------|---------------------|
| minute (1min) | 60 days |
| 3minute | 100 days |
| 5minute | 100 days |
| 10minute | 100 days |
| 15minute | 200 days |
| 30minute | 200 days |
| 60minute | 400 days |
| day | 2,000 days (~5.5 years) |

Need more? Make multiple requests with different date ranges.

**Gotcha:** You need the `instrument_token` (a number), not the symbol name. See Section 4H for how to get it.

### 4C. Real-Time Streaming (WebSocket)

Get live tick-by-tick prices pushed to your bot. No polling needed. **Requires Connect plan.**

```python
from kiteconnect import KiteTicker

kws = KiteTicker("your_api_key", "your_access_token")

def on_ticks(ws, ticks):
    for tick in ticks:
        print(f"{tick['instrument_token']}: Rs {tick['last_price']}")

def on_connect(ws, response):
    # Subscribe to instruments (using instrument_tokens, not symbols!)
    ws.subscribe([408065, 738561])
    ws.set_mode(ws.MODE_FULL, [408065])  # full depth for this one

kws.on_ticks = on_ticks
kws.on_connect = on_connect
kws.connect(threaded=True)  # runs in background thread
```

**Three streaming modes:**

| Mode | What you get | Packet size |
|------|-------------|-------------|
| `MODE_LTP` | Last traded price only | 8 bytes |
| `MODE_QUOTE` | LTP + OHLC + volume + buy/sell quantity | 44 bytes |
| `MODE_FULL` | Everything including 5-level market depth | 184 bytes |

**Limits:**
- Max 3 WebSocket connections per API key
- Max 3,000 instruments per connection
- Max 9,000 total instruments across all connections
- If no data flows, a 1-byte heartbeat keeps the connection alive

**Events you can handle:**
- `on_ticks` — price updates
- `on_connect` — connection established
- `on_close` — connection closed
- `on_error` — error occurred
- `on_reconnect` — auto-reconnect attempt
- `on_order_update` — order status changes (fills, cancellations, rejections)

The `on_order_update` callback is powerful — it fires for orders placed from ANY source (web, app, API), not just your bot.

### 4D. Place Orders

The core of any trading bot.

```python
order_id = kite.place_order(
    variety=kite.VARIETY_REGULAR,
    tradingsymbol="INFY",
    exchange=kite.EXCHANGE_NSE,
    transaction_type=kite.TRANSACTION_TYPE_BUY,
    quantity=1,
    order_type=kite.ORDER_TYPE_MARKET,
    product=kite.PRODUCT_MIS,          # MIS = intraday
    validity=kite.VALIDITY_DAY,
    tag="MYBOT01"                       # optional 20-char tag for tracking
)
print(f"Order placed: {order_id}")
```

**Order varieties:**

| Variety | What it is |
|---------|-----------|
| `regular` | Standard order — most common |
| `amo` | After Market Order — place outside market hours, executes next open |
| `co` | Cover Order — comes with a mandatory stop-loss leg |
| `iceberg` | Splits a large order into 2–50 smaller legs to reduce market impact |
| `auction` | For participating in call auctions |

**Order types:**

| Type | When to use | Required params |
|------|------------|----------------|
| `MARKET` | Buy/sell at whatever the current price is | `quantity` only |
| `LIMIT` | Buy/sell only at a specific price or better | `quantity`, `price` |
| `SL` | Stop-loss limit — triggers at `trigger_price`, then places a limit order at `price` | `quantity`, `trigger_price`, `price` |
| `SL-M` | Stop-loss market — triggers at `trigger_price`, then fills at market price | `quantity`, `trigger_price` |

**Products (position types):**

| Product | What it is |
|---------|-----------|
| `MIS` | Margin Intraday Squareoff — intraday only, auto-squared-off by 3:15-3:25 PM |
| `CNC` | Cash and Carry — delivery, for holding overnight (equities) |
| `NRML` | Normal — for F&O overnight positions |

**NEW (April 2026): Market Protection**

MARKET and SL-M orders now require a `market_protection` parameter. This is the maximum % the fill price can deviate from LTP. Minimum is 1%. Orders with `market_protection=0` get rejected.

```python
kite.place_order(
    variety=kite.VARIETY_REGULAR,
    tradingsymbol="INFY",
    exchange=kite.EXCHANGE_NSE,
    transaction_type=kite.TRANSACTION_TYPE_BUY,
    quantity=1,
    order_type=kite.ORDER_TYPE_MARKET,
    product=kite.PRODUCT_MIS,
    validity=kite.VALIDITY_DAY,
    market_protection=3           # allow up to 3% slippage
)
```

### 4E. Modify and Cancel Orders

```python
# Modify an open order (change price, quantity, etc.)
kite.modify_order(
    variety=kite.VARIETY_REGULAR,
    order_id="241016000123456",
    quantity=2,                     # new quantity
    price=1460.0                    # new price
)

# Cancel an open order
kite.cancel_order(
    variety=kite.VARIETY_REGULAR,
    order_id="241016000123456"
)
```

**Max 25 modifications per order.**

### 4F. Check Orders and Trades

```python
# All orders placed today (all statuses)
orders = kite.orders()
for o in orders:
    print(f"{o['tradingsymbol']} {o['transaction_type']} {o['status']}")

# Full history of a single order (every status change)
history = kite.order_history("241016000123456")
# Shows: OPEN → VALIDATION → OPEN → COMPLETE (or REJECTED, CANCELLED)

# All executed trades today
trades = kite.trades()

# Trades from a specific order
order_trades = kite.order_trades("241016000123456")
```

**Order statuses:**
`OPEN` → `VALIDATION` → `OPEN` → `COMPLETE` / `CANCELLED` / `REJECTED`

Also: `TRIGGER PENDING` (for SL orders waiting to trigger), `MODIFY VALIDATION`, `MODIFY PENDING`, `CANCEL PENDING`.

### 4G. Positions, Holdings, Margins

```python
# Current intraday + overnight positions
positions = kite.positions()
# Returns: {"net": [...], "day": [...]}
# "net" = net positions across days, "day" = today's intraday positions

# Equity delivery holdings
holdings = kite.holdings()

# Account margins/funds
margins = kite.margins()
# Returns: {"equity": {...}, "commodity": {...}}
# equity.available.cash, equity.utilised.debits, etc.

# Check margin BEFORE placing an order
margin_needed = kite.order_margins([{
    "tradingsymbol": "INFY",
    "exchange": "NSE",
    "transaction_type": "BUY",
    "quantity": 10,
    "order_type": "MARKET",
    "product": "MIS"
}])
print(f"Margin needed: Rs {margin_needed[0]['total']}")

# Convert position type (e.g., MIS to CNC before square-off)
kite.convert_position(
    tradingsymbol="INFY",
    exchange="NSE",
    transaction_type="BUY",
    quantity=1,
    old_product="MIS",
    new_product="CNC"
)
```

### 4H. The Instruments List (How to Get instrument_tokens)

Many API calls need `instrument_token` (a number), not the symbol name. You get the mapping by downloading the instruments list.

```python
# Download all NSE instruments
instruments = kite.instruments("NSE")
# Returns: list of dicts, one per instrument

# Find INFY's instrument_token
for inst in instruments:
    if inst["tradingsymbol"] == "INFY":
        print(inst["instrument_token"])  # 408065
        break
```

**Each instrument has:**
- `instrument_token` — unique numeric ID (used for WebSocket and historical data)
- `exchange_token` — exchange-issued ID (rarely needed)
- `tradingsymbol` — the symbol string (used for orders and quotes)
- `name` — company name
- `last_price` — NOT real-time, just a reference
- `expiry` — for derivatives
- `strike` — for options
- `tick_size` — minimum price movement (e.g., 0.05 for most NSE stocks)
- `lot_size` — minimum tradeable quantity
- `instrument_type` — EQ (equity), FUT, CE (call option), PE (put option), etc.
- `segment` — NSE, BSE, NFO, BFO, CDS, MCX, etc.
- `exchange` — NSE, BSE

**The raw download is a big CSV** (~15 MB for all exchanges, ~3 MB for NSE only). Download it once daily and store locally.

Direct URL: `GET https://api.kite.trade/instruments` (all) or `GET https://api.kite.trade/instruments/NSE` (NSE only). Needs auth header.

**Important:** For F&O contracts, instrument_tokens get recycled after expiry. A token that was NIFTY APR FUT today might be assigned to a different contract after April expiry. Always re-download daily.

### 4I. GTT Orders (Good Till Triggered)

GTT orders sit on Zerodha's servers (not the exchange) and trigger when the LTP hits your price. Great for set-and-forget stop-losses or targets that persist across days.

**Two types:**

| Type | What it does | Example |
|------|-------------|---------|
| **Single** | One condition, one order | "Sell INFY if price drops to 1400" |
| **Two-leg (OCO)** | Two conditions — one cancels the other | "Sell INFY if it drops to 1400 (stop-loss) OR rises to 1600 (target)" |

```python
# Single trigger GTT
gtt_id = kite.place_gtt(
    trigger_type=kite.GTT_TYPE_SINGLE,
    tradingsymbol="INFY",
    exchange="NSE",
    trigger_values=[1400.0],           # trigger when LTP hits 1400
    last_price=1452.0,                 # current LTP (required for validation)
    orders=[{
        "transaction_type": "SELL",
        "quantity": 10,
        "price": 1400.0,              # limit price for the order
        "order_type": "LIMIT",
        "product": "CNC"
    }]
)

# Two-leg (OCO) GTT — stop-loss at 1400, target at 1600
gtt_id = kite.place_gtt(
    trigger_type=kite.GTT_TYPE_OCO,
    tradingsymbol="INFY",
    exchange="NSE",
    trigger_values=[1400.0, 1600.0],    # [stop-loss, target]
    last_price=1452.0,
    orders=[
        {"transaction_type": "SELL", "quantity": 10, "price": 1400.0,
         "order_type": "LIMIT", "product": "CNC"},
        {"transaction_type": "SELL", "quantity": 10, "price": 1600.0,
         "order_type": "LIMIT", "product": "CNC"},
    ]
)

# List all active GTTs
gtts = kite.get_gtts()

# Cancel a GTT
kite.delete_gtt(gtt_id)
```

**GTT limitations:**
- Only LIMIT orders (no MARKET orders)
- Triggers on LTP only (not on indicators or volume)
- GTTs for equity (CNC) persist until triggered or cancelled
- GTTs for intraday (MIS) are auto-cancelled at end of day
- Max active GTTs: check Zerodha's current limit (was around 20-50)

### 4J. Postback Webhooks (Order Notifications)

If you set a Postback URL in your app settings, Zerodha POSTs to it when orders change status.

**When it fires:** `COMPLETE`, `CANCELLED`, `REJECTED`, `UPDATE` (modification or partial fill)

**Payload includes:** order_id, status, tradingsymbol, exchange, transaction_type, quantity, filled_quantity, average_price, timestamps, and more.

**Security:** Each payload includes a checksum:
```
checksum = SHA-256(order_id + order_timestamp + api_secret)
```
Always verify this before trusting the payload.

**For personal bots, you probably don't need postbacks.** Use `kws.on_order_update` (WebSocket) instead — it's simpler and catches orders from all platforms (web, app, API), not just API orders.

---

## 5. Rate Limits — How Much Can You Hit the API?

| What | Limit |
|------|-------|
| **General API calls** | 10 requests/second per API key |
| **Quote endpoint** (`/quote`) | 1 request/second |
| **Historical data** | 3 requests/second |
| **Order placement** | 10 orders/second |
| **Orders per minute** | 400 |
| **Orders per day** | 5,000 per API key |
| **Order modifications** | 25 per order |
| **WebSocket connections** | 3 per API key |
| **WebSocket instruments** | 3,000 per connection (9,000 total) |

### What happens when you exceed limits?

You get **HTTP 429 (Too Many Requests)**. The block is temporary — wait 1 second and retry. Implement exponential backoff or a simple sleep.

### Practical implications for a personal bot

With 5 trades/day and 10 stocks to monitor, you'll never come close to any limit. The historical data limit (3 req/sec) is the one you'll hit most often when downloading backtest data for multiple stocks — just add a 0.4-second delay between calls.

---

## 6. Costs

### API subscription

| Plan | Monthly cost | What you get |
|------|-------------|-------------|
| **Personal** | Free (Rs 0) | Orders, positions, holdings, margins, GTT |
| **Connect** | Rs 500/month | Everything in Personal + live WebSocket streaming + historical candle data |

The Connect plan was reduced from Rs 2,000/month to Rs 500/month in May 2025. There's sometimes a free 1-day trial when you first sign up.

### Per-order API charges

**None.** The API does not charge per order.

### Normal brokerage still applies

The API is just a different way to place orders. You pay the same Zerodha brokerage as on the web/app:

| Segment | Brokerage |
|---------|-----------|
| Equity intraday (MIS) | Rs 20 per executed order or 0.03% — whichever is lower |
| Equity delivery (CNC) | Zero (free) |
| F&O (futures + options) | Rs 20 per executed order |

Plus: STT, exchange transaction charges, GST, SEBI turnover fee, stamp duty. These are unavoidable regulatory charges.

### What you need to budget

For a personal intraday bot: **Rs 500/month** for Connect + normal brokerage on trades. That's it.

---

## 7. Common Pitfalls That Waste Hours

### Pitfall 1: instrument_token vs tradingsymbol

This confuses everyone at first.

| Identifier | Type | Used for | Example |
|-----------|------|----------|---------|
| `tradingsymbol` | String | Orders, quotes | `"INFY"` |
| `instrument_token` | Integer | WebSocket, historical data | `408065` |
| `exchange_token` | Integer | Exchange-internal (rarely needed) | `12345` |

They are NOT interchangeable. If you try to subscribe to WebSocket with `"INFY"` instead of `408065`, it silently fails.

**Fix:** Download instruments list daily, build a symbol-to-token lookup dict.

### Pitfall 2: Token expires at 6 AM daily

Your access token dies at 6:00 AM IST every day. No exceptions. If your bot ran fine yesterday and fails today at 9:15 AM, this is why.

Also: if you log into Kite web or app on your phone, it may invalidate your API session (master logout). Don't log in elsewhere while the bot is running.

### Pitfall 3: The first candle is garbage

The 9:15 AM candle has wild OHLC values because of the opening auction. Many strategies produce false signals from this candle. Standard practice: skip the first 15 minutes (9:15–9:30) and start analyzing from 9:30 onwards.

### Pitfall 4: request_token expires in minutes

After login, you get a `request_token` in the redirect URL. You have ~2-3 minutes to exchange it for an `access_token`. If you take too long (maybe you went to grab coffee), it expires and you need to log in again.

### Pitfall 5: quote() returns missing keys for dead instruments

If you request a quote for an expired or invalid instrument, the key is simply missing from the response dict. No error is thrown. Always check `if symbol in response:` before accessing fields.

### Pitfall 6: Historical data returns incomplete current candle

During market hours, the most recent candle in historical data is still forming. Its high/low/close/volume will keep changing. Don't treat it as final data until the candle's time period has ended.

### Pitfall 7: MIS auto-square-off

Zerodha auto-squares-off MIS positions between 3:15–3:25 PM. If your bot hasn't exited by then, Zerodha will close your positions for you — often at worse prices. Exit well before 3:15 PM.

### Pitfall 8: Paper trading doesn't exist in the API

There is no sandbox or paper trading mode in Kite Connect. If you call `kite.place_order()`, it places a real order with real money. Paper trading must be built into your bot's code by simulating fills against real market data without actually placing orders.

### Pitfall 9: F&O instrument tokens get recycled

After a derivative contract expires, its instrument_token may be reassigned to a new contract. If you hardcoded an instrument_token for "NIFTY APR FUT", it will point to a different contract after April expiry. Always re-download the instruments list.

### Pitfall 10: Selenium login breaks randomly

If you automate login with Selenium, it will break whenever Zerodha updates their login page HTML (new class names, different element IDs, added captcha). Keep your login script updated and have a manual fallback.

---

## 8. SEBI Algo Rules (April 2026)

### What qualifies as algorithmic trading?

Any order placed via API — even a single order from a Python script — is technically "algorithmic trading" under SEBI's definition.

### What do you need as a personal user?

| Requirement | Personal bot (under 10 orders/sec) | Notes |
|------------|-----------------------------------|-------|
| **Static IP** | Yes, mandatory since April 2026 | Register on developers.kite.trade dashboard |
| **Algo-ID** | Generic one from Zerodha | No exchange registration needed |
| **TOTP 2FA** | Yes, mandatory since 2021 | Already required for all Kite Connect apps |
| **Market protection** | Yes, on MARKET/SL-M orders | Minimum 1%, set via `market_protection` param |
| **Exchange registration** | No | Only if you exceed 10 orders/sec |
| **Research Analyst license** | No | Only if you sell/distribute your algo |

### How to get a static IP

- **Home broadband:** Ask your ISP for a static IP. Usually Rs 200-500/month extra.
- **Cloud VPS:** Any AWS/GCP/DigitalOcean instance comes with a static IP by default.
- Register the IP on your Kite Connect app settings page.
- You can register backup/secondary IPs too.

### What you do NOT need to worry about

- HFT co-location (irrelevant for retail)
- Exchange algo registration (you're under 10 OPS)
- Special licenses (you're not selling strategies)
- India-based IP requirement (any country works)

### Order frequency

Stay under 10 orders/second and you're fine. With a bot that does 5 trades/day, you're at roughly 0.001 orders/second. Not even close.

---

## 9. Quick Reference Cheatsheet

### Setup checklist

```
[ ] Zerodha trading account active
[ ] TOTP 2FA enabled (save the secret key!)
[ ] Developer account at developers.kite.trade
[ ] App created with redirect URL = http://127.0.0.1
[ ] Connect plan subscribed (Rs 500/month)
[ ] api_key and api_secret saved in .env
[ ] Static IP registered (for live trading)
[ ] pykiteconnect installed (pip install kiteconnect)
```

### Daily bot lifecycle

```
06:00 AM — Old access token expires
06:30 AM — Bot logs in, gets new access token
09:15 AM — Market opens (skip this candle for signals)
09:30 AM — Bot starts trading (after opening range collected)
03:00 PM — Stop entering new trades
03:15 PM — Force close all MIS positions
03:30 PM — Market closes
```

### Key API calls

```python
# Auth
kite = KiteConnect(api_key="...")
data = kite.generate_session(request_token, api_secret="...")
kite.set_access_token(data["access_token"])

# Data
kite.ltp("NSE:INFY")                             # live price
kite.quote("NSE:INFY")                            # full quote with depth
kite.historical_data(token, from_d, to_d, "5min") # candles
kite.instruments("NSE")                            # all instruments

# Orders
kite.place_order(variety, symbol, exchange, ...)   # place
kite.modify_order(variety, order_id, ...)          # modify
kite.cancel_order(variety, order_id)               # cancel
kite.orders()                                      # list all today
kite.trades()                                      # list all fills

# Portfolio
kite.positions()                                   # intraday + overnight
kite.holdings()                                    # delivery holdings
kite.margins()                                     # funds and margins

# GTT
kite.place_gtt(...)                                # good-till-triggered
kite.get_gtts()                                    # list GTTs
kite.delete_gtt(gtt_id)                            # cancel GTT

# WebSocket
kws = KiteTicker(api_key, access_token)
kws.on_ticks = callback
kws.connect()
```

### HTTP error codes

| Code | Meaning | What to do |
|------|---------|-----------|
| 200 | Success | All good |
| 400 | Bad request | Check your parameters |
| 403 | Forbidden | Token expired or invalid. Re-login. |
| 429 | Rate limited | Wait 1 second, retry |
| 500 | Server error | Retry with backoff |
| 502/503 | Gateway/service unavailable | Zerodha is having issues. Wait and retry. |

### Exception classes in pykiteconnect

```python
from kiteconnect import exceptions

# exceptions.TokenException      — token expired, need to re-login
# exceptions.PermissionException — insufficient permissions
# exceptions.OrderException      — order placement/modification failed
# exceptions.InputException      — bad input parameters
# exceptions.DataException       — issue fetching data
# exceptions.NetworkException    — connection/timeout issue
# exceptions.GeneralException    — everything else
```

---

## Sources

- [Kite Connect v3 Documentation](https://kite.trade/docs/connect/v3/)
- [pykiteconnect v4 Docs](https://kite.trade/docs/pykiteconnect/v4/)
- [Kite Connect Developer Forum](https://kite.trade/forum/)
- [Zerodha Support — Kite API](https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api)
- [SEBI Algo Trading Circular (Feb 2025)](https://www.sebi.gov.in/legal/circulars/feb-2025/safer-participation-of-retail-investors-in-algorithmic-trading_91614.html)
- [Zerodha Z-Connect — SEBI Algo Rules Explained](https://zerodha.com/z-connect/business-updates/explaining-the-latest-sebi-algo-trading-regulations)
