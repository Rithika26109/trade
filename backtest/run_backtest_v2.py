"""
Backtest Runner v2 — Realistic Strategies
──────────────────────────────────────────
Ports the critical live filters into backtesting.py so results
reflect what the actual live bot would do.

v1 tested naked indicator crossovers → catastrophic results.
v2 adds: ADX filter, VWAP confirmation, volume filter, time-of-day
filter, range-size filter, daily trade limits, wider stops (2.0x ATR).

Usage:
    python backtest/run_backtest_v2.py                            # Default: ORB
    python backtest/run_backtest_v2.py --strategy RSI_EMA
    python backtest/run_backtest_v2.py --strategy VWAP_SUPERTREND --symbol RELIANCE
    python backtest/run_backtest_v2.py --compare                  # Run v2 on all, print v1 vs v2
"""

import argparse
import sys
from datetime import datetime, timedelta, time as dtime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import pandas_ta as ta
from backtesting import Backtest, Strategy
from backtesting.lib import crossover

from config import settings

# Import v1 data loader
from backtest.run_backtest import (
    load_sample_data,
    zerodha_commission,
    zerodha_commission_with_slippage,
)

# ── Time-of-day filter ──
TRADE_START = dtime(9, 30)
TRADE_END = dtime(14, 30)
SQUARE_OFF_TIME = dtime(15, 15)


def _in_trading_window(ts) -> bool:
    """True if timestamp is within the safe trading window (9:30 - 14:30)."""
    try:
        t = ts.time()
        return TRADE_START <= t <= TRADE_END
    except Exception:
        return True  # If no time info, allow trading


def _past_square_off(ts) -> bool:
    """True if at/after intraday square-off time."""
    try:
        return ts.time() >= SQUARE_OFF_TIME
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════
# ORB v2 — with range-size filter, volume, ADX, time-of-day
# ═══════════════════════════════════════════════════════════════════

