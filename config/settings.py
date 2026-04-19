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

# ── Trading Mode ──
TRADING_MODE = os.getenv("TRADING_MODE", "paper")  # "paper" or "live"

# ── Strategy Settings ──
STRATEGY = "ORB"  # Options: "ORB", "RSI_EMA", "VWAP_SUPERTREND"
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
ATR_MULTIPLIER = 1.5  # For stop-loss calculation
SUPERTREND_PERIOD = 10
SUPERTREND_MULTIPLIER = 3.0
VWAP_ENABLED = True
SUPERTREND_CONFIRMATION_CANDLES = 2  # Candles to confirm Supertrend flip

# ── RSI Strategy Ranges ──
RSI_BUY_MIN = 30  # Buy when RSI recovering from oversold
RSI_BUY_MAX = 55
RSI_SELL_MIN = 45  # Sell when RSI losing momentum
RSI_SELL_MAX = 70

# ── ORB Strategy ──
ORB_VOLUME_MULTIPLIER = 1.5  # Breakout volume must be >= 1.5x average

# ── Risk Management ──
INITIAL_CAPITAL = 100000  # Starting capital in Rs (used for paper trading)
RISK_PER_TRADE_PCT = 1.0  # Max 1% of capital risked per trade
MAX_DAILY_LOSS_PCT = 3.0  # Stop trading after 3% daily loss
MAX_TRADES_PER_DAY = 5  # Maximum number of trades in a day
MAX_OPEN_POSITIONS = 2  # Maximum concurrent open positions
MIN_RISK_REWARD_RATIO = 2.0  # Minimum 1:2 risk/reward
MAX_POSITION_PCT = 30.0  # Max 30% of capital in a single position
MAX_CONSECUTIVE_LOSSES = 3  # Pause after 3 consecutive losses
PAUSE_AFTER_LOSSES_MINUTES = 30  # Pause duration after consecutive losses

# ── Stop-Loss Settings ──
STOP_LOSS_TYPE = "ATR"  # Options: "FIXED", "ATR", "TRAILING"
FIXED_STOP_LOSS_PCT = 1.0  # 1% fixed stop-loss
TRAILING_STOP_PCT = 0.5  # 0.5% trailing stop

# ── Intraday Drawdown ──
MAX_INTRADAY_DRAWDOWN_PCT = 2.0  # Stop trading if drawdown from peak > 2%

# ── Market Regime Detection ──
ENABLE_REGIME_DETECTION = True
ADX_STRONG_TREND = 40  # ADX above this = strong trend
ADX_TREND = 25  # ADX above this = trend
ADX_RANGING = 20  # ADX below this = ranging/choppy

# ── Confluence Scoring ──
ENABLE_CONFLUENCE_SCORING = True
CONFLUENCE_THRESHOLD = 55  # Minimum score (0-100) to take a trade

# ── Volatility (VIX) Scaling ──
VOLATILITY_SCALING_ENABLED = True
VIX_LOW = 12.0  # Below this: low volatility → 1.2x size
VIX_HIGH = 20.0  # Above this: high volatility → 0.6x size
VIX_EXTREME = 25.0  # Above this: extreme → 0.3x size

# ── Performance-Adaptive Sizing (Kelly Criterion) ──
KELLY_ENABLED = True
KELLY_MIN_TRADES = 20  # Minimum trades before Kelly activates

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

# ── Trading Hours (IST) ──
MARKET_OPEN = "09:15"
TRADING_START = "09:30"  # Start after opening range collected
STOP_NEW_TRADES = "15:00"  # No new trades after 3:00 PM
FORCE_SQUARE_OFF = "15:15"  # Force close all positions by 3:15 PM
PRE_MARKET_LOGIN = "09:00"  # Login time before market opens

# ── Watchlist ──
# High-liquidity NIFTY 50 stocks ideal for intraday
WATCHLIST = [
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
]

# ── Stock Selection Filters ──
MIN_VOLUME = 1_000_000  # Minimum average daily volume
MIN_PRICE = 100  # Minimum stock price (Rs)
MAX_PRICE = 5000  # Maximum stock price (Rs)

# ── Notifications ──
TELEGRAM_ENABLED = False
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

    if errors:
        raise ValueError("Configuration errors:\n  - " + "\n  - ".join(errors))
