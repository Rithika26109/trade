"""
Backtest Runner
───────────────
Run backtests on historical data to validate strategies before trading.

Usage:
    python backtest/run_backtest.py                    # Default: ORB strategy
    python backtest/run_backtest.py --strategy RSI_EMA
    python backtest/run_backtest.py --symbol RELIANCE --days 90
"""

import argparse
import sys
from datetime import datetime, timedelta, time as dtime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import pandas_ta as ta
from backtesting import Backtest, Strategy
from backtesting.lib import crossover

from config import settings


# ── Realistic Zerodha Cost Model ──
def zerodha_commission(size, price):
    """
    Compute realistic Zerodha intraday trading costs.

    Includes brokerage, STT, transaction charges, GST, SEBI fees, and stamp duty.
    Returns total cost for the given leg (buy or sell side).
    """
    turnover = abs(size) * price
    brokerage = min(20, turnover * 0.0003)
    stt = turnover * 0.00025  # Sell-side STT approximation
    txn = turnover * 0.0000345
    gst = (brokerage + txn) * 0.18
    sebi = turnover * 0.000001
    stamp = turnover * 0.00003
    return brokerage + stt + txn + gst + sebi + stamp


# ── Intraday square-off helper ──
SQUARE_OFF_TIME = dtime(15, 15)  # Match live STOP_NEW_TRADES / EOD flattening


def _past_square_off(ts) -> bool:
    """True if a timestamp is at/after the intraday square-off clock."""
    try:
        return ts.time() >= SQUARE_OFF_TIME
    except Exception:
        return False


class ORBBacktest(Strategy):
    """Opening Range Breakout backtest — matches live logic (fixed range per day)."""
    orb_period = 3  # Number of candles for opening range (3 × 5min = 15min)
    atr_multiplier = 1.5
    rr_ratio = 2.0

    def init(self):
        self.atr = self.I(
            lambda h, l, c: ta.atr(pd.Series(h), pd.Series(l), pd.Series(c), length=14),
            self.data.High, self.data.Low, self.data.Close
        )
        self._current_day = None
        self._day_candle_count = 0
        self._orb_high = -float('inf')
        self._orb_low = float('inf')
        self._traded_today = False

    def next(self):
        if len(self.data) < self.orb_period + 5:
            return

        # Intraday square-off: flatten at/after 15:15 and do not re-enter.
        if _past_square_off(self.data.index[-1]):
            if self.position:
                self.position.close()
            return

        # Detect new day — compute opening range once per day
        current_date = self.data.index[-1].date() if hasattr(self.data.index[-1], 'date') else None
        if current_date != self._current_day:
            self._current_day = current_date
            self._day_candle_count = 0
            self._orb_high = -float('inf')
            self._orb_low = float('inf')
            self._traded_today = False

        self._day_candle_count += 1

        # Collect opening range for first N candles of the day
        if self._day_candle_count <= self.orb_period:
            self._orb_high = max(self._orb_high, self.data.High[-1])
            self._orb_low = min(self._orb_low, self.data.Low[-1])
            return

        # Skip if already in a position or already traded today
        if self.position or self._traded_today:
            return

        orb_high = self._orb_high
        orb_low = self._orb_low
        current_close = self.data.Close[-1]
        prev_close = self.data.Close[-2]

        atr_val = self.atr[-1]
        if pd.isna(atr_val):
            return

        # Breakout above
        if current_close > orb_high and prev_close <= orb_high:
            stop = orb_low
            risk = current_close - stop
            target = current_close + (risk * self.rr_ratio)
            self.buy(sl=stop, tp=target)
            self._traded_today = True

        # Breakdown below
        elif current_close < orb_low and prev_close >= orb_low:
            stop = orb_high
            risk = stop - current_close
            target = current_close - (risk * self.rr_ratio)
            self.sell(sl=stop, tp=target)
            self._traded_today = True