class ORBv2(Strategy):
    """Opening Range Breakout — realistic version with trailing stop + time-decay."""
    orb_period = 3          # 3 × 5min = 15min opening range
    atr_multiplier = 2.0    # 2x ATR stop
    rr_ratio = 2.0          # 2x risk TP (best for most stocks)
    adx_min = 20            # Reject trades in ranging markets
    range_min_pct = 0.3     # Skip if ORB range < 0.3%
    range_max_pct = 3.0     # Skip if ORB range > 3.0%
    vol_multiplier = 1.5    # Breakout volume must be >= 1.5x average

    def init(self):
        self.atr = self.I(
            lambda h, l, c: ta.atr(pd.Series(h), pd.Series(l), pd.Series(c), length=14),
            self.data.High, self.data.Low, self.data.Close,
        )
        # ADX
        def _adx(h, l, c):
            adx_df = ta.adx(pd.Series(h), pd.Series(l), pd.Series(c), length=14)
            return adx_df.iloc[:, 0].values  # ADX column
        self.adx = self.I(_adx, self.data.High, self.data.Low, self.data.Close)

        # Rolling volume average (20-period)
        self.avg_vol = self.I(
            lambda v: pd.Series(v).rolling(20, min_periods=5).mean().values,
            self.data.Volume,
        )

        # Per-day tracking
        self._current_day = None
        self._day_candle_count = 0
        self._orb_high = -float('inf')
        self._orb_low = float('inf')
        self._orb_open = 0
        self._traded_today = False
        # Trailing stop state
        self._entry_price = 0.0
        self._entry_atr = 0.0
        self._trailing_sl = 0.0
        self._is_long = True

    def next(self):
        if len(self.data) < self.orb_period + 5:
            return

        # Square-off
        if _past_square_off(self.data.index[-1]):
            if self.position:
                self.position.close()
            return

        # ── 4-level trailing stop + time-decay for open positions ──
        if self.position:
            close = self.data.Close[-1]
            atr_val = self.atr[-1]

            try:
                t = self.data.index[-1].time()
                mid_session = t >= dtime(13, 0)
                late_session = t >= dtime(14, 30)
            except Exception:
                mid_session = False
                late_session = False

            ea = self._entry_atr  # locked at entry
            ep = self._entry_price

            if self._is_long:
                profit = close - ep
                # Trail: breakeven at 1x ATR, lock profit above that
                if profit >= 2.0 * ea:
                    self._trailing_sl = max(self._trailing_sl, ep + 1.0 * ea)
                elif profit >= 1.5 * ea:
                    self._trailing_sl = max(self._trailing_sl, ep + 0.5 * ea)
                elif profit >= 1.0 * ea:
                    self._trailing_sl = max(self._trailing_sl, ep)  # breakeven
                # Time-decay: tighten in afternoon
                if not pd.isna(atr_val):
                    if late_session:
                        time_sl = close - (1.0 * atr_val)
                        self._trailing_sl = max(self._trailing_sl, time_sl)
                    elif mid_session:
                        time_sl = close - (1.5 * atr_val)
                        self._trailing_sl = max(self._trailing_sl, time_sl)
                if close <= self._trailing_sl:
                    self.position.close()
            else:
                profit = ep - close
                if profit >= 2.0 * ea:
                    self._trailing_sl = min(self._trailing_sl, ep - 1.0 * ea)
                elif profit >= 1.5 * ea:
                    self._trailing_sl = min(self._trailing_sl, ep - 0.5 * ea)
                elif profit >= 1.0 * ea:
                    self._trailing_sl = min(self._trailing_sl, ep)  # breakeven
                if not pd.isna(atr_val):
                    if late_session:
                        time_sl = close + (1.0 * atr_val)
                        self._trailing_sl = min(self._trailing_sl, time_sl)
                    elif mid_session:
                        time_sl = close + (1.5 * atr_val)
                        self._trailing_sl = min(self._trailing_sl, time_sl)
                if close >= self._trailing_sl:
                    self.position.close()
            return

        # New day detection
        current_date = self.data.index[-1].date() if hasattr(self.data.index[-1], 'date') else None
        if current_date != self._current_day:
            self._current_day = current_date
            self._day_candle_count = 0
            self._orb_high = -float('inf')
            self._orb_low = float('inf')
            self._orb_open = self.data.Open[-1]
            self._traded_today = False

        self._day_candle_count += 1

        # Collect opening range
        if self._day_candle_count <= self.orb_period:
            self._orb_high = max(self._orb_high, self.data.High[-1])
            self._orb_low = min(self._orb_low, self.data.Low[-1])
            return

        # Skip if already traded
        if self._traded_today:
            return

        # ── Time-of-day filter ──
        if not _in_trading_window(self.data.index[-1]):
            return

        orb_high = self._orb_high
        orb_low = self._orb_low
        range_size = orb_high - orb_low

        # ── Range size filter ──
        if self._orb_open > 0 and range_size > 0:
            range_pct = (range_size / self._orb_open) * 100
            if range_pct < self.range_min_pct or range_pct > self.range_max_pct:
                return

        # ── ADX filter ──
        adx_val = self.adx[-1]
        if not pd.isna(adx_val) and adx_val < self.adx_min:
            return

        # ── Volume filter ──
        current_vol = self.data.Volume[-1]
        avg_vol = self.avg_vol[-1]
        if not pd.isna(avg_vol) and avg_vol > 0:
            if current_vol < avg_vol * self.vol_multiplier:
                return

        current_close = self.data.Close[-1]
        prev_close = self.data.Close[-2]
        atr_val = self.atr[-1]
        if pd.isna(atr_val):
            return

        # Breakout above
        if current_close > orb_high and prev_close <= orb_high:
            stop = max(current_close - (self.atr_multiplier * atr_val), orb_low)
            risk = current_close - stop
            if risk <= 0:
                return
            target = current_close + (risk * self.rr_ratio)
            self._entry_price = current_close
            self._entry_atr = atr_val
            self._trailing_sl = stop
            self._is_long = True
            self.buy(tp=target)  # TP + trailing stop manages exits
            self._traded_today = True

        # Breakdown below
        elif current_close < orb_low and prev_close >= orb_low:
            stop = min(current_close + (self.atr_multiplier * atr_val), orb_high)
            risk = stop - current_close
            if risk <= 0:
                return
            target = current_close - (risk * self.rr_ratio)
            self._entry_price = current_close
            self._entry_atr = atr_val
            self._trailing_sl = stop
            self._is_long = False
            self.sell(tp=target)  # TP + trailing stop manages exits
            self._traded_today = True


