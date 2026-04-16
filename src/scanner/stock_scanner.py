"""
Stock Scanner
─────────────
Scans and filters the watchlist for the most tradeable stocks each day.
Selects stocks based on volume, price range, and volatility.
"""

import pandas as pd
from kiteconnect import KiteConnect

from config import settings
from src.data.market_data import MarketData
from src.utils.logger import logger


class StockScanner:
    """Filters watchlist stocks for best intraday candidates."""

    def __init__(self, market_data: MarketData):
        self.market_data = market_data

    def scan(self, watchlist: list[str] = None) -> list[str]:
        """
        Scan stocks and return the best candidates for today.

        Filters:
        - Price within configured range
        - Volume above minimum threshold
        - Has sufficient volatility (ATR-based)

        Returns sorted list of symbols (best candidates first).
        """
        watchlist = watchlist or settings.WATCHLIST
        candidates = []

        logger.info(f"Scanning {len(watchlist)} stocks...")

        for symbol in watchlist:
            try:
                score = self._score_stock(symbol)
                if score is not None:
                    candidates.append((symbol, score))
            except Exception as e:
                logger.debug(f"Skipping {symbol}: {e}")

        # Sort by score (higher is better)
        candidates.sort(key=lambda x: x[1], reverse=True)
        selected = [s for s, _ in candidates]

        logger.info(f"Selected {len(selected)} stocks: {selected}")
        return selected

    def _score_stock(self, symbol: str) -> float | None:
        """
        Score a stock for intraday tradability.
        Returns score (higher = better) or None if filtered out.
        """
        # Get recent data (5 days of daily candles for screening)
        df = self.market_data.get_historical_data(symbol, interval="day", days=10)
        if df.empty or len(df) < 5:
            return None

        latest = df.iloc[-1]
        price = latest["close"]
        volume = latest["volume"]

        # Price filter
        if price < settings.MIN_PRICE or price > settings.MAX_PRICE:
            return None

        # Volume filter
        avg_volume = df["volume"].tail(5).mean()
        if avg_volume < settings.MIN_VOLUME:
            return None

        # Calculate volatility (ATR % of price)
        df["tr"] = pd.concat([
            df["high"] - df["low"],
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr = df["tr"].tail(5).mean()
        atr_pct = (atr / price) * 100

        # Score: prefer higher volume and moderate volatility (1-4%)
        volume_score = min(avg_volume / settings.MIN_VOLUME, 5)  # Cap at 5x
        volatility_score = min(atr_pct, 4) if atr_pct >= 0.5 else 0  # Want 0.5-4%

        return volume_score + volatility_score