class RSIEMABacktest(Strategy):
    """RSI + EMA Crossover backtest strategy."""
    ema_fast = 9
    ema_slow = 21
    rsi_period = 14
    atr_multiplier = 1.5
    rr_ratio = 2.0

    def init(self):
        close = pd.Series(self.data.Close)
        self.ema_f = self.I(lambda c: ta.ema(pd.Series(c), length=self.ema_fast), self.data.Close)
        self.ema_s = self.I(lambda c: ta.ema(pd.Series(c), length=self.ema_slow), self.data.Close)
        self.rsi = self.I(lambda c: ta.rsi(pd.Series(c), length=self.rsi_period), self.data.Close)
        self.atr = self.I(
            lambda h, l, c: ta.atr(pd.Series(h), pd.Series(l), pd.Series(c), length=14),
            self.data.High, self.data.Low, self.data.Close
        )

    def next(self):
        if _past_square_off(self.data.index[-1]):
            if self.position:
                self.position.close()
            return
        if self.position:
            return

        if pd.isna(self.rsi[-1]) or pd.isna(self.atr[-1]):
            return

        close = self.data.Close[-1]
        atr_val = self.atr[-1]

        # Buy: EMA bullish crossover + RSI 40-70
        if crossover(self.ema_f, self.ema_s) and 40 <= self.rsi[-1] <= 70:
            stop = close - (self.atr_multiplier * atr_val)
            risk = close - stop
            target = close + (risk * self.rr_ratio)
            self.buy(sl=stop, tp=target)

        # Sell: EMA bearish crossover + RSI 30-60
        elif crossover(self.ema_s, self.ema_f) and 30 <= self.rsi[-1] <= 60:
            stop = close + (self.atr_multiplier * atr_val)
            risk = stop - close
            target = close - (risk * self.rr_ratio)
            self.sell(sl=stop, tp=target)


class VWAPSupertrendBacktest(Strategy):
    """VWAP + Supertrend backtest strategy.

    BUY:  Supertrend flips bullish (direction -1 -> 1 confirmed for 2+ candles)
          AND price is above VWAP.
    SELL: Supertrend flips bearish (direction 1 -> -1 confirmed for 2+ candles)
          AND price is below VWAP.
    Stop-loss: Supertrend line value.
    Target:    entry + risk * 2.0.
    Position sizing based on ATR.
    """
    supertrend_period = 10
    supertrend_multiplier = 3.0
    confirmation_candles = 2
    rr_ratio = 2.0

    def init(self):
        high = pd.Series(self.data.High, index=self.data.index)
        low = pd.Series(self.data.Low, index=self.data.index)
        close = pd.Series(self.data.Close, index=self.data.index)
        volume = pd.Series(self.data.Volume, index=self.data.index)

        # ── Supertrend ──
        st_df = ta.supertrend(
            high, low, close,
            length=self.supertrend_period,
            multiplier=self.supertrend_multiplier,
        )
        # pandas_ta returns a DataFrame with columns like:
        #   SUPERT_{length}_{mult}, SUPERTd_{length}_{mult}, ...
        st_col = [c for c in st_df.columns if c.startswith("SUPERT_")][0]
        sd_col = [c for c in st_df.columns if c.startswith("SUPERTd_")][0]

        self.supertrend = self.I(lambda: st_df[st_col].values, name="Supertrend")
        self.st_direction = self.I(lambda: st_df[sd_col].values, name="ST_Dir")

        # ── VWAP (cumulative, reset daily) ──
        def _daily_vwap(high, low, close, volume):
            h = pd.Series(high)
            l = pd.Series(low)
            c = pd.Series(close)
            v = pd.Series(volume)
            idx = self.data.index

            typical_price = (h + l + c) / 3.0
            tp_vol = typical_price * v

            # Group by date for daily reset
            dates = pd.Series([d.date() if hasattr(d, 'date') else d for d in idx])
            cum_tp_vol = tp_vol.groupby(dates).cumsum()
            cum_vol = v.groupby(dates).cumsum()
            vwap = cum_tp_vol / cum_vol.replace(0, float('nan'))
            return vwap.values

        self.vwap = self.I(
            _daily_vwap,
            self.data.High, self.data.Low, self.data.Close, self.data.Volume,
            name="VWAP",
        )

        # ── ATR for position sizing ──
        self.atr = self.I(
            lambda h, l, c: ta.atr(pd.Series(h), pd.Series(l), pd.Series(c), length=14),
            self.data.High, self.data.Low, self.data.Close,
        )

    def next(self):
        if _past_square_off(self.data.index[-1]):
            if self.position:
                self.position.close()
            return
        if self.position:
            return

        # Need enough history for confirmation window
        if len(self.data) < self.confirmation_candles + 2:
            return

        atr_val = self.atr[-1]
        if pd.isna(atr_val) or pd.isna(self.vwap[-1]) or pd.isna(self.supertrend[-1]):
            return

        close = self.data.Close[-1]
        st_val = self.supertrend[-1]
        vwap_val = self.vwap[-1]

        # Check if Supertrend direction is consistently bullish/bearish
        # for the last `confirmation_candles` bars
        dirs = [self.st_direction[-1 - i] for i in range(self.confirmation_candles)]

        all_bullish = all(d == 1 for d in dirs)
        all_bearish = all(d == -1 for d in dirs)

        # Also check that this is a *flip* — the bar just before the confirmation
        # window was the opposite direction
        prev_idx = self.confirmation_candles
        if prev_idx >= len(self.data):
            return
        prev_dir = self.st_direction[-1 - prev_idx]

        # ── BUY: Supertrend flipped bullish + price above VWAP ──
        if all_bullish and prev_dir == -1 and close > vwap_val:
            stop = st_val
            risk = close - stop
            if risk <= 0:
                return
            target = close + (risk * self.rr_ratio)
            self.buy(sl=stop, tp=target)

        # ── SELL: Supertrend flipped bearish + price below VWAP ──
        elif all_bearish and prev_dir == 1 and close < vwap_val:
            stop = st_val
            risk = stop - close
            if risk <= 0:
                return
            target = close - (risk * self.rr_ratio)
            self.sell(sl=stop, tp=target)