# ═══════════════════════════════════════════════════════════════════
# RSI + EMA v2 — with ADX filter, VWAP confirmation, wider ranges
# ═══════════════════════════════════════════════════════════════════

class RSIEMAv2(Strategy):
    """RSI + EMA Crossover — realistic version matching live filters.

    v3 changes (bug-fix alignment):
    - Added RSI divergence detection (matches live strategy)
    - Trailing stop: move SL to breakeven at 1×ATR profit, then trail
    - Time-decay exit: tighten stop to 1×ATR after 14:30
    - Removed alignment_buy/sell (whipsaw trap)
    """
    ema_fast = 9
    ema_slow = 21
    rsi_period = 14
    atr_multiplier = 2.0    # Match live (was 1.5)
    rr_ratio = 2.0
    adx_min = 20            # Reject ranging markets (live uses 15, we use 20 for safety)
    rsi_buy_min = 30        # Match live settings
    rsi_buy_max = 55
    rsi_sell_min = 45
    rsi_sell_max = 70

    def init(self):
        self.ema_f = self.I(lambda c: ta.ema(pd.Series(c), length=self.ema_fast), self.data.Close)
        self.ema_s = self.I(lambda c: ta.ema(pd.Series(c), length=self.ema_slow), self.data.Close)
        self.rsi = self.I(lambda c: ta.rsi(pd.Series(c), length=self.rsi_period), self.data.Close)
        self.atr = self.I(
            lambda h, l, c: ta.atr(pd.Series(h), pd.Series(l), pd.Series(c), length=14),
            self.data.High, self.data.Low, self.data.Close,
        )
        # ADX
        def _adx(h, l, c):
            adx_df = ta.adx(pd.Series(h), pd.Series(l), pd.Series(c), length=14)
            return adx_df.iloc[:, 0].values
        self.adx = self.I(_adx, self.data.High, self.data.Low, self.data.Close)

        # Daily VWAP
        def _daily_vwap(h, l, c, v):
            tp = (pd.Series(h) + pd.Series(l) + pd.Series(c)) / 3.0
            tp_vol = tp * pd.Series(v)
            idx = self.data.index
            dates = pd.Series([d.date() if hasattr(d, 'date') else d for d in idx])
            cum_tp_vol = tp_vol.groupby(dates).cumsum()
            cum_vol = pd.Series(v).groupby(dates).cumsum()
            vwap = cum_tp_vol / cum_vol.replace(0, float('nan'))
            return vwap.values
        self.vwap = self.I(
            _daily_vwap,
            self.data.High, self.data.Low, self.data.Close, self.data.Volume,
        )

        # Rolling volume average
        self.avg_vol = self.I(
            lambda v: pd.Series(v).rolling(20, min_periods=5).mean().values,
            self.data.Volume,
        )

        # Daily trade tracking
        self._current_day = None
        self._traded_today = False
        # Trailing stop state
        self._entry_price = 0.0
        self._entry_atr = 0.0
        self._trailing_sl = 0.0
        self._is_long = True

    def _detect_rsi_divergence(self) -> str | None:
        """Detect RSI divergence — mirrors live RSIEMAStrategy logic."""
        if len(self.data) < 12:
            return None
        lookback = min(20, len(self.data))
        prices = list(self.data.Close[-lookback:])
        rsis = list(self.rsi[-lookback:])
        if sum(1 for r in rsis if pd.isna(r)) > lookback * 0.3:
            return None

        # Bullish divergence: price lower low, RSI higher low
        lows_idx = []
        for i in range(2, len(prices) - 1):
            if prices[i] < prices[i-1] and prices[i] < prices[i+1]:
                lows_idx.append(i)
        if len(lows_idx) >= 2:
            prev_i, curr_i = lows_idx[-2], lows_idx[-1]
            if (prices[curr_i] < prices[prev_i]
                    and not pd.isna(rsis[curr_i]) and not pd.isna(rsis[prev_i])
                    and rsis[curr_i] > rsis[prev_i]):
                return "BULLISH"

        # Bearish divergence: price higher high, RSI lower high
        highs_idx = []
        for i in range(2, len(prices) - 1):
            if prices[i] > prices[i-1] and prices[i] < prices[i+1]:
                highs_idx.append(i)
        if len(highs_idx) >= 2:
            prev_i, curr_i = highs_idx[-2], highs_idx[-1]
            if (prices[curr_i] > prices[prev_i]
                    and not pd.isna(rsis[curr_i]) and not pd.isna(rsis[prev_i])
                    and rsis[curr_i] < rsis[prev_i]):
                return "BEARISH"
        return None

    def next(self):
        # Square-off
        if _past_square_off(self.data.index[-1]):
            if self.position:
                self.position.close()
            return

        # ── Trailing stop + time-decay management for open positions ──
        if self.position:
            close = self.data.Close[-1]
            atr_val = self.atr[-1]

            # Time-decay: tighten stop after 14:30
            try:
                t = self.data.index[-1].time()
                late_session = t >= dtime(14, 30)
            except Exception:
                late_session = False

            if self._is_long:
                profit = close - self._entry_price
                # Trail stop: at 1×ATR profit → breakeven; at 1.5×ATR → lock 0.5×ATR
                if profit >= 1.5 * self._entry_atr:
                    new_sl = self._entry_price + 0.5 * self._entry_atr
                    self._trailing_sl = max(self._trailing_sl, new_sl)
                elif profit >= 1.0 * self._entry_atr:
                    self._trailing_sl = max(self._trailing_sl, self._entry_price)

                # Time-decay: tighten to 1×ATR stop if after 14:30
                if late_session and not pd.isna(atr_val):
                    time_sl = close - (1.0 * atr_val)
                    self._trailing_sl = max(self._trailing_sl, time_sl)

                if close <= self._trailing_sl:
                    self.position.close()
            else:
                profit = self._entry_price - close
                if profit >= 1.5 * self._entry_atr:
                    new_sl = self._entry_price - 0.5 * self._entry_atr
                    self._trailing_sl = min(self._trailing_sl, new_sl)
                elif profit >= 1.0 * self._entry_atr:
                    self._trailing_sl = min(self._trailing_sl, self._entry_price)

                if late_session and not pd.isna(atr_val):
                    time_sl = close + (1.0 * atr_val)
                    self._trailing_sl = min(self._trailing_sl, time_sl)

                if close >= self._trailing_sl:
                    self.position.close()
            return

        # ── Time-of-day filter ──
        if not _in_trading_window(self.data.index[-1]):
            return

        # ── Daily trade limit: 1 trade per day ──
        current_date = self.data.index[-1].date() if hasattr(self.data.index[-1], 'date') else None
        if current_date != self._current_day:
            self._current_day = current_date
            self._traded_today = False
        if self._traded_today:
            return

        if pd.isna(self.rsi[-1]) or pd.isna(self.atr[-1]):
            return

        # ── ADX filter — reject ranging markets ──
        adx_val = self.adx[-1]
        if not pd.isna(adx_val) and adx_val < self.adx_min:
            return

        # ── Volume filter ──
        current_vol = self.data.Volume[-1]
        avg_vol = self.avg_vol[-1]
        if not pd.isna(avg_vol) and avg_vol > 0:
            if current_vol < avg_vol * 1.2:
                return

        close = self.data.Close[-1]
        atr_val = self.atr[-1]
        rsi_val = self.rsi[-1]
        vwap_val = self.vwap[-1]

        # ── Check for RSI divergence (matches live strategy) ──
        divergence = self._detect_rsi_divergence()

        # ── BUY: EMA bullish crossover OR bullish divergence ──
        buy_signal = crossover(self.ema_f, self.ema_s) or divergence == "BULLISH"
        if buy_signal:
            rsi_ok = self.rsi_buy_min <= rsi_val <= self.rsi_buy_max
            # Divergence overrides strict RSI range
            if divergence == "BULLISH" and not rsi_ok:
                rsi_ok = rsi_val < 60
            vwap_ok = (close > vwap_val) if not pd.isna(vwap_val) else True

            if rsi_ok and vwap_ok:
                stop = close - (self.atr_multiplier * atr_val)
                risk = close - stop
                target = close + (risk * self.rr_ratio)
                self._entry_price = close
                self._entry_atr = atr_val
                self._trailing_sl = stop
                self._is_long = True
                self.buy(tp=target)  # SL managed by trailing logic
                self._traded_today = True
                return

        # ── SELL: EMA bearish crossover OR bearish divergence ──
        sell_signal = crossover(self.ema_s, self.ema_f) or divergence == "BEARISH"
        if sell_signal:
            rsi_ok = self.rsi_sell_min <= rsi_val <= self.rsi_sell_max
            if divergence == "BEARISH" and not rsi_ok:
                rsi_ok = rsi_val > 40
            vwap_ok = (close < vwap_val) if not pd.isna(vwap_val) else True

            # Never short when RSI < 30 (oversold protection)
            if rsi_val < 30:
                return

            if rsi_ok and vwap_ok:
                stop = close + (self.atr_multiplier * atr_val)
                risk = stop - close
                target = close - (risk * self.rr_ratio)
                self._entry_price = close
                self._entry_atr = atr_val
                self._trailing_sl = stop
                self._is_long = False
                self.sell(tp=target)  # SL managed by trailing logic
                self._traded_today = True
                return


