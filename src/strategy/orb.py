"""
Opening Range Breakout (ORB) Strategy — Enhanced
─────────────────────────────────────────────────
Professional-grade ORB with:
- Gap analysis (adjusts behavior for gap-up/gap-down opens)
- Range size filter (skip too tight or too wide ranges)
- Volume acceleration (not just level, but acceleration)
- Higher-timeframe trend filter (15-min EMA alignment)
- Market regime awareness (skip ranging markets)
- Confluence scoring
"""

import pandas as pd

from config import settings
from src.indicators.market_regime import MarketRegime
from src.strategy.base import BaseStrategy, Signal, TradeSignal
from src.strategy.confluence import calculate_confluence
from src.utils.logger import logger


class ORBStrategy(BaseStrategy):
    """Opening Range Breakout strategy with professional filters."""

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
        range_pct = (range_size / open_price) * 100 if open_price > 0 else 0
        logger.info(
            f"[ORB] {symbol} opening range set: "
            f"High={high:.2f}, Low={low:.2f}, Range={range_size:.2f} ({range_pct:.2f}%)"
        )

    def analyze(
        self,
        df: pd.DataFrame,
        symbol: str,
        df_htf: pd.DataFrame = None,
        regime: MarketRegime = None,
    ) -> TradeSignal:
        """
        Check for breakout with professional-grade filters.
        """
        if symbol not in self._opening_range:
            return self._hold(symbol, "Opening range not set yet")

        if len(df) < 2:
            return self._hold(symbol, "Not enough data")

        orb = self._opening_range[symbol]
        orb_high = orb["high"]
        orb_low = orb["low"]
        range_size = orb_high - orb_low

        # ── Range size filter ──
        if range_size > 0 and orb["open"] > 0:
            range_pct = (range_size / orb["open"]) * 100
            if range_pct < 0.3:
                return self._hold(symbol, f"ORB range too tight ({range_pct:.2f}%)")
            if range_pct > 3.0:
                return self._hold(symbol, f"ORB range too wide ({range_pct:.2f}%)")

        # ── Market regime filter ──
        if regime is not None and getattr(settings, 'ENABLE_REGIME_DETECTION', False):
            if regime == MarketRegime.RANGING:
                return self._hold(symbol, f"Ranging market (regime: {regime.value})")

        current_close = df["close"].iloc[-1]
        current_high = df["high"].iloc[-1]
        current_low = df["low"].iloc[-1]
        prev_close = df["close"].iloc[-2]

        # Use ATR for dynamic stop if available, otherwise use range
        atr = df["atr"].iloc[-1] if "atr" in df.columns and pd.notna(df["atr"].iloc[-1]) else range_size

        # ── Volume confirmation with acceleration ──
        volume_confirmed = True
        volume_accelerating = False
        if "volume" in df.columns and len(df) >= 6:
            current_volume = df["volume"].iloc[-1]
            avg_volume = df["volume"].iloc[-6:-1].mean()
            if avg_volume > 0:
                volume_confirmed = current_volume >= (avg_volume * settings.ORB_VOLUME_MULTIPLIER)
                # Volume acceleration: increasing over last 2 candles
                if len(df) >= 3:
                    vol_prev = df["volume"].iloc[-2]
                    vol_prev2 = df["volume"].iloc[-3]
                    volume_accelerating = current_volume > vol_prev > vol_prev2

        # ── Gap analysis ──
        gap_info = self._analyze_gap(symbol, df)

        # ── HTF trend filter ──
        htf_bullish = None
        if df_htf is not None and not df_htf.empty:
            if "ema_fast" in df_htf.columns and "ema_slow" in df_htf.columns:
                htf_fast = df_htf["ema_fast"].iloc[-1]
                htf_slow = df_htf["ema_slow"].iloc[-1]
                if not pd.isna(htf_fast) and not pd.isna(htf_slow):
                    htf_bullish = htf_fast > htf_slow

        # ── BREAKOUT ABOVE (BUY) ──
        if current_close > orb_high and prev_close <= orb_high and volume_confirmed:
            # HTF filter: skip BUY if 15-min trend is bearish
            if htf_bullish is not None and not htf_bullish:
                return self._hold(symbol, "ORB BUY rejected: 15-min trend bearish")

            # Gap filter: skip BUY breakout if huge gap down (mean-reversion likely)
            if gap_info.get("is_large_gap") and gap_info.get("is_gap_down"):
                return self._hold(symbol, "ORB BUY rejected: large gap down")

            # Stop-loss
            if settings.STOP_LOSS_TYPE == "ATR" and not pd.isna(atr):
                stop_loss = max(current_close - (settings.ATR_MULTIPLIER * atr), orb_low)
            else:
                stop_loss = orb_low
            risk = current_close - stop_loss
            target = current_close + (risk * settings.MIN_RISK_REWARD_RATIO)

            reason_parts = [f"ORB breakout above {orb_high:.2f}"]
            if volume_accelerating:
                reason_parts.append("vol accelerating")
            if gap_info.get("gap_pct", 0) != 0:
                reason_parts.append(f"gap {gap_info['gap_pct']:+.1f}%")
            if htf_bullish:
                reason_parts.append("HTF bullish")

            signal = TradeSignal(
                signal=Signal.BUY,
                symbol=symbol,
                price=current_close,
                stop_loss=stop_loss,
                target=target,
                reason=" | ".join(reason_parts),
                strategy=self.name,
            )

            # Calculate confluence score
            if getattr(settings, 'ENABLE_CONFLUENCE_SCORING', False):
                conf = calculate_confluence(Signal.BUY, df, df_htf, regime)
                signal.confluence_score = conf.total
                signal.confluence_details = conf.components

            return signal

        # ── BREAKDOWN BELOW (SELL) ──
        if current_close < orb_low and prev_close >= orb_low and volume_confirmed:
            # HTF filter: skip SELL if 15-min trend is bullish
            if htf_bullish is not None and htf_bullish:
                return self._hold(symbol, "ORB SELL rejected: 15-min trend bullish")

            # Gap filter: skip SELL breakdown if huge gap up
            if gap_info.get("is_large_gap") and gap_info.get("is_gap_up"):
                return self._hold(symbol, "ORB SELL rejected: large gap up")

            if settings.STOP_LOSS_TYPE == "ATR" and not pd.isna(atr):
                stop_loss = min(current_close + (settings.ATR_MULTIPLIER * atr), orb_high)
            else:
                stop_loss = orb_high
            risk = stop_loss - current_close
            target = current_close - (risk * settings.MIN_RISK_REWARD_RATIO)

            reason_parts = [f"ORB breakdown below {orb_low:.2f}"]
            if volume_accelerating:
                reason_parts.append("vol accelerating")
            if gap_info.get("gap_pct", 0) != 0:
                reason_parts.append(f"gap {gap_info['gap_pct']:+.1f}%")
            if htf_bullish is not None and not htf_bullish:
                reason_parts.append("HTF bearish")

            signal = TradeSignal(
                signal=Signal.SELL,
                symbol=symbol,
                price=current_close,
                stop_loss=stop_loss,
                target=target,
                reason=" | ".join(reason_parts),
                strategy=self.name,
            )

            if getattr(settings, 'ENABLE_CONFLUENCE_SCORING', False):
                conf = calculate_confluence(Signal.SELL, df, df_htf, regime)
                signal.confluence_score = conf.total
                signal.confluence_details = conf.components

            return signal

        return self._hold(symbol, f"Price within range [{orb_low:.2f} - {orb_high:.2f}]")

    def _analyze_gap(self, symbol: str, df: pd.DataFrame) -> dict:
        """Analyze opening gap relative to previous close."""
        orb = self._opening_range[symbol]
        result = {"gap_pct": 0, "is_gap_up": False, "is_gap_down": False, "is_large_gap": False}

        if len(df) < 2:
            return result

        # Find previous day's close (last close before today's data)
        today = settings.now_ist().date()
        prev_day_data = df[df["date"].dt.date < today]
        if prev_day_data.empty:
            return result

        prev_close = prev_day_data["close"].iloc[-1]
        if prev_close <= 0:
            return result

        gap_pct = ((orb["open"] - prev_close) / prev_close) * 100
        result["gap_pct"] = gap_pct
        result["is_gap_up"] = gap_pct > 0.5
        result["is_gap_down"] = gap_pct < -0.5
        result["is_large_gap"] = abs(gap_pct) > 1.5
        return result

    def is_range_set(self, symbol: str) -> bool:
        """Check if opening range has been recorded for a symbol."""
        return symbol in self._opening_range

    def get_range(self, symbol: str) -> dict | None:
        """Get the opening range for a symbol."""
        return self._opening_range.get(symbol)