def load_sample_data(symbol: str = "INFY", days: int = 60, allow_synthetic: bool = False) -> pd.DataFrame:
    """
    Load historical data. Tries Zerodha first; synthetic fallback is
    opt-in via `allow_synthetic` to prevent silently tuning strategies
    against random walks (which produce meaningless P&L).
    """
    try:
        from src.auth.login import ZerodhaAuth
        from src.data.market_data import MarketData

        auth = ZerodhaAuth()
        kite = auth.login()
        md = MarketData(kite)
        md.load_instruments("NSE")

        df = md.get_historical_data(symbol, interval="5minute", days=days)
        if not df.empty:
            df = df.rename(columns={
                "date": "Date", "open": "Open", "high": "High",
                "low": "Low", "close": "Close", "volume": "Volume"
            })
            df = df.set_index("Date")
            print(f"Loaded {len(df)} candles from Zerodha for {symbol}")
            return df
    except Exception as e:
        print(f"Could not load from Zerodha: {e}")

    if not allow_synthetic:
        print(
            "ERROR: Real data unavailable and --allow-synthetic was NOT set. "
            "Synthetic random-walk data is NOT representative of the market; "
            "tuning strategies against it will produce false confidence. "
            "Run with --allow-synthetic to explicitly accept this risk."
        )
        return pd.DataFrame()

    # Generate realistic sample data with momentum and intraday patterns
    print("Generating sample data for backtest demo (SYNTHETIC \u2014 use only for smoke-testing)...")
    import numpy as np
    np.random.seed(42)

    dates = pd.date_range(start="2025-06-01", periods=5000, freq="5min")
    # Filter to market hours only (9:15 - 15:30)
    dates = dates[(dates.hour * 60 + dates.minute >= 555) &  # 9:15
                  (dates.hour * 60 + dates.minute <= 930)]   # 15:30

    price = 1500.0
    momentum = 0.0
    data = []
    for dt in dates:
        # Add momentum (auto-correlated returns — like real markets)
        momentum = 0.92 * momentum + np.random.normal(0, 0.4)
        change = momentum + np.random.normal(0, 0.15)
        # Simulate opening gaps on new days
        if dt.hour == 9 and dt.minute == 15:
            change += np.random.normal(0, 3.0)  # Opening gap
        open_p = price
        high_p = price + abs(np.random.normal(0, 1.5))
        low_p = price - abs(np.random.normal(0, 1.5))
        close_p = price + change
        # Volume: higher at open/close, lower midday (U-shape)
        hour_factor = 1.0 + 0.5 * (abs(dt.hour - 12) / 3)
        volume = int(np.random.uniform(50000, 500000) * hour_factor)
        data.append([dt, open_p, max(high_p, close_p, open_p),
                     min(low_p, close_p, open_p), close_p, volume])
        price = close_p

    df = pd.DataFrame(data, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    df = df.set_index("Date")
    print(f"Generated {len(df)} sample candles")
    return df


def main():
    parser = argparse.ArgumentParser(description="Backtest Trading Strategies")
    parser.add_argument("--strategy", default="ORB",
                        choices=["ORB", "RSI_EMA", "VWAP_SUPERTREND"],
                        help="Strategy to backtest")
    parser.add_argument("--symbol", default="INFY", help="Stock symbol")
    parser.add_argument("--days", type=int, default=60, help="Days of historical data")
    parser.add_argument("--capital", type=int, default=100000, help="Starting capital")
    parser.add_argument(
        "--allow-synthetic",
        action="store_true",
        help="Permit synthetic random-walk fallback when real data is unavailable. "
             "Off by default because synthetic data will mislead strategy tuning.",
    )
    args = parser.parse_args()

    # Load data
    df = load_sample_data(args.symbol, args.days, allow_synthetic=args.allow_synthetic)
    if df.empty:
        print("No data available for backtesting")
        return

    # Select strategy
    strategy_map = {
        "ORB": ORBBacktest,
        "RSI_EMA": RSIEMABacktest,
        "VWAP_SUPERTREND": VWAPSupertrendBacktest,
    }
    strategy_class = strategy_map[args.strategy]

    print(f"\nRunning backtest: {args.strategy} on {args.symbol}")
    print(f"Capital: Rs {args.capital:,} | Commission: Zerodha realistic cost model")
    print("=" * 50)

    # Run backtest with realistic Zerodha commission model
    bt = Backtest(
        df, strategy_class,
        cash=args.capital,
        commission=zerodha_commission,
        exclusive_orders=True,
    )
    stats = bt.run()

    # Print results
    print("\n📊 BACKTEST RESULTS")
    print("=" * 50)
    print(f"Return:          {stats['Return [%]']:.2f}%")
    print(f"Sharpe Ratio:    {stats['Sharpe Ratio']:.2f}" if pd.notna(stats['Sharpe Ratio']) else "Sharpe Ratio:    N/A")
    print(f"Max Drawdown:    {stats['Max. Drawdown [%]']:.2f}%")
    print(f"Win Rate:        {stats['Win Rate [%]']:.1f}%")
    print(f"Num Trades:      {stats['# Trades']}")
    print(f"Avg Trade:       {stats['Avg. Trade [%]']:.2f}%")
    print(f"Best Trade:      {stats['Best Trade [%]']:.2f}%")
    print(f"Worst Trade:     {stats['Worst Trade [%]']:.2f}%")
    print("=" * 50)

    # Assessment
    sharpe = stats['Sharpe Ratio'] if pd.notna(stats['Sharpe Ratio']) else 0
    if sharpe > 1.0 and stats['Win Rate [%]'] > 40:
        print("✅ Strategy looks promising! Consider paper trading.")
    elif sharpe > 0.5:
        print("⚠️  Strategy is marginal. Needs optimization.")
    else:
        print("❌ Strategy underperforms. Try different parameters.")

    # Save interactive report
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)
    report_path = results_dir / f"{args.strategy}_{args.symbol}_{datetime.now():%Y%m%d_%H%M}.html"
    bt.plot(filename=str(report_path), open_browser=False)
    print(f"\n📄 Interactive report saved: {report_path}")


if __name__ == "__main__":
    main()
