"""
Market Data Module
──────────────────
Fetch historical OHLCV candles, live quotes, and instrument info from Zerodha.
"""

from datetime import datetime, timedelta

import pandas as pd
from kiteconnect import KiteConnect

from config import settings
from config.settings import now_ist
from src.utils.logger import logger
from src.utils.rate_limiter import RateLimiter


def resample_to_htf(df: pd.DataFrame, interval: str = "15min") -> pd.DataFrame:
    """
    Resample a lower-timeframe DataFrame to a higher timeframe.
    E.g., 5-minute candles → 15-minute candles.
    """
    if df.empty or "date" not in df.columns:
        return pd.DataFrame()

    df_copy = df.set_index("date")
    resampled = df_copy.resample(interval).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna(subset=["open"])
    resampled = resampled.reset_index()
    return resampled


class MarketData:
    """Handles all market data fetching from Zerodha Kite."""

    def __init__(self, kite: KiteConnect):
        self.kite = kite
        self._instruments_cache: dict[str, dict] = {}
        self._hist_rate_limiter = RateLimiter(max_calls=3, period=1.0)  # 3 req/s for historical
        self._api_rate_limiter = RateLimiter(max_calls=10, period=1.0)  # 10 req/s general

    def load_instruments(self, exchange: str = "NSE"):
        """Load and cache instrument list for quick symbol→token lookup."""
        instruments = self.kite.instruments(exchange)
        for inst in instruments:
            key = f"{exchange}:{inst['tradingsymbol']}"
            self._instruments_cache[key] = inst
        logger.info(f"Loaded {len(instruments)} instruments from {exchange}")

    def get_instrument_token(self, symbol: str, exchange: str = "NSE") -> int:
        """Get numeric instrument token for a symbol."""
        key = f"{exchange}:{symbol}"
        if key not in self._instruments_cache:
            self.load_instruments(exchange)
        inst = self._instruments_cache.get(key)
        if inst is None:
            raise ValueError(f"Instrument not found: {key}")
        return inst["instrument_token"]

    def get_ltp(self, symbols: list[str], exchange: str = "NSE") -> dict[str, float]:
        """
        Get Last Traded Price for multiple symbols.
        Returns: {"RELIANCE": 2450.50, "INFY": 1520.30, ...}
        """
        self._api_rate_limiter.wait()
        keys = [f"{exchange}:{s}" for s in symbols]
        data = self.kite.ltp(keys)
        return {
            s: data[f"{exchange}:{s}"]["last_price"]
            for s in symbols
            if f"{exchange}:{s}" in data
        }

    def get_quote(self, symbols: list[str], exchange: str = "NSE") -> dict:
        """Get full quote (OHLC, volume, depth) for symbols."""
        keys = [f"{exchange}:{s}" for s in symbols]
        return self.kite.quote(keys)

    def get_historical_data(
        self,
        symbol: str,
        interval: str = "5minute",
        days: int = 5,
        exchange: str = "NSE",
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV candle data.

        Args:
            symbol: Stock symbol (e.g., "RELIANCE")
            interval: Candle interval — minute, 3minute, 5minute, 15minute,
                      30minute, 60minute, day
            days: Number of days of data to fetch
            exchange: Exchange (NSE/BSE)

        Returns:
            DataFrame with columns: date, open, high, low, close, volume
        """
        token = self.get_instrument_token(symbol, exchange)
        to_date = now_ist()
        from_date = to_date - timedelta(days=days)

        # Kite API limits per request:
        # minute: 60 days, 5minute: 100 days, 15minute+: 200 days, day: 2000 days
        max_days = {"minute": 60, "3minute": 100, "5minute": 100,
                    "15minute": 200, "30minute": 200, "60minute": 400, "day": 2000}
        limit = max_days.get(interval, 100)

        all_data = []
        current_from = from_date

        while current_from < to_date:
            current_to = min(current_from + timedelta(days=limit), to_date)
            try:
                self._hist_rate_limiter.wait()
                data = self.kite.historical_data(
                    instrument_token=token,
                    from_date=current_from,
                    to_date=current_to,
                    interval=interval,
                )
                all_data.extend(data)
            except Exception as e:
                logger.error(f"Error fetching historical data for {symbol}: {e}")
                break
            current_from = current_to + timedelta(days=1)

        if not all_data:
            logger.warning(f"No historical data for {symbol}")
            return pd.DataFrame()

        df = pd.DataFrame(all_data)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        df = df.drop_duplicates(subset=["date"])
        logger.info(f"Fetched {len(df)} candles for {symbol} ({interval}, {days}d)")
        return df

    def get_todays_candles(
        self, symbol: str, interval: str = "5minute", exchange: str = "NSE"
    ) -> pd.DataFrame:
        """Fetch today's intraday candle data."""
        return self.get_historical_data(symbol, interval=interval, days=1, exchange=exchange)

    def get_todays_multi_tf(
        self, symbol: str, exchange: str = "NSE"
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Fetch today's candles and return both 5-min and 15-min DataFrames.
        Resamples 5-min to 15-min to avoid extra API calls.

        Returns:
            (df_5min, df_15min) tuple of DataFrames
        """
        df_5min = self.get_todays_candles(symbol, interval="5minute", exchange=exchange)
        if df_5min.empty:
            return df_5min, pd.DataFrame()
        df_15min = resample_to_htf(df_5min, interval="15min")
        return df_5min, df_15min

    def get_opening_range(
        self, symbol: str, minutes: int = 15, exchange: str = "NSE"
    ) -> dict | None:
        """
        Get the opening range (high/low) for the first N minutes of today.
        Used by the ORB strategy.

        Returns:
            {"high": float, "low": float, "open": float} or None
        """
        df = self.get_todays_candles(symbol, interval="minute", exchange=exchange)
        if df.empty:
            return None

        market_open = df["date"].iloc[0].replace(hour=9, minute=15, second=0)
        range_end = market_open + timedelta(minutes=minutes)

        range_df = df[(df["date"] >= market_open) & (df["date"] < range_end)]
        if range_df.empty:
            return None

        return {
            "high": float(range_df["high"].max()),
            "low": float(range_df["low"].min()),
            "open": float(range_df["open"].iloc[0]),
        }
