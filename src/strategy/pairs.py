"""
Pairs Trading Strategy — Simplified v1
───────────────────────────────────────
Trades the spread between correlated stock pairs. When one stock diverges
from its partner (z-score of log spread exceeds threshold), bet on
convergence: buy the underperformer, sell the outperformer.

v1 limitations (addressed in v2):
- Each leg is traded independently (no coordinated pair exit)
- MAX_POSITIONS_PER_SECTOR may block same-sector pair legs
- Fetches partner candles inside analyze() (extra API call)
"""

import numpy as np
import pandas as pd

from config import settings
from src.strategy.base import BaseStrategy, Signal, TradeSignal
from src.utils.logger import logger


class PairsTradingStrategy(BaseStrategy):
    """Trade spread divergence between correlated stock pairs."""

    def __init__(self, market_data=None):
        self._market_data = market_data

    @property
    def name(self) -> str:
        return "PAIRS"

    def set_market_data(self, market_data):
        """Wire market_data after construction (lazy injection)."""
        self._market_data = market_data

    def analyze(
        self,
        df: pd.DataFrame,
        symbol: str,
        df_htf: pd.DataFrame = None,
        regime=None,
    ) -> TradeSignal:
        """Generate signal from spread z-score between paired stocks."""
        if not self._market_data:
            return self._hold(symbol, "No market data for pairs")

        pair = self._find_pair(symbol)
        if pair is None:
            return self._hold(symbol, "Not in any configured pair")

        partner = pair[1] if pair[0] == symbol else pair[0]

        # Fetch partner candles
        try:
            df_partner = self._market_data.get_todays_candles(
                partner, interval=settings.TIMEFRAME
            )
        except Exception as e:
            logger.debug(f"[PAIRS] Failed to fetch {partner} data: {e}")
            return self._hold(symbol, f"Cannot fetch {partner} data")

        if df_partner is None or df_partner.empty:
            return self._hold(symbol, f"No data for partner {partner}")

        # Compute spread z-score
        z = self._compute_spread_zscore(df, df_partner, symbol, pair)
        if z is None:
            return self._hold(symbol, f"Insufficient aligned data for {symbol}/{partner}")

        close = df["close"].iloc[-1]
        atr = df["atr"].iloc[-1] if "atr" in df.columns and pd.notna(df["atr"].iloc[-1]) else close * 0.01

        entry_z = getattr(settings, "PAIRS_ENTRY_Z", 2.0)

        # BUY: spread z < -entry_z → symbol is undervalued relative to partner
        if z < -entry_z:
            stop_loss = close - (settings.ATR_MULTIPLIER * atr)
            risk = close - stop_loss
            target = close + (risk * settings.MIN_RISK_REWARD_RATIO)

            return TradeSignal(
                signal=Signal.BUY,
                symbol=symbol,
                price=close,
                stop_loss=stop_loss,
                target=target,
                reason=f"Pairs BUY: {symbol}/{partner} spread z={z:.2f} (undervalued)",
                strategy=self.name,
                confluence_score=60.0 + min(abs(z) * 10, 30),
                rsi=df["rsi"].iloc[-1] if "rsi" in df.columns and pd.notna(df["rsi"].iloc[-1]) else None,
            )

        # SELL: spread z > +entry_z → symbol is overvalued relative to partner
        if z > entry_z:
            stop_loss = close + (settings.ATR_MULTIPLIER * atr)
            risk = stop_loss - close
            target = close - (risk * settings.MIN_RISK_REWARD_RATIO)

            return TradeSignal(
                signal=Signal.SELL,
                symbol=symbol,
                price=close,
                stop_loss=stop_loss,
                target=target,
                reason=f"Pairs SELL: {symbol}/{partner} spread z={z:.2f} (overvalued)",
                strategy=self.name,
                confluence_score=60.0 + min(abs(z) * 10, 30),
                rsi=df["rsi"].iloc[-1] if "rsi" in df.columns and pd.notna(df["rsi"].iloc[-1]) else None,
            )

        return self._hold(symbol, f"Pairs: {symbol}/{partner} z={z:.2f} within bounds")

    def _find_pair(self, symbol: str) -> tuple | None:
        """Find the pair containing this symbol. Returns (A, B) or None."""
        pairs = getattr(settings, "PAIRS_SYMBOLS", [])
        for pair in pairs:
            if symbol in pair:
                return tuple(pair)
        return None

    def _compute_spread_zscore(
        self,
        df_a: pd.DataFrame,
        df_b: pd.DataFrame,
        symbol: str,
        pair: tuple,
    ) -> float | None:
        """
        Compute z-score of log spread between two symbols.
        Spread direction is always computed as log(pair[0] / pair[1])
        regardless of which symbol triggered the analysis, so both
        symbols see the same spread (with opposite sign for the second).
        """
        min_history = getattr(settings, "PAIRS_MIN_HISTORY", 20)
        lookback = getattr(settings, "PAIRS_LOOKBACK", 50)

        if "date" not in df_a.columns or "date" not in df_b.columns:
            return None
        if "close" not in df_a.columns or "close" not in df_b.columns:
            return None

        merged = pd.merge(
            df_a[["date", "close"]].rename(columns={"close": "close_a"}),
            df_b[["date", "close"]].rename(columns={"close": "close_b"}),
            on="date",
            how="inner",
        )

        if len(merged) < min_history:
            return None

        # Replace zeros/negatives to avoid log errors
        merged = merged[(merged["close_a"] > 0) & (merged["close_b"] > 0)]
        if len(merged) < min_history:
            return None

        # Always compute spread from the current symbol's perspective:
        #   spread = log(symbol_close / partner_close)
        # So: z > 0 means symbol is overvalued → SELL
        #     z < 0 means symbol is undervalued → BUY
        spread = np.log(merged["close_a"] / merged["close_b"])

        window = spread.tail(lookback)
        mean = window.mean()
        std = window.std()

        if pd.isna(std) or std == 0:
            return None

        return float((spread.iloc[-1] - mean) / std)
