"""
RSI + EMA Crossover Strategy
─────────────────────────────
Combines trend detection (EMA crossover) with momentum filter (RSI).

BUY when:
  - Fast EMA crosses above Slow EMA (bullish trend)
  - RSI is between 40-70 (has room to go up, not overbought)
  - Price is above VWAP (institutional buying)

SELL when:
  - Fast EMA crosses below Slow EMA (bearish trend)
  - RSI is between 30-60 (has room to go down, not oversold)
  - Price is below VWAP
"""

import pandas as pd

from config import settings
from src.indicators.indicators import ema_crossover
from src.strategy.base import BaseStrategy, Signal, TradeSignal
from src.utils.logger import logger


class RSIEMAStrategy(BaseStrategy):
    """RSI + EMA Crossover strategy for intraday trading."""

    @property
    def name(self) -> str:
        return "RSI_EMA"

    def analyze(self, df: pd.DataFrame, symbol: str) -> TradeSignal:
        """Generate signal based on EMA crossover confirmed by RSI."""
        required = ["close", "rsi", "ema_fast", "ema_slow", "atr"]
        for col in required:
            if col not in df.columns:
                return self._hold(symbol, f"Missing indicator: {col}")

        if len(df) < 3:
            return self._hold(symbol, "Not enough data")

        # Latest values
        close = df["close"].iloc[-1]
        rsi = df["rsi"].iloc[-1]
        atr = df["atr"].iloc[-1]

        if pd.isna(rsi) or pd.isna(atr):
            return self._hold(symbol, "Indicators not ready")

        # Check VWAP if available
        has_vwap = "vwap" in df.columns and pd.notna(df["vwap"].iloc[-1])
        vwap = df["vwap"].iloc[-1] if has_vwap else None

        # Check EMA crossover
        crossover = ema_crossover(df)

        # ── BUY SIGNAL ──
        if crossover == "BULLISH":
            rsi_ok = settings.RSI_BUY_MIN <= rsi <= settings.RSI_BUY_MAX
            vwap_ok = (close > vwap) if vwap else True

            if rsi_ok and vwap_ok:
                stop_loss = close - (settings.ATR_MULTIPLIER * atr)
                risk = close - stop_loss
                target = close + (risk * settings.MIN_RISK_REWARD_RATIO)

                reason = f"EMA bullish crossover, RSI={rsi:.1f}"
                if vwap:
                    reason += f", above VWAP={vwap:.2f}"

                return TradeSignal(
                    signal=Signal.BUY,
                    symbol=symbol,
                    price=close,
                    stop_loss=stop_loss,
                    target=target,
                    reason=reason,
                    strategy=self.name,
                )

        # ── SELL SIGNAL ──
        elif crossover == "BEARISH":
            rsi_ok = settings.RSI_SELL_MIN <= rsi <= settings.RSI_SELL_MAX
            vwap_ok = (close < vwap) if vwap else True

            if rsi_ok and vwap_ok:
                stop_loss = close + (settings.ATR_MULTIPLIER * atr)
                risk = stop_loss - close
                target = close - (risk * settings.MIN_RISK_REWARD_RATIO)

                reason = f"EMA bearish crossover, RSI={rsi:.1f}"
                if vwap:
                    reason += f", below VWAP={vwap:.2f}"

                return TradeSignal(
                    signal=Signal.SELL,
                    symbol=symbol,
                    price=close,
                    stop_loss=stop_loss,
                    target=target,
                    reason=reason,
                    strategy=self.name,
                )

        return self._hold(symbol, f"No crossover (RSI={rsi:.1f})")
