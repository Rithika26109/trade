"""
VWAP + Supertrend Strategy
──────────────────────────
Uses VWAP as the primary trend filter and Supertrend for entry signals.

BUY when:
  - Price is above VWAP (bullish institutional bias)
  - Supertrend flips to bullish (direction changes from -1 to 1)

SELL when:
  - Price is below VWAP (bearish institutional bias)
  - Supertrend flips to bearish (direction changes from 1 to -1)

Stop-loss: Supertrend value (acts as trailing stop).
"""

import pandas as pd

from config import settings
from src.strategy.base import BaseStrategy, Signal, TradeSignal
from src.utils.logger import logger


class VWAPSupertrendStrategy(BaseStrategy):
    """VWAP + Supertrend strategy for intraday trading."""

    @property
    def name(self) -> str:
        return "VWAP_SUPERTREND"

    def analyze(self, df: pd.DataFrame, symbol: str) -> TradeSignal:
        """Generate signal based on VWAP trend + Supertrend flip."""
        required = ["close", "vwap", "supertrend", "supertrend_direction", "atr"]
        for col in required:
            if col not in df.columns:
                return self._hold(symbol, f"Missing indicator: {col}")

        confirm_candles = settings.SUPERTREND_CONFIRMATION_CANDLES
        min_len = max(3, confirm_candles + 2)
        if len(df) < min_len:
            return self._hold(symbol, "Not enough data")

        # Latest values
        close = df["close"].iloc[-1]
        vwap = df["vwap"].iloc[-1]
        st_value = df["supertrend"].iloc[-1]
        atr = df["atr"].iloc[-1]

        # Get recent supertrend directions for confirmation
        recent_dirs = df["supertrend_direction"].iloc[-(confirm_candles + 2):].tolist()

        if any(pd.isna(v) for v in [vwap, st_value, atr]) or any(pd.isna(d) for d in recent_dirs):
            return self._hold(symbol, "Indicators not ready")

        # Detect confirmed Supertrend flip (flip + N confirmation candles agreeing)
        # Bullish: was bearish(-1), then N+1 consecutive bullish(1) candles
        st_flipped_bullish = (recent_dirs[0] == -1 and
                              all(d == 1 for d in recent_dirs[1:]))
        st_flipped_bearish = (recent_dirs[0] == 1 and
                              all(d == -1 for d in recent_dirs[1:]))

        # ── BUY SIGNAL ──
        if st_flipped_bullish and close > vwap:
            stop_loss = st_value  # Supertrend value as stop
            risk = close - stop_loss
            if risk <= 0:
                return self._hold(symbol, "Invalid stop-loss (ST above price)")
            target = close + (risk * settings.MIN_RISK_REWARD_RATIO)

            return TradeSignal(
                signal=Signal.BUY,
                symbol=symbol,
                price=close,
                stop_loss=stop_loss,
                target=target,
                reason=f"Supertrend bullish flip, above VWAP={vwap:.2f}",
                strategy=self.name,
            )

        # ── SELL SIGNAL ──
        if st_flipped_bearish and close < vwap:
            stop_loss = st_value  # Supertrend value as stop
            risk = stop_loss - close
            if risk <= 0:
                return self._hold(symbol, "Invalid stop-loss (ST below price)")
            target = close - (risk * settings.MIN_RISK_REWARD_RATIO)

            return TradeSignal(
                signal=Signal.SELL,
                symbol=symbol,
                price=close,
                stop_loss=stop_loss,
                target=target,
                reason=f"Supertrend bearish flip, below VWAP={vwap:.2f}",
                strategy=self.name,
            )

        # Current trend info for hold reason
        current_dir = recent_dirs[-1]
        trend = "bullish" if current_dir == 1 else "bearish"
        side = "above" if close > vwap else "below"
        return self._hold(symbol, f"ST {trend}, price {side} VWAP, no confirmed flip")
