"""
VWAP + Supertrend Strategy — Enhanced
──────────────────────────────────────
Professional-grade with:
- Volume-weighted confirmation (not just candle count)
- VWAP distance filtering (avoid extended entries)
- Market regime filter (skip ranging markets)
- Higher-timeframe Supertrend agreement
- Confluence scoring
"""

import pandas as pd

from config import settings
from src.indicators.market_regime import MarketRegime
from src.strategy.base import BaseStrategy, Signal, TradeSignal
from src.strategy.confluence import calculate_confluence
from src.utils.logger import logger


class VWAPSupertrendStrategy(BaseStrategy):
    """VWAP + Supertrend strategy with professional filters."""

    @property
    def name(self) -> str:
        return "VWAP_SUPERTREND"

    def analyze(
        self,
        df: pd.DataFrame,
        symbol: str,
        df_htf: pd.DataFrame = None,
        regime: MarketRegime = None,
    ) -> TradeSignal:
        """Generate signal based on VWAP trend + Supertrend flip."""
        required = ["close", "vwap", "supertrend", "supertrend_direction", "atr"]
        for col in required:
            if col not in df.columns:
                return self._hold(symbol, f"Missing indicator: {col}")

        confirm_candles = settings.SUPERTREND_CONFIRMATION_CANDLES
        min_len = max(3, confirm_candles + 2)
        if len(df) < min_len:
            return self._hold(symbol, "Not enough data")

        # ── Market regime filter ──
        # Removed hard RANGING block — let regime tracker weight this
        # strategy down in regimes where it underperforms.

        # Latest values
        close = df["close"].iloc[-1]
        vwap = df["vwap"].iloc[-1]
        st_value = df["supertrend"].iloc[-1]
        atr = df["atr"].iloc[-1]

        # Get recent supertrend directions for confirmation (with catch-up window)
        catchup = getattr(settings, 'CATCH_UP_CANDLES', 0)
        window = confirm_candles + 2 + max(catchup, 6)  # At least 30 min lookback
        recent_dirs = df["supertrend_direction"].iloc[-window:].tolist()

        if any(pd.isna(v) for v in [vwap, st_value, atr]) or any(pd.isna(d) for d in recent_dirs):
            return self._hold(symbol, "Indicators not ready")

        # ── Volume-weighted confirmation ──
        st_flipped_bullish, st_flipped_bearish = self._check_weighted_flip(
            df, recent_dirs, confirm_candles
        )

        # ── VWAP distance check ──
        vwap_distance_pct = abs(close - vwap) / vwap * 100 if vwap > 0 else 0
        vwap_extended = vwap_distance_pct > 1.5  # More than 1.5% from VWAP is extended

        # ── HTF Supertrend agreement ──
        htf_agrees = True
        htf_info = ""
        if df_htf is not None and not df_htf.empty:
            if "supertrend_direction" in df_htf.columns:
                htf_st_dir = df_htf["supertrend_direction"].iloc[-1]
                if not pd.isna(htf_st_dir):
                    if st_flipped_bullish and htf_st_dir != 1:
                        htf_agrees = False
                        htf_info = " (HTF ST bearish)"
                    elif st_flipped_bearish and htf_st_dir != -1:
                        htf_agrees = False
                        htf_info = " (HTF ST bullish)"
                    else:
                        htf_info = " HTF confirmed"

        # ── BUY SIGNAL ──
        if st_flipped_bullish and close > vwap:
            if not htf_agrees:
                return self._hold(symbol, f"Supertrend bullish flip rejected{htf_info}")

            stop_loss = st_value  # Supertrend value as stop
            risk = close - stop_loss
            if risk <= 0:
                return self._hold(symbol, "Invalid stop-loss (ST above price)")
            target = close + (risk * settings.TARGET_RISK_REWARD_RATIO)

            reason_parts = [f"Supertrend bullish flip, above VWAP={vwap:.2f}"]
            if vwap_extended:
                reason_parts.append(f"VWAP distance={vwap_distance_pct:.1f}% (extended)")
            if regime:
                reason_parts.append(f"regime={regime.value}")
            if htf_info:
                reason_parts.append(htf_info.strip())

            signal = TradeSignal(
                signal=Signal.BUY,
                symbol=symbol,
                price=close,
                stop_loss=stop_loss,
                target=target,
                reason=" | ".join(reason_parts),
                strategy=self.name,
            )

            if getattr(settings, 'ENABLE_CONFLUENCE_SCORING', False):
                conf = calculate_confluence(Signal.BUY, df, df_htf, regime)
                # Penalize extended VWAP entries
                if vwap_extended:
                    conf.total = max(0, conf.total - 10)
                    conf.components["vwap_extension_penalty"] = -10
                signal.confluence_score = conf.total
                signal.confluence_details = conf.components

            return signal

        # ── SELL SIGNAL ──
        if st_flipped_bearish and close < vwap:
            if not htf_agrees:
                return self._hold(symbol, f"Supertrend bearish flip rejected{htf_info}")

            stop_loss = st_value  # Supertrend value as stop
            risk = stop_loss - close
            if risk <= 0:
                return self._hold(symbol, "Invalid stop-loss (ST below price)")
            target = close - (risk * settings.TARGET_RISK_REWARD_RATIO)

            reason_parts = [f"Supertrend bearish flip, below VWAP={vwap:.2f}"]
            if vwap_extended:
                reason_parts.append(f"VWAP distance={vwap_distance_pct:.1f}% (extended)")
            if regime:
                reason_parts.append(f"regime={regime.value}")

            signal = TradeSignal(
                signal=Signal.SELL,
                symbol=symbol,
                price=close,
                stop_loss=stop_loss,
                target=target,
                reason=" | ".join(reason_parts),
                strategy=self.name,
            )

            if getattr(settings, 'ENABLE_CONFLUENCE_SCORING', False):
                conf = calculate_confluence(Signal.SELL, df, df_htf, regime)
                if vwap_extended:
                    conf.total = max(0, conf.total - 10)
                    conf.components["vwap_extension_penalty"] = -10
                signal.confluence_score = conf.total
                signal.confluence_details = conf.components

            return signal

        # Current trend info for hold reason
        current_dir = recent_dirs[-1]
        trend = "bullish" if current_dir == 1 else "bearish"
        side = "above" if close > vwap else "below"
        return self._hold(symbol, f"ST {trend}, price {side} VWAP, no confirmed flip")

    def _check_weighted_flip(
        self,
        df: pd.DataFrame,
        recent_dirs: list,
        confirm_candles: int,
    ) -> tuple[bool, bool]:
        """
        Volume-weighted Supertrend flip confirmation.
        Scans the window for the most recent direction change, then checks
        that enough confirmed candles follow it (by volume weight).
        """
        # Find the most recent flip point in the window
        flip_idx = None
        for i in range(len(recent_dirs) - 1):
            if recent_dirs[i] != recent_dirs[i + 1]:
                flip_idx = i  # keep scanning — we want the latest flip

        if flip_idx is None:
            return False, False

        old_dir = recent_dirs[flip_idx]
        new_dir = recent_dirs[flip_idx + 1]

        # All candles after the flip must stay in the new direction
        post_flip = recent_dirs[flip_idx + 1:]
        if not all(d == new_dir for d in post_flip):
            return False, False

        # Calculate average volume for normalization
        avg_vol = df["volume"].iloc[-20:].mean() if "volume" in df.columns and len(df) >= 20 else 0

        if avg_vol <= 0:
            # Simple candle count confirmation
            confirmed = len(post_flip) >= confirm_candles
            return (
                old_dir == -1 and new_dir == 1 and confirmed,
                old_dir == 1 and new_dir == -1 and confirmed,
            )

        # Volume-weighted confirmation
        min_weighted_count = confirm_candles + 0.5
        weighted = 0
        for i in range(flip_idx + 1, len(recent_dirs)):
            idx = -(len(recent_dirs) - i)
            vol = df["volume"].iloc[idx] if "volume" in df.columns else avg_vol
            vol_weight = min(vol / avg_vol, 2.0) if avg_vol > 0 else 1.0
            weighted += vol_weight

        return (
            old_dir == -1 and new_dir == 1 and weighted >= min_weighted_count,
            old_dir == 1 and new_dir == -1 and weighted >= min_weighted_count,
        )
