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
        # Cache for multi-day HTF frames keyed by (symbol, interval) → (date, df).
        # Refresh once per calendar day to avoid re-fetching on every cycle.
        self._htf_cache: dict[tuple[str, str], tuple[object, pd.DataFrame]] = {}

    def load_instruments(self, exchange: str = "NSE"):
        """Load and cache instrument list for quick symbol→token lookup.

        The enctoken auth method doesn't support the /instruments endpoint,
        so we fetch the publicly available CSV from api.kite.trade instead.
        Falls back to the kite API for standard auth setups.
        """
        import csv
        import io
        import requests as _requests

        url = f"https://api.kite.trade/instruments/{exchange}"
        try:
            resp = _requests.get(url, timeout=30)
            resp.raise_for_status()
            reader = csv.DictReader(io.StringIO(resp.text))
            count = 0
            for row in reader:
                key = f"{exchange}:{row['tradingsymbol']}"
                row["instrument_token"] = int(row["instrument_token"])
                row["last_price"] = float(row["last_price"] or 0)
                row["strike"] = float(row["strike"] or 0)
                row["tick_size"] = float(row["tick_size"] or 0)
                row["lot_size"] = int(row["lot_size"] or 0)
                self._instruments_cache[key] = row
                count += 1
            logger.info(f"Loaded {count} instruments from {exchange} (public CSV)")
        except Exception as e:
            logger.warning(f"Public CSV fetch failed ({e}), trying kite API...")
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

        Tries kite.ltp() first; falls back to the latest minute candle
        close when the quote endpoint is unavailable (enctoken auth).
        """
        self._api_rate_limiter.wait()
        keys = [f"{exchange}:{s}" for s in symbols]
        try:
            data = self.kite.ltp(keys)
            return {
                s: data[f"{exchange}:{s}"]["last_price"]
                for s in symbols
                if f"{exchange}:{s}" in data
            }
        except Exception:
            # Fallback: latest minute candle close
            result = {}
            today = now_ist().strftime("%Y-%m-%d")
            for s in symbols:
                try:
                    token = self.get_instrument_token(s, exchange)
                    self._hist_rate_limiter.wait()
                    candles = self.kite.historical_data(token, today, today, "minute")
                    if candles:
                        result[s] = candles[-1]["close"]
                except Exception as e:
                    logger.debug(f"LTP fallback failed for {s}: {e}")
            return result

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
        Fetch today's 5-min candles and return (5min, 15min) frames.

        Unlike a pure resample of today's data, the 15-min frame is built
        from ~5 days of history so EMA/ADX/Supertrend on the HTF frame have
        enough warm-up to match backtest behaviour (where indicators were
        computed over the full series before slicing).
        """
        df_5min = self.get_todays_candles(symbol, interval="5minute", exchange=exchange)
        df_htf = self.get_htf_data(symbol, interval="15minute", days=5, exchange=exchange)
        if df_5min.empty:
            return df_5min, df_htf
        return df_5min, df_htf

    def get_htf_data(
        self,
        symbol: str,
        interval: str = "15minute",
        days: int = 5,
        exchange: str = "NSE",
    ) -> pd.DataFrame:
        """
        Fetch higher-timeframe bars with enough history for indicator warm-up.
        Cached per calendar day — subsequent calls within the same day reuse
        the fetched frame, so this is safe to call every trading cycle.
        """
        cache_key = (f"{exchange}:{symbol}", interval)
        today = now_ist().date()
        cached = self._htf_cache.get(cache_key)
        if cached and cached[0] == today and not cached[1].empty:
            return cached[1]

        df = self.get_historical_data(symbol, interval=interval, days=days, exchange=exchange)
        if not df.empty:
            self._htf_cache[cache_key] = (today, df)
        return df

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

    def get_prev_close(self, symbol: str, exchange: str = "NSE") -> float | None:
        """
        Fetch the previous trading day's close. Uses `kite.quote()` which
        returns `ohlc.close` = prev close for intraday contexts.
        Falls back to daily historical if quote is unavailable.
        """
        try:
            quote = self.get_quote([symbol], exchange=exchange)
            key = f"{exchange}:{symbol}"
            if key in quote:
                ohlc = quote[key].get("ohlc", {})
                prev_close = ohlc.get("close")
                if prev_close and prev_close > 0:
                    return float(prev_close)
        except Exception as e:
            logger.debug(f"get_prev_close quote fallback for {symbol}: {e}")

        # Fallback: last daily candle
        try:
            df = self.get_historical_data(symbol, interval="day", days=5, exchange=exchange)
            if df.empty:
                return None
            today = now_ist().date()
            prior = df[df["date"].dt.date < today]
            if prior.empty:
                return None
            return float(prior["close"].iloc[-1])
        except Exception as e:
            logger.warning(f"get_prev_close failed for {symbol}: {e}")
            return None

    def get_circuit_limits(self, symbol: str, exchange: str = "NSE") -> dict | None:
        """
        Return today's lower/upper circuit band for a symbol from kite.quote().
        Signals whose stop-loss falls outside the band are un-fillable and
        must be rejected by risk management.

        Returns:
            {"lower": float, "upper": float} or None if unavailable.
        """
        try:
            quote = self.get_quote([symbol], exchange=exchange)
            key = f"{exchange}:{symbol}"
            if key not in quote:
                return None
            q = quote[key]
            lower = q.get("lower_circuit_limit")
            upper = q.get("upper_circuit_limit")
            if lower is None or upper is None:
                return None
            return {"lower": float(lower), "upper": float(upper)}
        except Exception as e:
            logger.debug(f"get_circuit_limits failed for {symbol}: {e}")
            return None

    def get_tick_size(self, symbol: str, exchange: str = "NSE") -> float:
        """Look up tick_size from the loaded instruments cache (default 0.05)."""
        from src.utils.tick_size import get_tick_size as _lookup
        if not self._instruments_cache:
            self.load_instruments(exchange)
        return _lookup(self._instruments_cache, symbol, exchange)
