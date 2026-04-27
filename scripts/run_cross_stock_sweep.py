"""
Cross-Stock Sweep
─────────────────
Analyze baseline results to determine how well each strategy works
across the full stock universe (not just cherry-picked winners).

Usage:
    python scripts/run_cross_stock_sweep.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

RESULTS_DIR = Path(__file__).resolve().parent.parent / "backtest" / "results"


def main():
    baseline_path = RESULTS_DIR / "baseline_summary.csv"
    if not baseline_path.exists():
        print(f"ERROR: {baseline_path} not found. Run run_baseline_backtests.py first.")
        sys.exit(1)

    df = pd.read_csv(baseline_path)
    ok = df[df["status"] == "ok"].copy()

    if ok.empty:
        print("No successful backtests found in baseline_summary.csv")
        sys.exit(1)

    print("CROSS-STOCK SWEEP")
    print("=" * 70)

    summary_rows = []
    strategies = ok["strategy"].unique()

    for strat in strategies:
        s = ok[ok["strategy"] == strat]
        total_stocks = len(s)
        profitable = (s["return_pct"] > 0).sum()
        good_sharpe = (s["sharpe"] > 0.5).sum()
        mean_sharpe = s["sharpe"].mean()
        std_sharpe = s["sharpe"].std()
        mean_return = s["return_pct"].mean()
        worst_dd = s["max_dd_pct"].min()  # Most negative drawdown
        median_wr = s["win_rate_pct"].median()
        mean_trades = s["num_trades"].mean()

        # Pass/fail criteria
        pass_profitable = profitable >= 6  # >=6/10 profitable
        pass_sharpe = mean_sharpe > 0
        pass_dd = worst_dd > -40  # No single stock DD > 40%
        overall = "PASS" if (pass_profitable and pass_sharpe and pass_dd) else "FAIL"

        row = {
            "strategy": strat,
            "total_stocks": total_stocks,
            "profitable_stocks": profitable,
            "good_sharpe_stocks": good_sharpe,
            "mean_sharpe": round(mean_sharpe, 3),
            "std_sharpe": round(std_sharpe, 3),
            "mean_return_pct": round(mean_return, 2),
            "worst_max_dd_pct": round(worst_dd, 2),
            "median_win_rate": round(median_wr, 1),
            "mean_trades": round(mean_trades, 1),
            "pass_profitable": pass_profitable,
            "pass_sharpe": pass_sharpe,
            "pass_dd": pass_dd,
            "overall": overall,
        }
        summary_rows.append(row)

        print(f"\n  {strat}:")
        print(f"    Profitable: {profitable}/{total_stocks} stocks {'PASS' if pass_profitable else 'FAIL'}")
        print(f"    Mean Sharpe: {mean_sharpe:.3f} (std: {std_sharpe:.3f}) {'PASS' if pass_sharpe else 'FAIL'}")
        print(f"    Mean Return: {mean_return:+.2f}%")
        print(f"    Worst Max DD: {worst_dd:.1f}% {'PASS' if pass_dd else 'FAIL (>40%)'}")
        print(f"    Median Win Rate: {median_wr:.1f}%")
        print(f"    Mean Trades/Stock: {mean_trades:.0f}")
        print(f"    OVERALL: {overall}")

    # Save
    df_summary = pd.DataFrame(summary_rows)
    csv_path = RESULTS_DIR / "cross_stock_summary.csv"
    df_summary.to_csv(csv_path, index=False)
    print(f"\nSaved: {csv_path}")

    # Per-stock detail
    print(f"\n{'=' * 70}")
    print("PER-STOCK DETAIL")
    print(f"{'Strategy':<18} {'Symbol':<12} {'Return%':>8} {'Sharpe':>7} {'MaxDD%':>7} {'Trades':>7}")
    print("-" * 65)
    for _, r in ok.sort_values(["strategy", "return_pct"], ascending=[True, False]).iterrows():
        print(f"{r['strategy']:<18} {r['symbol']:<12} {r['return_pct']:>+8.2f} "
              f"{r['sharpe']:>7.2f} {r['max_dd_pct']:>7.1f} {r['num_trades']:>7}")


if __name__ == "__main__":
    main()