# ═══════════════════════════════════════════════════════════════════
# VWAP + Supertrend v2 — with distance filter, ADX, volume weight
# ═══════════════════════════════════════════════════════════════════

class VWAPSupertrendv2(Strategy):
    """VWAP + Supertrend — realistic version with trailing stop + time-decay."""
    supertrend_period = 10
    supertrend_multiplier = 3.0
    confirmation_candles = 3    # Increased from 2 (more conservative)
    rr_ratio = 2.0
    adx_min = 20               # Reject ranging markets
    vwap_max_distance_pct = 1.5  # Reject if price > 1.5% from VWAP

    def init(self):
        high = pd.Series(self.data.High, index=self.data.index)
        low = pd.Series(self.data.Low, index=self.data.index)
        close = pd.Series(self.data.Close, index=self.data.index)
        volume = pd.Series(self.data.Volume, index=self.data.index)

        # Supertrend
        st_df = ta.supertrend(
            high, low, close,
            length=self.supertrend_period,
            multiplier=self.supertrend_multiplier,
        )
        st_col = [c for c in st_df.columns if c.startswith("SUPERT_")][0]
        sd_col = [c for c in st_df.columns if c.startswith("SUPERTd_")][0]
        self.supertrend = self.I(lambda: st_df[st_col].values, name="Supertrend")
        self.st_direction = self.I(lambda: st_df[sd_col].values, name="ST_Dir")

        # Daily VWAP
        def _daily_vwap(h, l, c, v):
            tp = (pd.Series(h) + pd.Series(l) + pd.Series(c)) / 3.0
            tp_vol = tp * pd.Series(v)
            idx = self.data.index
            dates = pd.Series([d.date() if hasattr(d, 'date') else d for d in idx])
            cum_tp_vol = tp_vol.groupby(dates).cumsum()
            cum_vol = pd.Series(v).groupby(dates).cumsum()
            vwap = cum_tp_vol / cum_vol.replace(0, float('nan'))
            return vwap.values
        self.vwap = self.I(
            _daily_vwap,
            self.data.High, self.data.Low, self.data.Close, self.data.Volume,
            name="VWAP",
        )

        # ATR
        self.atr = self.I(
            lambda h, l, c: ta.atr(pd.Series(h), pd.Series(l), pd.Series(c), length=14),
            self.data.High, self.data.Low, self.data.Close,
        )

        # ADX
        def _adx(h, l, c):
            adx_df = ta.adx(pd.Series(h), pd.Series(l), pd.Series(c), length=14)
            return adx_df.iloc[:, 0].values
        self.adx = self.I(_adx, self.data.High, self.data.Low, self.data.Close)

        # Rolling volume average
        self.avg_vol = self.I(
            lambda v: pd.Series(v).rolling(20, min_periods=5).mean().values,
            self.data.Volume,
        )

        # Daily trade tracking
        self._current_day = None
        self._traded_today = False
        # Trailing stop state
        self._entry_price = 0.0
        self._entry_atr = 0.0
        self._trailing_sl = 0.0
        self._is_long = True

    def next(self):
        # Square-off
        if _past_square_off(self.data.index[-1]):
            if self.position:
                self.position.close()
            return

        # ── Trailing stop + time-decay for open positions ──
        if self.position:
            close = self.data.Close[-1]
            atr_val = self.atr[-1]

            try:
                t = self.data.index[-1].time()
                late_session = t >= dtime(14, 30)
            except Exception:
                late_session = False

            if self._is_long:
                profit = close - self._entry_price
                if profit >= 1.5 * self._entry_atr:
                    new_sl = self._entry_price + 0.5 * self._entry_atr
                    self._trailing_sl = max(self._trailing_sl, new_sl)
                elif profit >= 1.0 * self._entry_atr:
                    self._trailing_sl = max(self._trailing_sl, self._entry_price)
                if late_session and not pd.isna(atr_val):
                    time_sl = close - (1.0 * atr_val)
                    self._trailing_sl = max(self._trailing_sl, time_sl)
                if close <= self._trailing_sl:
                    self.position.close()
            else:
                profit = self._entry_price - close
                if profit >= 1.5 * self._entry_atr:
                    new_sl = self._entry_price - 0.5 * self._entry_atr
                    self._trailing_sl = min(self._trailing_sl, new_sl)
                elif profit >= 1.0 * self._entry_atr:
                    self._trailing_sl = min(self._trailing_sl, self._entry_price)
                if late_session and not pd.isna(atr_val):
                    time_sl = close + (1.0 * atr_val)
                    self._trailing_sl = min(self._trailing_sl, time_sl)
                if close >= self._trailing_sl:
                    self.position.close()
            return

        # ── Time-of-day filter ──
        if not _in_trading_window(self.data.index[-1]):
            return

        # ── Daily trade limit ──
        current_date = self.data.index[-1].date() if hasattr(self.data.index[-1], 'date') else None
        if current_date != self._current_day:
            self._current_day = current_date
            self._traded_today = False
        if self._traded_today:
            return

        if len(self.data) < self.confirmation_candles + 3:
            return

        atr_val = self.atr[-1]
        vwap_val = self.vwap[-1]
        st_val = self.supertrend[-1]
        close = self.data.Close[-1]

        if any(pd.isna(v) for v in [atr_val, vwap_val, st_val]):
            return

        # ── ADX filter ──
        adx_val = self.adx[-1]
        if not pd.isna(adx_val) and adx_val < self.adx_min:
            return

        # ── VWAP distance filter ──
        vwap_dist_pct = abs(close - vwap_val) / vwap_val * 100 if vwap_val > 0 else 0
        if vwap_dist_pct > self.vwap_max_distance_pct:
            return

        # ── Volume filter ──
        current_vol = self.data.Volume[-1]
        avg_vol = self.avg_vol[-1]
        if not pd.isna(avg_vol) and avg_vol > 0:
            if current_vol < avg_vol * 1.2:
                return

        # Check Supertrend flip with confirmation
        dirs = [self.st_direction[-1 - i] for i in range(self.confirmation_candles)]
        all_bullish = all(d == 1 for d in dirs)
        all_bearish = all(d == -1 for d in dirs)

        prev_idx = self.confirmation_candles
        if prev_idx >= len(self.data):
            return
        prev_dir = self.st_direction[-1 - prev_idx]

        # ── BUY: ST flipped bullish + above VWAP ──
        if all_bullish and prev_dir == -1 and close > vwap_val:
            stop = st_val
            risk = close - stop
            if risk <= 0:
                return
            target = close + (risk * self.rr_ratio)
            self._entry_price = close
            self._entry_atr = atr_val
            self._trailing_sl = stop
            self._is_long = True
            self.buy(tp=target)  # SL managed by trailing logic
            self._traded_today = True

        # ── SELL: ST flipped bearish + below VWAP ──
        elif all_bearish and prev_dir == 1 and close < vwap_val:
            stop = st_val
            risk = stop - close
            if risk <= 0:
                return
            target = close - (risk * self.rr_ratio)
            self._entry_price = close
            self._entry_atr = atr_val
            self._trailing_sl = stop
            self._is_long = False
            self.sell(tp=target)  # SL managed by trailing logic
            self._traded_today = True


