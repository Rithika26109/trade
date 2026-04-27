"""
Mean-Reversion Strategy (Bollinger Band + RSI)
───────────────────────────────────────────────
Activates ONLY in ranging markets (low ADX) where the trend-following
strategies go silent. Buys at the lower Bollinger Band when RSI is
oversold, sells at the upper band when RSI is overbought.

Safety filters:
- BB squeeze detection (skip if bandwidth too narrow — breakout pending)
- Volume z-score cap (skip if breakout-level volume)
- HTF ranging confirmation boosts confluence
"""

import pandas as pd

from config import settings
from src.indicators.market_regime import MarketRegime
from src.strategy.base import BaseStrategy, Signal, TradeSignal
from src.strategy.confluence import calculate_confluence
from src.utils.logger import logger


class MeanReversionStrategy(BaseStrategy):
    """Buy at lower Bollinger Band, sell at upper — only in ranging markets."""

    @property
    def name(self) -> str:
        return "MEAN_REVERSION"

    def analyze(
        self,
        df: pd.DataFrame,
        symbol: str,
        df_htf: pd.DataFrame = None,
        regime: MarketRegime = None,
    ) -> TradeSignal:
        """Generate mean-reversion signal from BB touch + RSI confirmation."""
        required = ["close", "bb_lower", "bb_upper", "bb_middle", "bb_bandwidth", "rsi", "atr"]
        for col in required:
            if col not in df.columns:
                return self._hold(symbol, f"Missing indicator: {col}")

        if len(df) < 6:
            return self._hold(symbol, "Not enough data")

        close = df["close"].iloc[-1]
        bb_lower = df["bb_lower"].iloc[-1]
        bb_upper = df["bb_upper"].iloc[-1]
        bb_middle = df["bb_middle"].iloc[-1]
        bb_bw = df["bb_bandwidth"].iloc[-1]
        rsi = df["rsi"].iloc[-1]
        atr = df["atr"].iloc[-1]

        if any(pd.isna(v) for v in [close, bb_lower, bb_upper, bb_middle, bb_bw, rsi, atr]):
            return self._hold(symbol, "Indicators not ready")

        # ── ADX gate: only activate in ranging markets ──
        adx_max = getattr(settings, "MEAN_REV_ADX_MAX", 20)
        if "adx" in df.columns and pd.notna(df["adx"].iloc[-1]):
            adx = df["adx"].iloc[-1]
            if adx >= adx_max:
                return self._hold(symbol, f"ADX {adx:.1f} >= {adx_max} — not ranging")

        # ── Regime gate (redundant safety with ADX check) ──
        if regime is not None and getattr(settings, "ENABLE_REGIME_DETECTION", False):
            if regime.is_trending:
                return self._hold(symbol, f"Regime {regime.value} is trending")

        # ── BB squeeze filter: skip if bandwidth too narrow ──
        min_bw = getattr(settings, "MEAN_REV_MIN_BB_WIDTH_PCT", 0.5)
        if bb_bw < min_bw:
            return self._hold(symbol, f"BB squeeze (width {bb_bw:.2f}% < {min_bw}%)")

        # ── Volume filter: skip if breakout-level volume ──
        max_vol_z = getattr(settings, "MEAN_REV_MAX_VOL_Z", 2.0)
        if "volume" in df.columns and len(df) >= 21:
            vol = df["volume"].astype(float)
            recent_vol = vol.iloc[-1]
            window = vol.iloc[-21:-1]
            mu = window.mean()
            sd = window.std()
            if pd.notna(sd) and sd > 0:
                vol_z = (recent_vol - mu) / sd
                if vol_z > max_vol_z:
                    return self._hold(
                        symbol, f"Breakout volume (z={vol_z:.1f} > {max_vol_z})"
                    )

        # ── Signal generation ──
        rsi_oversold = getattr(settings, "MEAN_REV_RSI_OVERSOLD", 35)
        rsi_overbought = getattr(settings, "MEAN_REV_RSI_OVERBOUGHT", 65)

        signal = None

        # BUY: price at or below lower BB + RSI oversold
        if close <= bb_lower and rsi < rsi_oversold:
            stop_loss = close - (settings.ATR_MULTIPLIER * atr)
            risk = close - stop_loss
            min_rr_target = close + (risk * settings.MIN_RISK_REWARD_RATIO)
            target = max(bb_middle, min_rr_target)

            reason = (
                f"Mean-reversion BUY: close={close:.2f} at BB lower={bb_lower:.2f} | "
                f"RSI={rsi:.1f} | BB mid target={bb_middle:.2f}"
            )

            signal = TradeSignal(
                signal=Signal.BUY,
                symbol=symbol,
                price=close,
                stop_loss=stop_loss,
                target=target,
                reason=reason,
                strategy=self.name,
                rsi=rsi,
            )

        # SELL: price at or above upper BB + RSI overbought
        elif close >= bb_upper and rsi > rsi_overbought:
            stop_loss = close + (settings.ATR_MULTIPLIER * atr)
            risk = stop_loss - close
            min_rr_target = close - (risk * settings.MIN_RISK_REWARD_RATIO)
            target = min(bb_middle, min_rr_target)

            reason = (
                f"Mean-reversion SELL: close={close:.2f} at BB upper={bb_upper:.2f} | "
                f"RSI={rsi:.1f} | BB mid target={bb_middle:.2f}"
            )

            signal = TradeSignal(
                signal=Signal.SELL,
                symbol=symbol,
                price=close,
                stop_loss=stop_loss,
                target=target,
                reason=reason,
                strategy=self.name,
                rsi=rsi,
            )

        if signal is None:
            return self._hold(
                symbol,
                f"No mean-reversion setup (close={close:.2f}, "
                f"BB=[{bb_lower:.2f}, {bb_upper:.2f}], RSI={rsi:.1f})",
            )

        # ── Confluence scoring ──
        if getattr(settings, "ENABLE_CONFLUENCE_SCORING", False):
            conf = calculate_confluence(signal.signal, df, df_htf, regime)
            signal.confluence_score = conf.total
            signal.confluence_details = conf.components

        return signal
