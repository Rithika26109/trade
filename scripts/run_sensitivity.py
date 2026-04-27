"""
Parameter Sensitivity Analysis
──────────────────────────────
Test each strategy parameter at [0.8x, 0.9x, 1.0x, 1.1x, 1.2x] of default
on representative stocks to check robustness to parameter changes.

Usage:
    python scripts/run_sensitivity.py
    python scripts/run_sensitivity.py --days 365
"""

import argparse
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from backtesting import Backtest

from backtest.run_backtest import (
    load_sample_data,
    zerodha_commission_with_slippage,
)
from backtest.run_backtest_v2 import ORBv2, RSIEMAv2, VWAPSupertrendv2
from config import settings

RESULTS_DIR = Path(__file__).resolve().parent.parent / "backtest" / "results"

# Representative stocks for sensitivity testing
TEST_STOCKS = ["RELIANCE", "INFY", "HDFCBANK"]

# Perturbation multipliers
MULTIPLIERS = [0.8, 0.9, 1.0, 1.1, 1.2]

# Parameters per strategy (attr_name, default_value, is_integer)
STRATEGY_PARAMS = {
    "ORB": {
        "class": ORBv2,
        "params": [
            ("orb_period", 3, True),
            ("atr_multiplier", 2.0, False),
            ("rr_ratio", 2.0, False),
            ("adx_min", 20, True),
            ("vol_multiplier", 1.5, False),
        ],
    },
    "RSI_EMA": {
        "class": RSIEMAv2,
        "params": [
            ("ema_fast", 9, True),
            ("ema_slow", 21, True),
            ("rsi_period", 14, True),
            ("atr_multiplier", 2.0, False),
            ("rr_ratio", 2.0, False),
            ("adx_min", 20, True),
        ],
    },
    "VWAP_SUPERTREND": {
        "class": VWAPSupertrendv2,
        "params": [
            ("supertrend_period", 10, True),
            ("supertrend_multiplier", 3.0, False),
            ("confirmation_candles", 3, True),
            ("rr_ratio", 2.0, False),
            ("adx_min", 20, True),
        ],
    },
}


def run_sensitivity_for_strategy(strategy_name: str, days: int, capital: int) -> pd.DataFrame:
    """Run sensitivity analysis for one strategy across test stocks."""
    info = STRATEGY_PARAMS[strategy_name]
    strategy_class = info["class"]
    params = info["params"]

    # Pre-load data for all test stocks
    stock_data = {}
    for symbol in TEST_STOCKS:
        df = load_sample_data(symbol, days=days)
        if not df.empty:
            stock_data[symbol] = df

    if not stock_data:
        print(f"  No data available for any test stock. Skipping {strategy_name}.")
        return pd.DataFrame()

    results = []
    total_tests = len(params) * len(MULTIPLIERS) * len(stock_data)
    done = 0

    for param_name, default_val, is_int in params:
        for mult in MULTIPLIERS:
            val = default_val * mult
            if is_int:
                val = max(1, round(val))

            for symbol, df in stock_data.items():
                done += 1
                # Set the parameter on the class
                original = getattr(strategy_class, param_name)
                setattr(strategy_class, param_name, val)

                row = {
                    "strategy": strategy_name,
                    "parameter": param_name,
                    "default": default_val,
                    "multiplier": mult,
                    "value": val,
                    "symbol": symbol,
                }

                try:
                    bt = Backtest(
                        df, strategy_class,
                        cash=capital,
                        commission=zerodha_commission_with_slippage,
                        exclusive_orders=True,
                        trade_on_close=True,
                    )
                    stats = bt.run()
                    row["return_pct"] = round(stats["Return [%]"], 2)
                    row["sharpe"] = round(stats["Sharpe Ratio"], 2) if pd.notna(stats["Sharpe Ratio"]) else 0.0
                    row["max_dd_pct"] = round(stats["Max. Drawdown [%]"], 2)
                    row["win_rate_pct"] = round(stats["Win Rate [%]"], 1) if stats["# Trades"] > 0 else 0.0
                    row["num_trades"] = stats["# Trades"]
                except Exception as e:
                    row["return_pct"] = None
                    row["sharpe"] = None
                    row["max_dd_pct"] = None
                    row["win_rate_pct"] = None
                    row["num_trades"] = 0

                # Reset to original
                setattr(strategy_class, param_name, original)
                results.append(row)

        # Print progress per parameter
        print(f"    {param_name}: tested {len(MULTIPLIERS)} values x {len(stock_data)} stocks")

    return pd.DataFrame(results)


