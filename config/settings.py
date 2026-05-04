"""
Trading Bot Configuration
─────────────────────────
All tunable parameters in one place.
Change strategy, risk limits, watchlist, and timing here.
"""

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

# ── Load .env ──
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / "config" / ".env")

# ── Zerodha Credentials ──
KITE_API_KEY = os.getenv("KITE_API_KEY", "")
KITE_API_SECRET = os.getenv("KITE_API_SECRET", "")
KITE_USER_ID = os.getenv("KITE_USER_ID", "")
KITE_TOTP_SECRET = os.getenv("KITE_TOTP_SECRET", "")
KITE_PASSWORD = os.getenv("KITE_PASSWORD", "")

# ── Trading Mode ──
TRADING_MODE = os.getenv("TRADING_MODE", "paper")  # "paper" or "live"

# ── Strategy Settings ──
STRATEGY = "MULTI"  # Options: "ORB", "RSI_EMA", "VWAP_SUPERTREND", "MULTI"
TIMEFRAME = "5minute"  # Candle interval for indicators
ORB_PERIOD_MINUTES = 15  # Opening range: first 15 minutes (9:15 - 9:30)

# ── Technical Indicator Parameters ──
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
EMA_FAST = 9
EMA_SLOW = 21
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BOLLINGER_PERIOD = 20
BOLLINGER_STD = 2.0
ATR_PERIOD = 14
ATR_MULTIPLIER = 2.0  # For stop-loss calculation
SUPERTREND_PERIOD = 10
SUPERTREND_MULTIPLIER = 3.0
VWAP_ENABLED = True
SUPERTREND_CONFIRMATION_CANDLES = 2  # Candles to confirm Supertrend flip (1 was too noisy in ranging)

# ── RSI Strategy Ranges ──
RSI_BUY_MIN = 30  # Buy when RSI recovering from oversold
RSI_BUY_MAX = 55
RSI_SELL_MIN = 45  # Sell when RSI losing momentum
RSI_SELL_MAX = 70

# ── ORB Strategy ──
ORB_VOLUME_MULTIPLIER = 1.5  # Breakout volume must be >= 1.5x average

# ── Catch-Up Scan ──
# When the bot starts mid-session, look back this many 5-min candles
# (2 candles = 10 minutes) to detect recent crossovers/breakouts/flips.
# Was 6 (30 min) — chasing stale signals destroyed R:R.
CATCH_UP_CANDLES = 4

# ── Risk Management ──
INITIAL_CAPITAL = 100000  # Starting capital in Rs (used for paper trading)
RISK_PER_TRADE_PCT = 3.0  # Max 3% risk per trade (paper testing; tighten to 0.5% for live)
MAX_DAILY_LOSS_PCT = 3.0  # Stop trading after 3% daily loss (paper testing; tighten to 2% for live)
MAX_TRADES_PER_DAY = 7  # Max trades per day (paper testing; tighten to 4-5 for live)
MAX_OPEN_POSITIONS = 4  # Max concurrent positions (paper testing; tighten to 2-3 for live)
MIN_RISK_REWARD_RATIO = 1.5  # Minimum 1:1.5 risk/reward (net of costs)
TARGET_RISK_REWARD_RATIO = 2.0  # Target R:R for setting profit targets (must be > MIN to survive cost deduction)
MAX_POSITION_PCT = 50.0  # Max 50% of capital in a single position
MAX_CONSECUTIVE_LOSSES = 3  # Pause after 3 consecutive losses
PAUSE_AFTER_LOSSES_MINUTES = 10  # Pause duration after consecutive losses

# ── Stop-Loss Settings ──
STOP_LOSS_TYPE = "TRAILING"  # Options: "FIXED", "ATR", "TRAILING"
FIXED_STOP_LOSS_PCT = 1.0  # 1% fixed stop-loss
TRAILING_STOP_PCT = 0.5  # 0.5% trailing stop

# ── Intraday Drawdown ──
MAX_INTRADAY_DRAWDOWN_PCT = 2.0  # Stop trading if drawdown from peak > 2%

# ── Market Regime Detection ──
ENABLE_REGIME_DETECTION = True
ADX_STRONG_TREND = 40  # ADX above this = strong trend
ADX_TREND = 25  # ADX above this = trend
ADX_RANGING = 15  # ADX below this = ranging/choppy

# ── Confluence Scoring ──
ENABLE_CONFLUENCE_SCORING = True
CONFLUENCE_THRESHOLD = 45  # Minimum score (0-100) to take a trade (25 let weak setups through)

# ── Volatility (VIX) Scaling ──
VOLATILITY_SCALING_ENABLED = True
VIX_LOW = 12.0  # Below this: low volatility → 1.2x size
VIX_HIGH = 20.0  # Above this: high volatility → 0.6x size
VIX_EXTREME = 25.0  # Above this: extreme → 0.3x size

