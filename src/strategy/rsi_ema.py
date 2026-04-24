"""
RSI + EMA Crossover Strategy — Enhanced
────────────────────────────────────────
Professional-grade with:
- Adaptive RSI ranges based on market regime
- ADX trend strength filter (reject signals in low-ADX environments)
- RSI divergence detection (strongest reversal signal)
- Higher-timeframe EMA confirmation
- Confluence scoring
"""

import pandas as pd

from config import settings
from src.indicators.indicators import ema_crossover
from src.indicators.market_regime import MarketRegime
from src.strategy.base import BaseStrategy, Signal, TradeSignal
from src.strategy.confluence import calculate_confluence
from src.utils.logger import logger


class RSIEMAStrategy(BaseStrategy):
    """RSI + EMA Crossover strategy with professional filters."""

    @property
    def name(self) -> str:
        return "RSI_EMA"

    def analyze(
        self,
        df: pd.DataFrame,
        symbol: str,
        df_htf: pd.DataFrame = None,
        regime: MarketRegime = None,
    ) -> TradeSignal:
        """Generate signal based on EMA crossover confirmed by RSI with regime adaptation."""
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

        # ── ADX trend strength filter ──
        if "adx" in df.columns:
            adx = df["adx"].iloc[-1]
            if not pd.isna(adx) and adx < 20:
                return self._hold(symbol, f"ADX too low ({adx:.1f}) — no clear trend")

        # ── Get adaptive RSI ranges based on regime ──
        rsi_ranges = self._get_rsi_ranges(regime)

        # Check VWAP if available
        has_vwap = "vwap" in df.columns and pd.notna(df["vwap"].iloc[-1])
        vwap = df["vwap"].iloc[-1] if has_vwap else None

        # Check EMA crossover (with catch-up lookback for mid-session starts)
        catchup = getattr(settings, 'CATCH_UP_CANDLES', 1)
        crossover = ema_crossover(df, lookback=catchup)

        # ── Check for RSI divergence (stronger signal) ──
        divergence = self._detect_rsi_divergence(df)

        # ── HTF trend confirmation ──
        htf_aligned = True
        htf_info = ""
        if df_htf is not None and not df_htf.empty:
            if "ema_fast" in df_htf.columns and "ema_slow" in df_htf.columns:
                htf_fast = df_htf["ema_fast"].iloc[-1]
                htf_slow = df_htf["ema_slow"].iloc[-1]
                if not pd.isna(htf_fast) and not pd.isna(htf_slow):
                    htf_bullish = htf_fast > htf_slow
                    if crossover == "BULLISH" and not htf_bullish:
                        htf_aligned = False
                        htf_info = " (HTF bearish — filtered)"
                    elif crossover == "BEARISH" and htf_bullish:
                        htf_aligned = False
                        htf_info = " (HTF bullish — filtered)"
                    else:
                        htf_info = " HTF confirmed"

        # ── BUY SIGNAL ──
        if crossover == "BULLISH" or divergence == "BULLISH":
            rsi_ok = rsi_ranges["buy_min"] <= rsi <= rsi_ranges["buy_max"]
            vwap_ok = (close > vwap) if vwap else True

            # Divergence overrides strict RSI range (it's a stronger signal)
            if divergence == "BULLISH" and not rsi_ok:
                rsi_ok = rsi < 60  # More lenient for divergence

            if not htf_aligned and divergence != "BULLISH":
                return self._hold(symbol, f"EMA bullish crossover{htf_info}")

            if rsi_ok and vwap_ok:
                stop_loss = close - (settings.ATR_MULTIPLIER * atr)
                risk = close - stop_loss
                target = close + (risk * settings.MIN_RISK_REWARD_RATIO)

                reason_parts = []
                if crossover == "BULLISH":
                    reason_parts.append("EMA bullish crossover")
                if divergence == "BULLISH":
                    reason_parts.append("RSI bullish divergence")
                reason_parts.append(f"RSI={rsi:.1f}")
                if vwap:
                    reason_parts.append(f"above VWAP={vwap:.2f}")
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
                    signal.confluence_score = conf.total
                    signal.confluence_details = conf.components

                return signal

        # ── SELL SIGNAL ──
        if crossover == "BEARISH" or divergence == "BEARISH":
            rsi_ok = rsi_ranges["sell_min"] <= rsi <= rsi_ranges["sell_max"]
            vwap_ok = (close < vwap) if vwap else True

            if divergence == "BEARISH" and not rsi_ok:
                rsi_ok = rsi > 40

            if not htf_aligned and divergence != "BEARISH":
                return self._hold(symbol, f"EMA bearish crossover{htf_info}")

            if rsi_ok and vwap_ok:
                stop_loss = close + (settings.ATR_MULTIPLIER * atr)
                risk = stop_loss - close
                target = close - (risk * settings.MIN_RISK_REWARD_RATIO)

                reason_parts = []
                if crossover == "BEARISH":
                    reason_parts.append("EMA bearish crossover")
                if divergence == "BEARISH":
                    reason_parts.append("RSI bearish divergence")
                reason_parts.append(f"RSI={rsi:.1f}")
                if vwap:
                    reason_parts.append(f"below VWAP={vwap:.2f}")
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
                    signal.confluence_score = conf.total
                    signal.confluence_details = conf.components

                return signal

        return self._hold(symbol, f"No crossover (RSI={rsi:.1f})")

    def _get_rsi_ranges(self, regime: MarketRegime = None) -> dict:
        """Adapt RSI ranges based on market regime."""
        if regime is None or not getattr(settings, 'ENABLE_REGIME_DETECTION', False):
            return {
                "buy_min": settings.RSI_BUY_MIN,
                "buy_max": settings.RSI_BUY_MAX,
                "sell_min": settings.RSI_SELL_MIN,
                "sell_max": settings.RSI_SELL_MAX,
            }

        if regime in (MarketRegime.STRONG_TREND_UP, MarketRegime.TREND_UP):
            # In uptrend: allow buying at higher RSI (momentum still going)
            return {"buy_min": 35, "buy_max": 65, "sell_min": 55, "sell_max": 80}

        elif regime in (MarketRegime.STRONG_TREND_DOWN, MarketRegime.TREND_DOWN):
            # In downtrend: tighter buy range (only deep oversold), wider sell
            return {"buy_min": 20, "buy_max": 45, "sell_min": 35, "sell_max": 65}

        else:  # RANGING or VOLATILE
            # Classic mean-reversion ranges
            return {"buy_min": 25, "buy_max": 45, "sell_min": 55, "sell_max": 75}

    def _detect_rsi_divergence(self, df: pd.DataFrame) -> str | None:
        """
        Detect RSI divergence on the last 20 candles.
        Bullish divergence: price makes lower low but RSI makes higher low.
        Bearish divergence: price makes higher high but RSI makes lower high.
        Returns: "BULLISH", "BEARISH", or None
        """
        if "rsi" not in df.columns or len(df) < 10:
            return None

        lookback = min(20, len(df))
        prices = df["close"].iloc[-lookback:]
        rsis = df["rsi"].iloc[-lookback:]

        if rsis.isna().sum() > lookback * 0.3:
            return None

        # Find two most recent swing lows for bullish divergence
        lows_idx = []
        for i in range(2, len(prices) - 1):
            if prices.iloc[i] < prices.iloc[i-1] and prices.iloc[i] < prices.iloc[i+1]:
                lows_idx.append(i)

        if len(lows_idx) >= 2:
            prev_low_i = lows_idx[-2]
            curr_low_i = lows_idx[-1]
            # Price lower low but RSI higher low = bullish divergence
            if (prices.iloc[curr_low_i] < prices.iloc[prev_low_i] and
                    not pd.isna(rsis.iloc[curr_low_i]) and not pd.isna(rsis.iloc[prev_low_i]) and
                    rsis.iloc[curr_low_i] > rsis.iloc[prev_low_i]):
                return "BULLISH"

        # Find two most recent swing highs for bearish divergence
        highs_idx = []
        for i in range(2, len(prices) - 1):
            if prices.iloc[i] > prices.iloc[i-1] and prices.iloc[i] > prices.iloc[i+1]:
                highs_idx.append(i)

        if len(highs_idx) >= 2:
            prev_high_i = highs_idx[-2]
            curr_high_i = highs_idx[-1]
            # Price higher high but RSI lower high = bearish divergence
            if (prices.iloc[curr_high_i] > prices.iloc[prev_high_i] and
                    not pd.isna(rsis.iloc[curr_high_i]) and not pd.isna(rsis.iloc[prev_high_i]) and
                    rsis.iloc[curr_high_i] < rsis.iloc[prev_high_i]):
                return "BEARISH"

        return None
