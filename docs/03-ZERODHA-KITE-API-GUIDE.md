# Zerodha Kite Connect API — Complete Guide

## Overview

Kite Connect is a REST-like HTTP API by Zerodha that lets you:
- Place/modify/cancel orders programmatically
- Get real-time market data via WebSockets
- Access historical candle data (OHLCV)
- Manage portfolio and positions
- Get account margins and funds info

---

## Setup Requirements

### 1. Zerodha Account
- Active Zerodha trading + demat account
- 2FA TOTP enabled (mandatory for API access)
- Minimum funds for trading (no minimum to open, but need margin for trades)

### 2. Kite Connect Developer Account
- Register at: https://developers.kite.trade/
- Create a new "app" to get your API key and secret
- **Cost:** Rs 500/month for data APIs (historical + real-time)
  - Personal app (for your own account only) = FREE for order/portfolio APIs
  - Data APIs (market data, historical data) = Rs 500/month

### 3. Python Setup
```bash
pip install kiteconnect
pip install pandas numpy
pip install pandas-ta   # For technical indicators (alternative to ta-lib)
```

---

## Authentication Flow

Kite Connect uses a 3-step login process (runs once daily):

```python
from kiteconnect import KiteConnect

# Step 1: Initialize with your API key
kite = KiteConnect(api_key="your_api_key")

# Step 2: Get login URL — user must visit this in browser
login_url = kite.login_url()
print(f"Login here: {login_url}")
# After login, Zerodha redirects to your redirect_url with a request_token

# Step 3: Exchange request_token for access_token
data = kite.generate_session(
    request_token="token_from_redirect",
    api_secret="your_api_secret"
)
access_token = data["access_token"]

# Step 4: Set access token for all future requests
kite.set_access_token(access_token)

# Now you can trade!
```

**Important:** The access_token is valid for one trading day only. You need to re-authenticate every morning.

### Auto-Login with TOTP
For automation, you can use `pyotp` to generate TOTP codes:
```python
import pyotp
totp = pyotp.TOTP("your_totp_secret")
otp = totp.now()
```

---

## Core API Methods

### Placing Orders
```python
# Market order — Buy INFY at current price
order_id = kite.place_order(
    variety=kite.VARIETY_REGULAR,
    exchange=kite.EXCHANGE_NSE,
    tradingsymbol="INFY",
    transaction_type=kite.TRANSACTION_TYPE_BUY,
    quantity=1,
    product=kite.PRODUCT_MIS,        # Intraday
    order_type=kite.ORDER_TYPE_MARKET
)

# Limit order — Buy RELIANCE at Rs 2500
order_id = kite.place_order(
    variety=kite.VARIETY_REGULAR,
    exchange=kite.EXCHANGE_NSE,
    tradingsymbol="RELIANCE",
    transaction_type=kite.TRANSACTION_TYPE_BUY,
    quantity=1,
    product=kite.PRODUCT_MIS,
    order_type=kite.ORDER_TYPE_LIMIT,
    price=2500
)

# Stop-Loss order
order_id = kite.place_order(
    variety=kite.VARIETY_REGULAR,
    exchange=kite.EXCHANGE_NSE,
    tradingsymbol="RELIANCE",
    transaction_type=kite.TRANSACTION_TYPE_SELL,
    quantity=1,
    product=kite.PRODUCT_MIS,
    order_type=kite.ORDER_TYPE_SL,
    trigger_price=2450,  # Triggers when price hits 2450
    price=2445           # Sells at 2445 or better
)
```

### Getting Market Data
```python
# Get LTP (Last Traded Price)
ltp = kite.ltp(["NSE:INFY", "NSE:RELIANCE"])

# Get full quote (with depth, OHLC, volume)
quote = kite.quote(["NSE:INFY"])

# Get OHLC only
ohlc = kite.ohlc(["NSE:INFY"])
```

### Historical Data (Candles)
```python
from datetime import datetime, timedelta

# Get 5-minute candles for last 5 days
instrument_token = 408065  # INFY token (get from instruments list)
data = kite.historical_data(
    instrument_token=instrument_token,
    from_date=datetime.now() - timedelta(days=5),
    to_date=datetime.now(),
    interval="5minute"  # Options: minute, 3minute, 5minute, 15minute, 30minute, 60minute, day
)

# Convert to DataFrame
import pandas as pd
df = pd.DataFrame(data)
```

### Positions and Portfolio
```python
# Get current positions
positions = kite.positions()
day_positions = positions["day"]       # Today's positions
net_positions = positions["net"]       # Net positions

# Get holdings (delivery stocks)
holdings = kite.holdings()

# Get account margins
margins = kite.margins()
equity_margin = margins["equity"]
```

### Modify/Cancel Orders
```python
# Modify an order
kite.modify_order(
    variety=kite.VARIETY_REGULAR,
    order_id=order_id,
    price=2510  # New price
)

# Cancel an order
kite.cancel_order(
    variety=kite.VARIETY_REGULAR,
    order_id=order_id
)
```

---

## WebSocket for Real-Time Data

```python
from kiteconnect import KiteTicker

kws = KiteTicker(api_key="your_api_key", access_token="your_access_token")

def on_ticks(ws, ticks):
    """Called when new ticks arrive"""
    for tick in ticks:
        print(f"Token: {tick['instrument_token']}, LTP: {tick['last_price']}")

def on_connect(ws, response):
    """Called on successful connection"""
    # Subscribe to instruments
    ws.subscribe([408065, 738561])  # INFY, RELIANCE tokens
    ws.set_mode(ws.MODE_FULL, [408065, 738561])  # Full data mode

def on_close(ws, code, reason):
    ws.stop()

kws.on_ticks = on_ticks
kws.on_connect = on_connect
kws.on_close = on_close

kws.connect()  # Blocking call — runs forever
```

### WebSocket Data Modes
| Mode | Data Included | Use Case |
|------|--------------|----------|
| `MODE_LTP` | Last price only | Simple price monitoring |
| `MODE_QUOTE` | LTP + OHLC + Volume | Strategy calculations |
| `MODE_FULL` | Everything + market depth | Full analysis |

---

## Instrument Tokens

Every tradeable instrument has a unique numeric token. Download the full list:
```python
instruments = kite.instruments()  # All exchanges
nse_instruments = kite.instruments("NSE")  # NSE only

# Find a specific stock
infy = [i for i in nse_instruments if i["tradingsymbol"] == "INFY"][0]
print(infy["instrument_token"])  # Use this token for subscriptions
```

---

## Rate Limits

| API | Limit |
|-----|-------|
| Orders per second | 10 |
| API requests per second | 10 |
| Historical data requests/second | 3 |
| WebSocket subscriptions | 3,000 instruments max |
| Order modifications per order | 25 |
| MIS orders per day | 2,000 |
| Cover Orders per day | 2,000 |

**Important:** Exceeding rate limits will get your requests temporarily blocked.

---

## SEBI Compliance (April 2026)

As of April 1, 2026, new SEBI rules apply:
1. **Algo-ID Required:** Every algorithmic order must carry an exchange-assigned identifier
2. **Static IP:** API access must come from whitelisted static IP addresses
3. **Broker Responsibility:** Zerodha is responsible for all algos running through their platform
4. **Retail Exemption:** Individual traders using broker APIs for personal use can continue as long as order frequency is below exchange-prescribed thresholds (Zerodha's limit: 10 orders/second)

**What this means for you:**
- For personal use with Zerodha APIs, you're fine as long as you stay under 10 orders/second
- If you plan to sell or distribute your bot, you'll need to register as an algo provider through a broker
- Keep your trading frequency reasonable
