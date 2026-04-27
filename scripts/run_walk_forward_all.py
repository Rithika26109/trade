"""
Walk-Forward Validation (All Strategies x All Stocks)
─────────────────────────────────────────────────────
Orchestrates walk-forward analysis across all strategy-stock combinations.

Usage:
    python scripts/run_walk_forward_all.py
    python scripts/run_walk_forward_all.py --days 365
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from backtest.run_backtest import (
    load_sample_data,
    zerodha_commission_with_slippage,
)
from backtest.run_backtest_v2 import ORBv2, RSIEMAv2, VWAPSupertrendv2
from backtest.walk_forward import walk_forward
from config import settings

STRATEGY_MAP = {
    "ORB": ORBv2,
    "RSI_EMA": RSIEMAv2,
    "VWAP_SUPERTREND": VWAPSupertrendv2,
}

RESULTS_DIR = Path(__file__).resolve().parent.parent / "backtest" / "results"


def summarize_walk_forward(results: list) -> dict:
    """Aggregate walk-forward window results into summary metrics."""
    if not results:
        return {
            "num_windows": 0,
            "avg_is_return": 0, "avg_oos_return": 0,
            "avg_is_sharpe": 0, "avg_oos_sharpe": 0,
            "oos_degradation_pct": 0,
            "positive_oos_windows": 0,
            "worst_oos_dd": 0,
        }

    is_returns = [r["IS Return [%]"] for r in results if isinstance(r.get("IS Return [%]"), (int, float))]
    oos_returns = [r["OOS Return [%]"] for r in results if isinstance(r.get("OOS Return [%]"), (int, float))]
    is_sharpes = [r["IS Sharpe"] for r in results if isinstance(r.get("IS Sharpe"), (int, float))]
    oos_sharpes = [r["OOS Sharpe"] for r in results if isinstance(r.get("OOS Sharpe"), (int, float))]
    oos_dds = [r["OOS Max DD [%]"] for r in results if isinstance(r.get("OOS Max DD [%]"), (int, float))]

    avg_is_ret = sum(is_returns) / len(is_returns) if is_returns else 0
    avg_oos_ret = sum(oos_returns) / len(oos_returns) if oos_returns else 0
    avg_is_shp = sum(is_sharpes) / len(is_sharpes) if is_sharpes else 0
    avg_oos_shp = sum(oos_sharpes) / len(oos_sharpes) if oos_sharpes else 0

    degradation = ((avg_is_ret - avg_oos_ret) / abs(avg_is_ret) * 100) if abs(avg_is_ret) > 0.01 else 0
    positive_oos = sum(1 for r in oos_returns if r > 0)

    return {
        "num_windows": len(results),
        "avg_is_return": round(avg_is_ret, 2),
        "avg_oos_return": round(avg_oos_ret, 2),
        "avg_is_sharpe": round(avg_is_shp, 2),
        "avg_oos_sharpe": round(avg_oos_shp, 2),
        "oos_degradation_pct": round(degradation, 1),
        "positive_oos_windows": positive_oos,
        "worst_oos_dd": round(min(oos_dds), 2) if oos_dds else 0,
    }


def main():
    parser = argparse.ArgumentParser(description="Walk-Forward Analysis for all strategies x stocks")
    parser.add_argument("--days", type=int, default=730, help="Days of data (default: 730)")
    parser.add_argument("--capital", type=int, default=100_000, help="Starting capital")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    symbols = settings.WATCHLIST
    strategies = list(STRATEGY_MAP.keys())
    total = len(symbols) * len(strategies)

    print(f"Walk-Forward Analysis: {len(strategies)} strategies x {len(symbols)} stocks = {total} combos")
    print(f"Days: {args.days} | Capital: Rs {args.capital:,}")
    print("=" * 70)

    summary_rows = []
    done = 0

    for strategy_name, strategy_class in STRATEGY_MAP.items():
        for symbol in symbols:
            done += 1
            print(f"\n[{done}/{total}] {strategy_name} on {symbol}...", end=" ")

            df = load_sample_data(symbol, days=args.days)
            if df.empty:
                print("NO DATA")
                summary_rows.append({
                    "strategy": strategy_name, "symbol": symbol,
                    "status": "no_data", "num_windows": 0,
                })
                continue

            try:
                results = walk_forward(
                    df, strategy_class,
                    capital=args.capital,
                    commission_func=zerodha_commission_with_slippage,
                )
                summary = summarize_walk_forward(results)
                summary["strategy"] = strategy_name
                summary["symbol"] = symbol
                summary["status"] = "ok"
                summary_rows.append(summary)

                print(f"Windows: {summary['num_windows']} | "
                      f"IS Return: {summary['avg_is_return']:+.2f}% | "
                      f"OOS Return: {summary['avg_oos_return']:+.2f}% | "
                      f"Degradation: {summary['oos_degradation_pct']:.0f}%")

            except Exception as e:
                print(f"ERROR: {e}")
                summary_rows.append({
                    "strategy": strategy_name, "symbol": symbol,
                    "status": f"error: {e}", "num_windows": 0,
                })

    # Save results
    df_summary = pd.DataFrame(summary_rows)
    csv_path = RESULTS_DIR / "walk_forward_summary.csv"
    df_summary.to_csv(csv_path, index=False)

    # Print strategy-level summary
    print(f"\n{'=' * 70}")
    print("WALK-FORWARD SUMMARY BY STRATEGY")
    print(f"{'=' * 70}")

    ok_results = df_summary[df_summary["status"] == "ok"]
    for strategy_name in strategies:
        strat_results = ok_results[ok_results["strategy"] == strategy_name]
        if strat_results.empty:
            print(f"\n  {strategy_name}: No valid results")
            continue

        avg_deg = strat_results["oos_degradation_pct"].mean()
        avg_oos_ret = strat_results["avg_oos_return"].mean()
        avg_oos_shp = strat_results["avg_oos_sharpe"].mean()
        stocks_profitable = (strat_results["avg_oos_return"] > 0).sum()

        verdict = "PASS" if avg_deg < 50 else "FAIL (overfitting suspected)"

        print(f"\n  {strategy_name}:")
        print(f"    Mean OOS Return: {avg_oos_ret:+.2f}%")
        print(f"    Mean OOS Sharpe: {avg_oos_shp:.2f}")
        print(f"    Mean Degradation: {avg_deg:.1f}%")
        print(f"    Stocks with positive OOS: {stocks_profitable}/{len(strat_results)}")
        print(f"    Verdict: {verdict}")

    print(f"\nFull results: {csv_path}")


if __name__ == "__main__":
    main()
