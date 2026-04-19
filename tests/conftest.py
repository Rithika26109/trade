"""
Shared pytest fixtures for the trading bot test suite.
"""

import sys
from pathlib import Path

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import pytest

from config import settings


# ── Force paper mode for all tests ──
settings.TRADING_MODE = "paper"


@pytest.fixture
def sample_ohlcv():
    """
    50-row OHLCV DataFrame with realistic trending-up data plus noise.
    Dates span 50 intraday 5-minute candles starting at 09:15 IST.
    """
    np.random.seed(42)
    n = 50
    base_price = 2000.0
    # Upward drift with noise
    returns = np.random.normal(0.001, 0.005, n)
    cum_returns = np.cumprod(1 + returns)
    close = base_price * cum_returns

    # Realistic OHLC from close
    high = close * (1 + np.abs(np.random.normal(0, 0.003, n)))
    low = close * (1 - np.abs(np.random.normal(0, 0.003, n)))
    open_ = close * (1 + np.random.normal(0, 0.002, n))
    volume = np.random.randint(100_000, 2_000_000, n).astype(float)

    dates = pd.date_range(
        start="2026-04-17 09:15:00",
        periods=n,
        freq="5min",
        tz=settings.IST,
    )

    df = pd.DataFrame({
        "date": dates,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })
    # Ensure high >= max(open, close) and low <= min(open, close) per candle
    df["high"] = df[["open", "high", "close"]].max(axis=1)
    df["low"] = df[["open", "low", "close"]].min(axis=1)
    return df


@pytest.fixture
def sample_ohlcv_with_indicators(sample_ohlcv):
    """sample_ohlcv with all technical indicators applied."""
    from src.indicators.indicators import add_all_indicators
    df = sample_ohlcv.copy()
    df = add_all_indicators(df)
    return df


@pytest.fixture
def mock_order_manager():
    """OrderManager in paper mode with no KiteConnect dependency."""
    from src.execution.order_manager import OrderManager
    om = OrderManager(kite=None)
    om.is_paper = True
    return om


@pytest.fixture
def mock_risk_manager(mock_order_manager):
    """RiskManager backed by the paper OrderManager."""
    from src.risk.risk_manager import RiskManager
    rm = RiskManager(order_manager=mock_order_manager, db=None)
    return rm


@pytest.fixture
def trade_db(tmp_path):
    """TradeDB pointing at a temporary SQLite database."""
    from src.utils.db import TradeDB
    db_path = tmp_path / "test_trades.db"
    return TradeDB(db_path=db_path)