# ═══════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════

STRATEGY_MAP = {
    "ORB": ORBv2,
    "RSI_EMA": RSIEMAv2,
    "VWAP_SUPERTREND": VWAPSupertrendv2,
}


def run_single(strategy_name: str, symbol: str, days: int, capital: int) -> dict:
    """Run a single backtest and return stats dict."""
    df = load_sample_data(symbol, days)
    if df.empty:
        print(f"No data for {symbol}")
        return {}

    strategy_class = STRATEGY_MAP[strategy_name]
    bt = Backtest(
        df, strategy_class,
        cash=capital,
        commission=zerodha_commission,
        exclusive_orders=True,
    )
    stats = bt.run()

    result = {
        "strategy": strategy_name,
        "symbol": symbol,
        "return_pct": stats["Return [%]"],
        "sharpe": stats["Sharpe Ratio"] if pd.notna(stats["Sharpe Ratio"]) else 0,
        "max_dd_pct": stats["Max. Drawdown [%]"],
        "win_rate_pct": stats["Win Rate [%]"],
        "num_trades": stats["# Trades"],
        "profit_factor": stats.get("Profit Factor", 0),
        "avg_trade_pct": stats["Avg. Trade [%]"],
        "best_trade_pct": stats["Best Trade [%]"],
        "worst_trade_pct": stats["Worst Trade [%]"],
    }

    # Save interactive report
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)
    report_path = results_dir / f"v2_{strategy_name}_{symbol}.html"
    bt.plot(filename=str(report_path), open_browser=False)

    return result


