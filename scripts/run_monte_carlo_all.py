"""
Monte Carlo Stress Testing (All Strategies x All Stocks)
────────────────────────────────────────────────────────
Run Monte Carlo simulation for every strategy-stock combo.

Usage:
    python scripts/run_monte_carlo_all.py
    python scripts/run_monte_carlo_all.py --simulations 5000
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from backtesting import Backtest

from backtest.run_backtest import (
    load_sample_data,
    zerodha_commission_with_slippage,
)
from backtest.run_backtest_v2 import ORBv2, RSIEMAv2, VWAPSupertrendv2
from backtest.monte_carlo import extract_trade_pnls, run_monte_carlo
from config import settings

STRATEGY_MAP = {
    "ORB": ORBv2,
    "RSI_EMA": RSIEMAv2,
    "VWAP_SUPERTREND": VWAPSupertrendv2,
}

RESULTS_DIR = Path(__file__).resolve().parent.parent / "backtest" / "results"


def main():
    parser = argparse.ArgumentParser(description="Monte Carlo for all strategies x stocks")
    parser.add_argument("--days", type=int, default=730, help="Days of data (default: 730)")
    parser.add_argument("--capital", type=int, default=100_000, help="Starting capital")
    parser.add_argument("--simulations", type=int, default=10_000, help="MC simulations (default: 10000)")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    symbols = settings.WATCHLIST
    strategies = list(STRATEGY_MAP.keys())
    total = len(symbols) * len(strategies)

    print(f"Monte Carlo: {len(strategies)} strategies x {len(symbols)} stocks = {total} combos")
    print(f"Simulations: {args.simulations:,} | Days: {args.days} | Capital: Rs {args.capital:,}")
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
                    "status": "no_data",
                })
                continue

            try:
                bt = Backtest(
                    df, strategy_class,
                    cash=args.capital,
                    commission=zerodha_commission_with_slippage,
                    exclusive_orders=True,
                    trade_on_close=True,
                )
                stats = bt.run()
                pnls = extract_trade_pnls(stats)
                n_trades = len(pnls)

                if n_trades == 0:
                    print("0 trades")
                    summary_rows.append({
                        "strategy": strategy_name, "symbol": symbol,
                        "status": "zero_trades", "n_trades": 0,
                    })
                    continue

                mc = run_monte_carlo(pnls, capital=args.capital, n_simulations=args.simulations)

                row = {
                    "strategy": strategy_name,
                    "symbol": symbol,
                    "status": "ok",
                    "n_trades": n_trades,
                    "base_return_pct": round(stats["Return [%]"], 2),
                    "dd_5th": round(mc["dd_5th"], 2),
                    "dd_median": round(mc["dd_median"], 2),
                    "dd_95th": round(mc["dd_95th"], 2),
                    "equity_5th": round(mc["equity_5th"], 0),
                    "equity_median": round(mc["equity_median"], 0),
                    "equity_95th": round(mc["equity_95th"], 0),
                    "prob_ruin": round(mc["prob_ruin"], 4),
                }
                summary_rows.append(row)

                print(f"Trades: {n_trades} | DD 95th: {mc['dd_95th']:.1f}% | "
                      f"P(ruin): {mc['prob_ruin']*100:.2f}%")

            except Exception as e:
                print(f"ERROR: {e}")
                summary_rows.append({
                    "strategy": strategy_name, "symbol": symbol,
                    "status": f"error: {e}",
                })

    # Save
    df_summary = pd.DataFrame(summary_rows)
    csv_path = RESULTS_DIR / "monte_carlo_summary.csv"
    df_summary.to_csv(csv_path, index=False)

    # Print summary
    print(f"\n{'=' * 70}")
    print("MONTE CARLO SUMMARY")
    print(f"{'=' * 70}")

    ok_rows = [r for r in summary_rows if r.get("status") == "ok"]
    if ok_rows:
        print(f"{'Strategy':<18} {'Symbol':<12} {'Trades':>7} {'DD 95th%':>9} {'DD Med%':>8} {'P(Ruin)':>9}")
        print("-" * 70)
        for r in ok_rows:
            print(f"{r['strategy']:<18} {r['symbol']:<12} {r['n_trades']:>7} "
                  f"{r['dd_95th']:>9.1f} {r['dd_median']:>8.1f} {r['prob_ruin']*100:>8.2f}%")

        # Strategy-level aggregation
        print(f"\nPER-STRATEGY AVERAGES:")
        for strat in strategies:
            strat_rows = [r for r in ok_rows if r["strategy"] == strat]
            if strat_rows:
                avg_dd95 = sum(r["dd_95th"] for r in strat_rows) / len(strat_rows)
                max_dd95 = max(r["dd_95th"] for r in strat_rows)
                avg_ruin = sum(r["prob_ruin"] for r in strat_rows) / len(strat_rows)
                print(f"  {strat:<18} Avg DD95: {avg_dd95:.1f}% | Max DD95: {max_dd95:.1f}% | "
                      f"Avg P(Ruin): {avg_ruin*100:.2f}%")

    print(f"\nFull results: {csv_path}")


if __name__ == "__main__":
    main()