# ── Performance-Adaptive Sizing (Kelly Criterion) ──
KELLY_ENABLED = True
KELLY_MIN_TRADES = 100  # Minimum trades before Kelly activates (20 was noise amplification)

# ── Equity Curve Trading ──
EQUITY_CURVE_TRADING_ENABLED = True
EQUITY_CURVE_LOOKBACK_DAYS = 10
EQUITY_CURVE_DRAWDOWN_SCALE = 0.5  # 50% size when losing streak
EQUITY_CURVE_SEVERE_SCALE = 0.25  # 25% size when severely losing
EQUITY_CURVE_SEVERE_THRESHOLD = 3  # Consecutive losing days for severe

# ── Sector Limits ──
MAX_POSITIONS_PER_SECTOR = 1  # Max 1 position in same sector

# ── Partial Profit-Taking ──
ENABLE_PARTIAL_EXITS = True
PARTIAL_EXIT_1R_PCT = 40  # Close 40% at 1R
PARTIAL_EXIT_2R_PCT = 30  # Close 30% at 2R
PARTIAL_EXIT_3R_PCT = 30  # Close remaining 30% at 3R

# ── Time-of-Day Scaling ──
ENABLE_TIME_SCALING = True

# ── Paper Trading ──
PAPER_SLIPPAGE_PCT = 0.05  # 0.05% slippage simulation for paper trades

# ── Backtest Slippage ──
BACKTEST_SLIPPAGE_PCT = 0.05  # 0.05% slippage per trade leg in backtests

# ── Paper Trading: Realistic Simulation ──
# All toggles default to False — existing paper behavior is unchanged unless opted in.

# Order rejection simulation (margin, circuit, random exchange glitches)
PAPER_SIMULATE_REJECTIONS = True
PAPER_RANDOM_REJECTION_PCT = 1.5        # % chance of random exchange rejection
PAPER_MARGIN_CHECK = True               # reject if notional > available capital

# Partial fill simulation
PAPER_SIMULATE_PARTIAL_FILLS = True
PAPER_PARTIAL_FILL_PROB = 0.15          # 15% of orders get partial fills
PAPER_PARTIAL_FILL_MIN_PCT = 60         # minimum fill %; below this → reject
PAPER_PARTIAL_FILL_MAX_PCT = 90         # maximum partial fill %
PAPER_PARTIAL_FILL_VOLUME_FACTOR = True # worse fills for large orders vs avg volume

# Dynamic slippage (replaces fixed PAPER_SLIPPAGE_PCT when enabled)
PAPER_DYNAMIC_SLIPPAGE = True
PAPER_BASE_SLIPPAGE_PCT = 0.03          # base slippage for liquid NIFTY 50 stocks
PAPER_SLIPPAGE_VOLATILITY_MULT = True   # scale by ATR%
PAPER_SLIPPAGE_TIME_MULT = True         # wider spreads at open/close
PAPER_SLIPPAGE_SIZE_MULT = True         # larger orders get more slippage
PAPER_SLIPPAGE_MAX_PCT = 0.50           # hard cap on slippage %

# ── Mean-Reversion Strategy ──
MEAN_REV_ADX_MAX = 20                   # Only activate below this ADX (ranging market)
MEAN_REV_RSI_OVERSOLD = 35              # Buy below this RSI (tighter to avoid noise entries)
MEAN_REV_RSI_OVERBOUGHT = 65            # Sell above this RSI (tighter to avoid noise entries)
MEAN_REV_MIN_BB_WIDTH_PCT = 0.5         # Skip if BB bandwidth < this % (squeeze)
MEAN_REV_MAX_VOL_Z = 2.0               # Skip if volume z-score > this (breakout)

# ── Pairs Trading (Simplified v1) ──
ENABLE_PAIRS_TRADING = False             # Off by default; needs market_data wiring
PAIRS_SYMBOLS = [
    ("HDFCBANK", "ICICIBANK"),
    ("TCS", "INFY"),
    ("SBIN", "KOTAKBANK"),
]
PAIRS_LOOKBACK = 50                      # Candles for spread mean/std
PAIRS_ENTRY_Z = 2.0                      # Z-score threshold for entry
PAIRS_MIN_HISTORY = 20                   # Minimum aligned candles required

# ── SEBI Algo-ID (April 2026 compliance) ──
# A short tag attached to every live order for broker/exchange audit trail.
# Kite's `tag` field is max 20 chars, alphanumeric + underscore.
ALGO_ID = os.getenv("ALGO_ID", "ALGO01")

