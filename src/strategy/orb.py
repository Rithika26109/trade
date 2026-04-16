"""
Opening Range Breakout (ORB) Strategy
──────────────────────────────────────
The simplest and most beginner-friendly intraday strategy.

How it works:
1. Wait for the first 15 minutes (9:15 - 9:30)
2. Record the HIGH and LOW of that period
3. If price breaks ABOVE the high → BUY
4. If price breaks BELOW the low → SELL (short)
5. Stop-loss at the opposite end of the range
"""

import pandas as pd

from config import settings
from src.strategy.base import BaseStrategy, Signal, TradeSignal
from src.utils.logger import logger


class ORBStrategy(BaseStrategy):
    """Opening Range Breakout strategy."""

    def __init__(self):
        self._opening_range: dict[str, dict] = {}  # symbol → {high, low, open}

    @property
    def name(self) -> str:
        return "ORB"

    def set_opening_range(self, symbol: str, high: float, low: float, open_price: float):
        """Set the opening range for a symbol (called after first 15 min)."""
        self._opening_range[symbol] = {
            "high": high,
            "low": low,
            "open": open_price,
        }
        range_size = high - low
        range_pct = (range_size / open_price) * 100
        logger.info(
            f"[ORB] {symbol} opening range set: "
            f"High={high:.2f}, Low={low:.2f}, Range={range_size:.2f} ({range_pct:.2f}%)"
        )

    def analyze(self, df: pd.DataFrame, symbol: str) -> TradeSignal:
        """
        Check if price has broken out of the opening range.

        Args:
            df: OHLCV DataFrame (should have latest candles)
            symbol: Stock symbol

        Returns:
            BUY if breakout above, SELL if breakdown below, HOLD otherwise
        """
        if symbol not in self._opening_range:
            return self._hold(symbol, "Opening range not set yet")

        if len(df) < 2:
            return self._hold(symbol, "Not enough data")

        orb = self._opening_range[symbol]
        orb_high = orb["high"]
        orb_low = orb["low"]
        range_size = orb_high - orb_low

        # Current and previous candle
        current_close = df["close"].iloc[-1]
        current_high = df["high"].iloc[-1]
        current_low = df["low"].iloc[-1]
        prev_close = df["close"].iloc[-2]

        # Use ATR for dynamic stop if available, otherwise use range
        atr = df["atr"].iloc[-1] if "atr" in df.columns and pd.notna(df["atr"].iloc[-1]) else range_size

        # Volume confirmation: breakout candle must have >= 1.5x average volume
        volume_confirmed = True
        if "volume" in df.columns and len(df) >= 6:
            current_volume = df["volume"].iloc[-1]
            avg_volume = df["volume"].iloc[-6:-1].mean()
            if avg_volume > 0:
                volume_confirmed = current_volume >= (avg_volume * settings.ORB_VOLUME_MULTIPLIER)

        # ── BREAKOUT ABOVE (BUY) ──
        # Price closes above ORB high AND previous close was below/at ORB high
        if current_close > orb_high and prev_close <= orb_high and volume_confirmed:
            # Stop-loss: ATR-based or range-based depending on settings
            if settings.STOP_LOSS_TYPE == "ATR" and not pd.isna(atr):
                stop_loss = max(current_close - (settings.ATR_MULTIPLIER * atr), orb_low)
            else:
                stop_loss = orb_low
            risk = current_close - stop_loss
            target = current_close + (risk * settings.MIN_RISK_REWARD_RATIO)

            return TradeSignal(
                signal=Signal.BUY,
                symbol=symbol,
                price=current_close,
                stop_loss=stop_loss,
                target=target,
                reason=f"ORB breakout above {orb_high:.2f} (vol confirmed)",
                strategy=self.name,
            )

        # ── BREAKDOWN BELOW (SELL) ──
        # Price closes below ORB low AND previous close was above/at ORB low
        if current_close < orb_low and prev_close >= orb_low and volume_confirmed:
            # Stop-loss: ATR-based or range-based depending on settings
            if settings.STOP_LOSS_TYPE == "ATR" and not pd.isna(atr):
                stop_loss = min(current_close + (settings.ATR_MULTIPLIER * atr), orb_high)
            else:
                stop_loss = orb_high
            risk = stop_loss - current_close
            target = current_close - (risk * settings.MIN_RISK_REWARD_RATIO)

            return TradeSignal(
                signal=Signal.SELL,
                symbol=symbol,
                price=current_close,
                stop_loss=stop_loss,
                target=target,
                reason=f"ORB breakdown below {orb_low:.2f} (vol confirmed)",
                strategy=self.name,
            )

        return self._hold(symbol, f"Price within range [{orb_low:.2f} - {orb_high:.2f}]")

    def is_range_set(self, symbol: str) -> bool:
        """Check if opening range has been recorded for a symbol."""
        return symbol in self._opening_range

    def get_range(self, symbol: str) -> dict | None:
        """Get the opening range for a symbol."""
        return self._opening_range.get(symbol)