def load_v1_results() -> pd.DataFrame:
    """Load v1 baseline results for comparison."""
    csv_path = Path(__file__).parent / "results" / "baseline_summary.csv"
    if csv_path.exists():
        return pd.read_csv(csv_path)
    return pd.DataFrame()


def print_comparison(v2_results: list[dict], v1_df: pd.DataFrame):
    """Print side-by-side v1 vs v2 comparison."""
    print("\n" + "=" * 90)
    print("v1 (NAIVE) vs v2 (REALISTIC) COMPARISON")
    print("=" * 90)
    print(f"{'Strategy':<16} {'Symbol':<12} {'v1 Ret%':>8} {'v2 Ret%':>8} {'v1 WR%':>7} {'v2 WR%':>7} {'v1 #T':>6} {'v2 #T':>6} {'v1 Sharpe':>10} {'v2 Sharpe':>10}")
    print("-" * 90)

    for r in v2_results:
        v1_row = v1_df[(v1_df["strategy"] == r["strategy"]) & (v1_df["symbol"] == r["symbol"])]
        if v1_row.empty:
            continue
        v1 = v1_row.iloc[0]
        print(
            f"{r['strategy']:<16} {r['symbol']:<12} "
            f"{v1['return_pct']:>7.1f}% {r['return_pct']:>7.1f}% "
            f"{v1['win_rate_pct']:>6.1f}% {r['win_rate_pct']:>6.1f}% "
            f"{int(v1['num_trades']):>5} {r['num_trades']:>5} "
            f"{v1['sharpe']:>9.2f} {r['sharpe']:>9.2f}"
        )

    # Averages
    if v2_results:
        print("-" * 90)
        for strat in STRATEGY_MAP:
            strat_v2 = [r for r in v2_results if r["strategy"] == strat and r["num_trades"] > 0]
            strat_v1 = v1_df[v1_df["strategy"] == strat]
            if strat_v2 and not strat_v1.empty:
                avg_v2_ret = np.mean([r["return_pct"] for r in strat_v2])
                avg_v1_ret = strat_v1["return_pct"].mean()
                avg_v2_wr = np.mean([r["win_rate_pct"] for r in strat_v2])
                avg_v1_wr = strat_v1["win_rate_pct"].mean()
                avg_v2_trades = np.mean([r["num_trades"] for r in strat_v2])
                avg_v1_trades = strat_v1["num_trades"].mean()
                avg_v2_sharpe = np.mean([r["sharpe"] for r in strat_v2])
                avg_v1_sharpe = strat_v1["sharpe"].mean()
                print(
                    f"{strat + ' AVG':<16} {'':12} "
                    f"{avg_v1_ret:>7.1f}% {avg_v2_ret:>7.1f}% "
                    f"{avg_v1_wr:>6.1f}% {avg_v2_wr:>6.1f}% "
                    f"{int(avg_v1_trades):>5} {int(avg_v2_trades):>5} "
                    f"{avg_v1_sharpe:>9.2f} {avg_v2_sharpe:>9.2f}"
                )


