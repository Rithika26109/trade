"""
Baseline Backtests
──────────────────
Run all strategies on all watchlist stocks with realistic costs + slippage.
Saves summary CSV and individual HTML reports.

Usage:
    python scripts/run_baseline_backtests.py
    python scripts/run_baseline_backtests.py --days 365    # 1 year instead of 2
    python scripts/run_baseline_backtests.py --capital 200000
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from backtesting import Backtest

from backtest.run_backtest import (
    load_sample_data,
    zerodha_commission_with_slippage,
)
from backtest.run_backtest_v2 import ORBv2, RSIEMAv2, VWAPSupertrendv2
from config import settings

STRATEGY_MAP = {
    "ORB": ORBv2,
    "RSI_EMA": RSIEMAv2,
    "VWAP_SUPERTREND": VWAPSupertrendv2,
}

RESULTS_DIR = Path(__file__).resolve().parent.parent / "backtest" / "results"


def compute_profit_factor(stats) -> float:
    """Compute profit factor from backtesting.py stats."""
    try:
        trades_df = stats._trades
        if trades_df.empty:
            return 0.0
        wins = trades_df[trades_df["PnL"] > 0]["PnL"].sum()
        losses = abs(trades_df[trades_df["PnL"] < 0]["PnL"].sum())
        return round(wins / losses, 2) if losses > 0 else float("inf")
    except Exception:
        return 0.0


def run_single_backtest(symbol: str, strategy_name: str, days: int, capital: int) -> dict:
    """Run one backtest, return metrics dict."""
    row = {
        "strategy": strategy_name,
        "symbol": symbol,
        "days": days,
        "return_pct": None,
        "sharpe": None,
        "max_dd_pct": None,
        "win_rate_pct": None,
        "num_trades": 0,
        "profit_factor": None,
        "avg_trade_pct": None,
        "best_trade_pct": None,
        "worst_trade_pct": None,
        "status": "unknown",
    }

    df = load_sample_data(symbol, days=days)
    if df.empty:
        row["status"] = "no_data"
        return row

    strategy_class = STRATEGY_MAP[strategy_name]

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
        row["profit_factor"] = compute_profit_factor(stats)
        row["avg_trade_pct"] = round(stats["Avg. Trade [%]"], 3) if stats["# Trades"] > 0 else 0.0
        row["best_trade_pct"] = round(stats["Best Trade [%]"], 2) if stats["# Trades"] > 0 else 0.0
        row["worst_trade_pct"] = round(stats["Worst Trade [%]"], 2) if stats["# Trades"] > 0 else 0.0
        row["status"] = "ok"

        # Save HTML report
        report_path = RESULTS_DIR / f"baseline_{strategy_name}_{symbol}.html"
        try:
            bt.plot(filename=str(report_path), open_browser=False)
        except Exception:
            pass  # Plot failures are non-critical

    except Exception as e:
        row["status"] = f"error: {e}"

    return row


def main():
    parser = argparse.ArgumentParser(description="Run baseline backtests for all strategies x stocks")
    parser.add_argument("--days", type=int, default=730, help="Days of data (default: 730)")
    parser.add_argument("--capital", type=int, default=100_000, help="Starting capital (default: 100000)")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    symbols = settings.WATCHLIST
    strategies = list(STRATEGY_MAP.keys())
    total = len(symbols) * len(strategies)

    print(f"Running {total} backtests ({len(strategies)} strategies x {len(symbols)} stocks)")
    print(f"Capital: Rs {args.capital:,} | Days: {args.days} | Slippage: {settings.BACKTEST_SLIPPAGE_PCT}%")
    print("=" * 70)

    results = []
    done = 0
    for strategy_name in strategies:
        for symbol in symbols:
            done += 1
            print(f"\n[{done}/{total}] {strategy_name} on {symbol}...", end=" ")

            row = run_single_backtest(symbol, strategy_name, args.days, args.capital)
            results.append(row)

            if row["status"] == "ok":
                print(f"Return: {row['return_pct']:+.2f}% | Sharpe: {row['sharpe']:.2f} | "
                      f"DD: {row['max_dd_pct']:.1f}% | Trades: {row['num_trades']} | "
                      f"WR: {row['win_rate_pct']:.0f}%")
            else:
                print(f"FAILED: {row['status']}")

    # Save summary CSV
    df_results = pd.DataFrame(results)
    csv_path = RESULTS_DIR / "baseline_summary.csv"
    df_results.to_csv(csv_path, index=False)
    print(f"\n{'=' * 70}")
    print(f"Summary saved: {csv_path}")

    # Print summary table
    ok_results = [r for r in results if r["status"] == "ok"]
    if ok_results:
        print(f"\nBASELINE SUMMARY ({len(ok_results)}/{total} successful)")
        print(f"{'Strategy':<18} {'Symbol':<12} {'Return%':>8} {'Sharpe':>7} {'MaxDD%':>7} {'Trades':>7} {'WinRate':>8} {'PF':>6}")
        print("-" * 75)
        for r in ok_results:
            print(f"{r['strategy']:<18} {r['symbol']:<12} {r['return_pct']:>+8.2f} {r['sharpe']:>7.2f} "
                  f"{r['max_dd_pct']:>7.1f} {r['num_trades']:>7} {r['win_rate_pct']:>7.1f}% {r['profit_factor']:>6.2f}")

    failed = [r for r in results if r["status"] != "ok"]
    if failed:
        print(f"\nFAILED ({len(failed)}):")
        for r in failed:
            print(f"  {r['strategy']} / {r['symbol']}: {r['status']}")


if __name__ == "__main__":
    main()
