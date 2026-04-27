"""
Walk-Forward Analysis
─────────────────────
Split historical data into rolling train/test windows and compare
in-sample vs out-of-sample performance to detect overfitting.

Usage:
    python backtest/walk_forward.py                              # Defaults
    python backtest/walk_forward.py --strategy RSI_EMA --days 120
    python backtest/walk_forward.py --symbol RELIANCE --strategy ORB --days 90
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from backtesting import Backtest

from backtest.run_backtest import (
    load_sample_data,
    zerodha_commission,
)
from backtest.run_backtest_v2 import ORBv2, RSIEMAv2, VWAPSupertrendv2
from backtest.run_backtest import zerodha_commission_with_slippage


# ── Strategy lookup ──
STRATEGY_MAP = {
    "ORB": ORBv2,
    "RSI_EMA": RSIEMAv2,
    "VWAP_SUPERTREND": VWAPSupertrendv2,
}

# ── Window Configuration ──
TRAIN_DAYS = 30
TEST_DAYS = 10
SLIDE_DAYS = 10  # How many days to slide the window forward each step


def _extract_metrics(stats) -> dict:
    """Pull key metrics from a backtesting.py stats object."""
    sharpe = stats["Sharpe Ratio"] if pd.notna(stats["Sharpe Ratio"]) else 0.0
    return {
        "Return [%]": round(stats["Return [%]"], 2),
        "Sharpe": round(sharpe, 2),
        "Max DD [%]": round(stats["Max. Drawdown [%]"], 2),
        "# Trades": stats["# Trades"],
        "Win Rate [%]": round(stats["Win Rate [%]"], 1) if stats["# Trades"] > 0 else 0.0,
    }


def _date_groups(df: pd.DataFrame) -> list:
    """Return sorted unique dates present in the index."""
    return sorted(set(d.date() for d in df.index))


def walk_forward(df: pd.DataFrame, strategy_class, capital: int = 100_000, commission_func=None):
    """
    Run walk-forward analysis.

    Splits data into rolling windows of TRAIN_DAYS + TEST_DAYS, sliding by
    SLIDE_DAYS.  For each window the strategy runs on training data (in-sample)
    and then on test data (out-of-sample) using the same default parameters.

    Returns a list of dicts with in-sample and out-of-sample metrics per window.
    """
    if commission_func is None:
        commission_func = zerodha_commission_with_slippage
    unique_dates = _date_groups(df)
    total_days = len(unique_dates)
    window_size = TRAIN_DAYS + TEST_DAYS

    if total_days < window_size:
        print(f"Not enough data: have {total_days} trading days, need at least {window_size}")
        return []

    results = []
    window_num = 0
    start = 0

    while start + window_size <= total_days:
        train_start_date = unique_dates[start]
        train_end_date = unique_dates[start + TRAIN_DAYS - 1]
        test_start_date = unique_dates[start + TRAIN_DAYS]
        test_end_date = unique_dates[min(start + window_size - 1, total_days - 1)]

        # Slice dataframes using date boundaries
        train_df = df[(df.index.date >= train_start_date) & (df.index.date <= train_end_date)]
        test_df = df[(df.index.date >= test_start_date) & (df.index.date <= test_end_date)]

        if len(train_df) < 50 or len(test_df) < 20:
            # Not enough candles for a meaningful backtest
            start += SLIDE_DAYS
            continue

        window_num += 1
        row = {
            "Window": window_num,
            "Train": f"{train_start_date} -> {train_end_date}",
            "Test": f"{test_start_date} -> {test_end_date}",
        }

        # ── In-sample (training) ──
        try:
            bt_train = Backtest(
                train_df, strategy_class,
                cash=capital,
                commission=commission_func,
                exclusive_orders=True,
            )
            train_stats = bt_train.run()
            is_metrics = _extract_metrics(train_stats)
            for k, v in is_metrics.items():
                row[f"IS {k}"] = v
        except Exception as e:
            print(f"  [Window {window_num}] Train error: {e}")
            for k in ["Return [%]", "Sharpe", "Max DD [%]", "# Trades", "Win Rate [%]"]:
                row[f"IS {k}"] = "ERR"

        # ── Out-of-sample (test) ──
        try:
            bt_test = Backtest(
                test_df, strategy_class,
                cash=capital,
                commission=commission_func,
                exclusive_orders=True,
            )
            test_stats = bt_test.run()
            oos_metrics = _extract_metrics(test_stats)
            for k, v in oos_metrics.items():
                row[f"OOS {k}"] = v
        except Exception as e:
            print(f"  [Window {window_num}] Test error: {e}")
            for k in ["Return [%]", "Sharpe", "Max DD [%]", "# Trades", "Win Rate [%]"]:
                row[f"OOS {k}"] = "ERR"

        results.append(row)
        start += SLIDE_DAYS

    return results


def print_results(results: list, strategy_name: str):
    """Pretty-print the walk-forward comparison table."""
    if not results:
        print("No walk-forward results to display.")
        return

    print(f"\nWALK-FORWARD ANALYSIS: {strategy_name}")
    print("=" * 110)

    # Header
    header = (
        f"{'Win':>3} | {'Train Period':<27} | {'Test Period':<27} | "
        f"{'IS Ret%':>7} {'IS Shrp':>7} {'IS DD%':>7} {'IS #T':>5} | "
        f"{'OOS Ret%':>8} {'OOS Shrp':>8} {'OOS DD%':>8} {'OOS #T':>6}"
    )
    print(header)
    print("-" * 110)

    # Accumulators for summary
    is_returns = []
    oos_returns = []
    is_sharpes = []
    oos_sharpes = []

    for r in results:
        is_ret = r.get("IS Return [%]", "ERR")
        is_shp = r.get("IS Sharpe", "ERR")
        is_dd = r.get("IS Max DD [%]", "ERR")
        is_nt = r.get("IS # Trades", "ERR")
        oos_ret = r.get("OOS Return [%]", "ERR")
        oos_shp = r.get("OOS Sharpe", "ERR")
        oos_dd = r.get("OOS Max DD [%]", "ERR")
        oos_nt = r.get("OOS # Trades", "ERR")

        line = (
            f"{r['Window']:>3} | {r['Train']:<27} | {r['Test']:<27} | "
            f"{is_ret:>7} {is_shp:>7} {is_dd:>7} {is_nt:>5} | "
            f"{oos_ret:>8} {oos_shp:>8} {oos_dd:>8} {oos_nt:>6}"
        )
        print(line)

        # Collect numeric values for summary
        if isinstance(is_ret, (int, float)):
            is_returns.append(is_ret)
        if isinstance(oos_ret, (int, float)):
            oos_returns.append(oos_ret)
        if isinstance(is_shp, (int, float)):
            is_sharpes.append(is_shp)
        if isinstance(oos_shp, (int, float)):
            oos_sharpes.append(oos_shp)

    print("-" * 110)

    # Summary statistics
    if is_returns and oos_returns:
        avg_is_ret = sum(is_returns) / len(is_returns)
        avg_oos_ret = sum(oos_returns) / len(oos_returns)
        avg_is_shp = sum(is_sharpes) / len(is_sharpes) if is_sharpes else 0
        avg_oos_shp = sum(oos_sharpes) / len(oos_sharpes) if oos_sharpes else 0

        print(f"\nSUMMARY ({len(results)} windows)")
        print(f"  Avg In-Sample Return:      {avg_is_ret:>7.2f}%   |   Avg Out-of-Sample Return:  {avg_oos_ret:>7.2f}%")
        print(f"  Avg In-Sample Sharpe:      {avg_is_shp:>7.2f}    |   Avg Out-of-Sample Sharpe:  {avg_oos_shp:>7.2f}")

        # Degradation check
        if avg_is_ret != 0:
            degradation = ((avg_is_ret - avg_oos_ret) / abs(avg_is_ret)) * 100
        else:
            degradation = 0
        print(f"  OOS Return Degradation:    {degradation:>7.1f}%")

        if degradation > 50:
            print("\n  WARNING: Large in-sample vs out-of-sample gap suggests overfitting.")
            print("  Consider simpler strategy parameters or longer training windows.")
        elif degradation > 25:
            print("\n  CAUTION: Moderate degradation. Strategy may be slightly overfit.")
        else:
            print("\n  OK: Out-of-sample performance is reasonably close to in-sample.")
    print()


def main():
    parser = argparse.ArgumentParser(description="Walk-Forward Analysis for Trading Strategies")
    parser.add_argument("--strategy", default="ORB", choices=list(STRATEGY_MAP.keys()),
                        help="Strategy to test (default: ORB)")
    parser.add_argument("--symbol", default="INFY", help="Stock symbol (default: INFY)")
    parser.add_argument("--days", type=int, default=120,
                        help="Days of historical data to load (default: 120)")
    parser.add_argument("--capital", type=int, default=100_000,
                        help="Starting capital in Rs (default: 100000)")
    parser.add_argument("--allow-synthetic", action="store_true",
                        help="Permit synthetic fallback if real data unavailable.")
    args = parser.parse_args()

    print(f"Loading {args.days} days of data for {args.symbol}...")
    df = load_sample_data(args.symbol, args.days, allow_synthetic=args.allow_synthetic)
    if df.empty:
        print("No data available.")
        return

    strategy_class = STRATEGY_MAP[args.strategy]
    print(f"Running walk-forward analysis: {args.strategy} on {args.symbol}")
    print(f"  Train window: {TRAIN_DAYS} days  |  Test window: {TEST_DAYS} days  |  Slide: {SLIDE_DAYS} days")

    results = walk_forward(df, strategy_class, capital=args.capital)
    print_results(results, args.strategy)


if __name__ == "__main__":
    main()