def main():
    parser = argparse.ArgumentParser(description="Backtest v2 — Realistic Strategies")
    parser.add_argument("--strategy", default="ORB",
                        choices=list(STRATEGY_MAP.keys()),
                        help="Strategy to backtest")
    parser.add_argument("--symbol", default="RELIANCE", help="Stock symbol")
    parser.add_argument("--days", type=int, default=730, help="Days of historical data")
    parser.add_argument("--capital", type=int, default=100000, help="Starting capital")
    parser.add_argument("--compare", action="store_true",
                        help="Run all strategies on all stocks and compare v1 vs v2")
    args = parser.parse_args()

    if args.compare:
        # Full comparison run
        symbols = settings.WATCHLIST
        strategies = list(STRATEGY_MAP.keys())
        all_results = []

        for strat in strategies:
            for sym in symbols:
                print(f"\nRunning v2: {strat} on {sym}...")
                result = run_single(strat, sym, args.days, args.capital)
                if result:
                    all_results.append(result)
                    print(
                        f"  Return: {result['return_pct']:.1f}% | "
                        f"Win Rate: {result['win_rate_pct']:.1f}% | "
                        f"Trades: {result['num_trades']} | "
                        f"Sharpe: {result['sharpe']:.2f}"
                    )

        # Save v2 summary
        results_dir = Path(__file__).parent / "results"
        v2_df = pd.DataFrame(all_results)
        v2_df.to_csv(results_dir / "v2_summary.csv", index=False)
        print(f"\nv2 summary saved to {results_dir / 'v2_summary.csv'}")

        # Compare with v1
        v1_df = load_v1_results()
        if not v1_df.empty:
            print_comparison(all_results, v1_df)
        return

    # Single run
    print(f"\n{'=' * 50}")
    print(f"BACKTEST v2 (Realistic): {args.strategy} on {args.symbol}")
    print(f"Capital: Rs {args.capital:,} | Filters: ADX, VWAP, Volume, Time")
    print(f"{'=' * 50}")

    result = run_single(args.strategy, args.symbol, args.days, args.capital)
    if not result:
        return

    print(f"\nRETURN:       {result['return_pct']:.2f}%")
    print(f"SHARPE:       {result['sharpe']:.2f}")
    print(f"MAX DRAWDOWN: {result['max_dd_pct']:.2f}%")
    print(f"WIN RATE:     {result['win_rate_pct']:.1f}%")
    print(f"TRADES:       {result['num_trades']}")
    print(f"AVG TRADE:    {result['avg_trade_pct']:.2f}%")
    print(f"BEST TRADE:   {result['best_trade_pct']:.2f}%")
    print(f"WORST TRADE:  {result['worst_trade_pct']:.2f}%")
    sharpe = result["sharpe"]
    if sharpe > 1.0 and result["win_rate_pct"] > 40:
        print("VERDICT: Strategy looks promising!")
    elif sharpe > 0.5:
        print("VERDICT: Marginal — needs work")
    elif result["num_trades"] < 10:
        print("VERDICT: Too few trades — filters may be too aggressive")
    else:
        print("VERDICT: Still underperforming")

    # Compare with v1 if available
    v1_df = load_v1_results()
    if not v1_df.empty:
        v1_row = v1_df[
            (v1_df["strategy"] == args.strategy) & (v1_df["symbol"] == args.symbol)
        ]
        if not v1_row.empty:
            v1 = v1_row.iloc[0]
            print(f"\nv1 COMPARISON:")
            print(f"  Return:   {v1['return_pct']:.1f}% -> {result['return_pct']:.1f}%")
            print(f"  Win Rate: {v1['win_rate_pct']:.1f}% -> {result['win_rate_pct']:.1f}%")
            print(f"  Trades:   {int(v1['num_trades'])} -> {result['num_trades']}")
            print(f"  Sharpe:   {v1['sharpe']:.2f} -> {result['sharpe']:.2f}")


if __name__ == "__main__":
    main()