def compute_stability_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Compute coefficient of variation for Sharpe across parameter values."""
    if df.empty:
        return pd.DataFrame()

    summary_rows = []
    for (strategy, param), group in df.groupby(["strategy", "parameter"]):
        # Average Sharpe across stocks for each multiplier value
        avg_sharpes = group.groupby("multiplier")["sharpe"].mean()
        sharpe_values = avg_sharpes.dropna().values

        if len(sharpe_values) >= 3:
            mean_sharpe = np.mean(sharpe_values)
            std_sharpe = np.std(sharpe_values)
            cv = abs(std_sharpe / mean_sharpe) if abs(mean_sharpe) > 0.01 else float("inf")
        else:
            mean_sharpe = 0
            cv = float("inf")

        stability = "STABLE" if cv < 0.3 else "MODERATE" if cv < 0.5 else "FRAGILE"

        summary_rows.append({
            "strategy": strategy,
            "parameter": param,
            "mean_sharpe": round(mean_sharpe, 3),
            "cv_sharpe": round(cv, 3),
            "stability": stability,
        })

    return pd.DataFrame(summary_rows)


def main():
    parser = argparse.ArgumentParser(description="Parameter sensitivity analysis")
    parser.add_argument("--days", type=int, default=730, help="Days of data (default: 730)")
    parser.add_argument("--capital", type=int, default=100_000, help="Starting capital")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Parameter Sensitivity Analysis")
    print(f"Stocks: {', '.join(TEST_STOCKS)} | Days: {args.days}")
    print(f"Multipliers: {MULTIPLIERS}")
    print("=" * 70)

    all_results = []
    for strategy_name in STRATEGY_PARAMS:
        print(f"\n{strategy_name}:")
        df = run_sensitivity_for_strategy(strategy_name, args.days, args.capital)
        if not df.empty:
            all_results.append(df)
            csv_path = RESULTS_DIR / f"sensitivity_{strategy_name}.csv"
            df.to_csv(csv_path, index=False)
            print(f"  Saved: {csv_path}")

    if not all_results:
        print("\nNo results generated. Check data availability.")
        return

    combined = pd.concat(all_results, ignore_index=True)

    # Stability summary
    stability = compute_stability_summary(combined)
    if not stability.empty:
        stability_path = RESULTS_DIR / "sensitivity_stability.csv"
        stability.to_csv(stability_path, index=False)

        print(f"\n{'=' * 70}")
        print("PARAMETER STABILITY SUMMARY")
        print(f"{'=' * 70}")
        print(f"{'Strategy':<18} {'Parameter':<24} {'Mean Sharpe':>12} {'CV':>8} {'Verdict':>10}")
        print("-" * 75)
        for _, r in stability.iterrows():
            print(f"{r['strategy']:<18} {r['parameter']:<24} {r['mean_sharpe']:>12.3f} "
                  f"{r['cv_sharpe']:>8.3f} {r['stability']:>10}")

        stable = (stability["stability"] == "STABLE").sum()
        moderate = (stability["stability"] == "MODERATE").sum()
        fragile = (stability["stability"] == "FRAGILE").sum()
        total = len(stability)
        print(f"\n  {stable}/{total} STABLE | {moderate}/{total} MODERATE | {fragile}/{total} FRAGILE")

        if fragile / total > 0.5:
            print("  WARNING: Majority of parameters are fragile. Strategy may be overfit.")
        elif fragile == 0:
            print("  PASS: All parameters show acceptable stability.")


if __name__ == "__main__":
    main()