# ── Phase 4: SEBI compliance & ops ──
# Static IP pin: the egress IP registered with your broker. If empty,
# the startup check is skipped. In live mode a mismatch halts the bot.
STATIC_IP_EXPECTED = os.getenv("STATIC_IP_EXPECTED", "")
# Personal-use algos must stay below 10 orders/sec. Leave headroom.
ORDER_RATE_LIMIT_PER_SEC = int(os.getenv("ORDER_RATE_LIMIT_PER_SEC", "8"))
# Append-only JSONL audit trail. Empty = default logs/audit/audit.jsonl.
AUDIT_LOG_PATH = os.getenv("AUDIT_LOG_PATH", "")
# Kill-switch sentinel file. Empty = <BASE_DIR>/.kill_switch.
KILL_SWITCH_PATH = os.getenv("KILL_SWITCH_PATH", "")

# ── Broker Order Safety ──
# Reject signals whose stop-loss is beyond today's circuit band (un-fillable).
ENABLE_CIRCUIT_LIMIT_CHECK = True
# Reconcile in-memory position state against kite.positions() on startup
# and every N trading cycles. 0 disables periodic reconciliation.
BROKER_RECONCILE_CYCLES = 6  # ~every 30 min on 5-min timeframe

# ── Retry / Backoff for broker calls ──
BROKER_RETRY_ATTEMPTS = 3
BROKER_RETRY_INITIAL_DELAY = 0.5  # seconds

# ── Trading Hours (IST) ──
MARKET_OPEN = "09:15"
TRADING_START = "09:30"  # Start after opening range collected
STOP_NEW_TRADES = "15:00"  # No new trades after 3:00 PM
FORCE_SQUARE_OFF = "15:15"  # Force close all positions by 3:15 PM
PRE_MARKET_LOGIN = "09:00"  # Login time before market opens

# ── Watchlist ──
# High-liquidity NIFTY 50 stocks ideal for intraday
WATCHLIST = [
    # Large-cap (NIFTY 50)
    "RELIANCE",
    "TCS",
    "HDFCBANK",
    "INFY",
    "ICICIBANK",
    "SBIN",
    "BHARTIARTL",
    "ITC",
    "KOTAKBANK",
    "LT",
    # Mid-cap (F&O eligible, high intraday volume)
    "TATAMOTORS",
    "TATAPOWER",
    "PNB",
    "ADANIENT",
    "BANKBARODA",
    "INDUSINDBK",
    "DLF",
    "BPCL",
    "SAIL",
    "ZOMATO",
]

# ── Stock Selection Filters ──
MIN_VOLUME = 1_000_000  # Minimum average daily volume
MIN_PRICE = 100  # Minimum stock price (Rs)
MAX_PRICE = 5000  # Maximum stock price (Rs)

# ── Scanner (Phase 3A) ──
SCANNER_TOP_N = 5                 # Only trade the top-N ranked candidates
SCANNER_VOLUME_WEIGHT = 0.20
SCANNER_VOLATILITY_WEIGHT = 0.20
SCANNER_MOMENTUM_WEIGHT = 0.25
SCANNER_RS_WEIGHT = 0.20
SCANNER_SECTOR_WEIGHT = 0.15
SCANNER_DROP_CIRCUIT_FROZEN = True     # skip stocks frozen at circuit today
SCANNER_MIN_TURNOVER_CR = 5.0          # Rs crore/day minimum turnover (price*volume)
SCANNER_MAX_SPREAD_BPS = 5.0           # max (ask-bid)/mid in basis points; 0 disables

# ── Phase 3C: Volatility Regime ──
ENABLE_VOLATILITY_REGIME = True
VOL_REGIME_LOOKBACK_DAYS = 20          # ATR% percentile window
VOL_REGIME_LOW_PCT = 33                # <=33rd pctile = LOW
VOL_REGIME_HIGH_PCT = 67               # >=67th pctile = HIGH ; else NORMAL

# ── Phase 3C: Regime performance tracker ──
REGIME_TRACKER_ENABLED = True
REGIME_TRACKER_MIN_TRADES = 10         # min trades before weighting kicks in
REGIME_TRACKER_WINDOW = 100            # rolling trade window per cell
REGIME_BLACKLIST_WR = 0.40             # below this WR → blacklist cell
REGIME_BLACKLIST_MIN_TRADES = 30       # only blacklist after this many trades

# ── Phase 3E: Risk upgrades ──
CORRELATION_LIMIT_ENABLED = True
CORRELATION_LIMIT_THRESHOLD = 0.7      # avg corr with open positions
CORRELATION_LOOKBACK_DAYS = 20
KELLY_USE_DB_HISTORY = True            # include DB-closed trades in Kelly
COSTS_ROUND_TRIP_BPS = 15.0             # ~0.15% round-trip (brokerage+STT+GST+stamps+slippage)
FAT_FINGER_MAX_NOTIONAL_PCT = 40.0     # absolute hard cap notional % of capital
PERSIST_INTRADAY_HWM = True            # persist HWM + daily_loss across restart

# ── Phase 3D: ML filter (opt-in, not implemented yet) ──
USE_ML_FILTER = False

# ── Notifications ──
TELEGRAM_ENABLED = True
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Paths ──
LOG_DIR = BASE_DIR / "logs"
TRADE_LOG_DIR = BASE_DIR / "logs" / "trades"
DATA_DIR = BASE_DIR / "data"
HISTORICAL_DATA_DIR = BASE_DIR / "data" / "historical"
DB_PATH = BASE_DIR / "data" / "trades.db"

# ── Logging ──
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR

# ── Timezone ──
IST = ZoneInfo("Asia/Kolkata")

# ── Market Holidays 2026 (NSE) ──
# Update this list annually from NSE website
MARKET_HOLIDAYS = [
    "2026-01-26",  # Republic Day
    "2026-03-10",  # Maha Shivaratri
    "2026-03-17",  # Holi
    "2026-03-30",  # Id-Ul-Fitr (Eid)
    "2026-04-02",  # Ram Navami
    "2026-04-03",  # Mahavir Jayanti
    "2026-04-14",  # Dr. Ambedkar Jayanti
    "2026-05-01",  # Maharashtra Day
    "2026-06-05",  # Id-Ul-Zuha (Bakri Eid)
    "2026-07-06",  # Muharram
    "2026-08-15",  # Independence Day
    "2026-08-19",  # Janmashtami
    "2026-09-04",  # Milad-Un-Nabi
    "2026-10-02",  # Mahatma Gandhi Jayanti
    "2026-10-20",  # Dussehra
    "2026-10-21",  # Dussehra (next day)
    "2026-11-09",  # Diwali (Laxmi Puja)
    "2026-11-10",  # Diwali (Balipratipada)
    "2026-11-30",  # Guru Nanak Jayanti
    "2026-12-25",  # Christmas
]


def now_ist() -> datetime:
    """Get current time in IST. Use this everywhere instead of datetime.now()."""
    return datetime.now(IST)


def is_market_day() -> bool:
    """Check if today is a trading day (not weekend or holiday)."""
    today = now_ist().date()
    if today.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    if str(today) in MARKET_HOLIDAYS:
        return False
    return True


def validate_config():
    """Validate critical configuration on startup. Raises ValueError on issues."""
    import re as _re

    errors = []

    # Check trading mode
    if TRADING_MODE not in ("paper", "live"):
        errors.append(f"TRADING_MODE must be 'paper' or 'live', got '{TRADING_MODE}'")

    # Check API keys (warn for paper, error for live)
    if TRADING_MODE == "live":
        if not KITE_API_KEY:
            errors.append("KITE_API_KEY is required for live trading")
        if not KITE_API_SECRET:
            errors.append("KITE_API_SECRET is required for live trading")
        if not KITE_USER_ID:
            errors.append("KITE_USER_ID is required for live trading")

    # Check risk parameters are sane
    if not (0.1 <= RISK_PER_TRADE_PCT <= 5.0):
        errors.append(f"RISK_PER_TRADE_PCT should be 0.1-5.0, got {RISK_PER_TRADE_PCT}")
    if not (1.0 <= MAX_DAILY_LOSS_PCT <= 10.0):
        errors.append(f"MAX_DAILY_LOSS_PCT should be 1.0-10.0, got {MAX_DAILY_LOSS_PCT}")
    if INITIAL_CAPITAL <= 0:
        errors.append(f"INITIAL_CAPITAL must be positive, got {INITIAL_CAPITAL}")

    # Check time ordering
    times = [MARKET_OPEN, TRADING_START, STOP_NEW_TRADES, FORCE_SQUARE_OFF]
    for i in range(len(times) - 1):
        if times[i] >= times[i + 1]:
            errors.append(f"Time ordering invalid: {times[i]} should be before {times[i+1]}")

    # Validate watchlist symbols — defence in depth; symbols flow into API
    # calls, log formatting, and file paths in some tooling.
    _sym_re = _re.compile(r"^[A-Z0-9&\-]{1,20}$")
    for sym in WATCHLIST:
        if not isinstance(sym, str) or not _sym_re.match(sym):
            errors.append(
                f"WATCHLIST entry {sym!r} invalid. Must be 1-20 chars of "
                "A-Z, 0-9, '&' or '-' (NSE tradingsymbol format)."
            )

    if errors:
        raise ValueError("Configuration errors:\n  - " + "\n  - ".join(errors))
