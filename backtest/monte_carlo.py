"""
Monte Carlo Simulation
──────────────────────
Shuffle trade order from a backtest to estimate the distribution of
drawdowns and final equity — helps gauge how much of the result is due
to lucky sequencing vs genuine edge.

Usage:
    python backtest/monte_carlo.py                                   # Defaults
    python backtest/monte_carlo.py --strategy RSI_EMA --capital 200000
    python backtest/monte_carlo.py --symbol RELIANCE --strategy ORB --simulations 5000
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from backtesting import Backtest

from backtest.run_backtest import (
    ORBBacktest,
    RSIEMABacktest,
    VWAPSupertrendBacktest,
    load_sample_data,
    zerodha_commission,
)


# ── Strategy lookup ──
STRATEGY_MAP = {
    "ORB": ORBBacktest,
    "RSI_EMA": RSIEMABacktest,
    "VWAP_SUPERTREND": VWAPSupertrendBacktest,
}


def extract_trade_pnls(stats) -> np.ndarray:
    """
    Extract per-trade P&L values from backtesting.py stats.

    The stats._trades DataFrame contains 'PnL' for each closed trade.
    Returns a numpy array of P&L values.
    """
    trades_df = stats._trades
    if trades_df.empty:
        return np.array([])
    return trades_df["PnL"].values.astype(float)


def run_monte_carlo(
    pnls: np.ndarray,
    capital: float,
    n_simulations: int = 10_000,
    ruin_threshold: float = 0.50,
) -> dict:
    """
    Shuffle trade P&L order and compute equity curve statistics.

    Parameters
    ----------
    pnls : array of per-trade P&L values
    capital : starting capital
    n_simulations : number of random shuffles (default 10,000)
    ruin_threshold : fraction of starting capital below which we declare ruin
                     (default 0.50 = equity drops below 50% of start)

    Returns
    -------
    dict with keys:
        max_drawdowns       - array of max drawdown (%) per simulation
        final_equities      - array of final equity values per simulation
        dd_5th              - 5th percentile max drawdown (worst-case-ish)
        dd_median           - median max drawdown
        dd_95th             - 95th percentile max drawdown
        equity_5th          - 5th percentile final equity
        equity_median       - median final equity
        equity_95th         - 95th percentile final equity
        prob_ruin           - probability of equity going below ruin_threshold * capital
        n_simulations       - number of simulations actually run
    """
    n_trades = len(pnls)
    if n_trades == 0:
        return {
            "max_drawdowns": np.array([]),
            "final_equities": np.array([]),
            "dd_5th": 0.0, "dd_median": 0.0, "dd_95th": 0.0,
            "equity_5th": capital, "equity_median": capital, "equity_95th": capital,
            "prob_ruin": 0.0,
            "n_simulations": 0,
        }

    ruin_level = capital * ruin_threshold
    max_drawdowns = np.empty(n_simulations)
    final_equities = np.empty(n_simulations)
    ruin_count = 0

    rng = np.random.default_rng(seed=42)

    for i in range(n_simulations):
        # Shuffle trade order
        shuffled = rng.permutation(pnls)

        # Build equity curve
        equity = np.empty(n_trades + 1)
        equity[0] = capital
        equity[1:] = capital + np.cumsum(shuffled)

        # Max drawdown
        running_peak = np.maximum.accumulate(equity)
        drawdown_pct = (running_peak - equity) / running_peak * 100.0
        max_drawdowns[i] = np.max(drawdown_pct)

        # Final equity
        final_equities[i] = equity[-1]

        # Ruin check
        if np.any(equity < ruin_level):
            ruin_count += 1

    return {
        "max_drawdowns": max_drawdowns,
        "final_equities": final_equities,
        "dd_5th": float(np.percentile(max_drawdowns, 5)),
        "dd_median": float(np.percentile(max_drawdowns, 50)),
        "dd_95th": float(np.percentile(max_drawdowns, 95)),
        "equity_5th": float(np.percentile(final_equities, 5)),
        "equity_median": float(np.percentile(final_equities, 50)),
        "equity_95th": float(np.percentile(final_equities, 95)),
        "prob_ruin": ruin_count / n_simulations,
        "n_simulations": n_simulations,
    }


def print_report(mc: dict, capital: float, n_trades: int, strategy: str, symbol: str):
    """Pretty-print Monte Carlo simulation results."""
    if mc["n_simulations"] == 0:
        print("No trades to simulate. Backtest produced zero trades.")
        return

    print(f"\nMONTE CARLO SIMULATION: {strategy} on {symbol}")
    print(f"  Starting Capital: Rs {capital:,.0f}")
    print(f"  Trades Shuffled:  {n_trades}")
    print(f"  Simulations:      {mc['n_simulations']:,}")
    print("=" * 60)

    print("\n  MAX DRAWDOWN DISTRIBUTION")
    print(f"    5th percentile (best case):   {mc['dd_5th']:>7.2f}%")
    print(f"    Median:                       {mc['dd_median']:>7.2f}%")
    print(f"    95th percentile (worst case): {mc['dd_95th']:>7.2f}%")

    print("\n  FINAL EQUITY DISTRIBUTION")
    print(f"    5th percentile (worst case):  Rs {mc['equity_5th']:>12,.0f}")
    print(f"    Median:                       Rs {mc['equity_median']:>12,.0f}")
    print(f"    95th percentile (best case):  Rs {mc['equity_95th']:>12,.0f}")

    # Return percentages relative to starting capital
    ret_5 = (mc["equity_5th"] - capital) / capital * 100
    ret_50 = (mc["equity_median"] - capital) / capital * 100
    ret_95 = (mc["equity_95th"] - capital) / capital * 100
    print(f"\n    5th pctile return:  {ret_5:>+7.2f}%")
    print(f"    Median return:      {ret_50:>+7.2f}%")
    print(f"    95th pctile return: {ret_95:>+7.2f}%")

    print(f"\n  PROBABILITY OF RUIN (<{int(50)}% of capital)")
    print(f"    P(ruin):  {mc['prob_ruin'] * 100:.2f}%")

    # Assessment
    print("\n  ASSESSMENT")
    print("  " + "-" * 40)
    if mc["prob_ruin"] > 0.10:
        print("  HIGH RISK: >10% chance of ruin. Reduce position sizes or")
        print("  tighten stop-losses before trading this strategy live.")
    elif mc["prob_ruin"] > 0.02:
        print("  MODERATE RISK: 2-10% ruin probability. Proceed with caution,")
        print("  consider reducing size or adding risk filters.")
    elif mc["prob_ruin"] > 0:
        print("  LOW RISK: <2% ruin probability. Strategy appears robust")
        print("  to trade ordering, but keep monitoring in live trading.")
    else:
        print("  MINIMAL RISK: No ruin scenarios in simulation. Strategy")
        print("  shows strong resilience to trade-order randomness.")

    if mc["dd_95th"] > 30:
        print("  WARNING: 95th percentile drawdown exceeds 30%. Ensure you")
        print("  can psychologically handle this level of drawdown.")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Monte Carlo Simulation for Trading Strategy Robustness"
    )
    parser.add_argument("--strategy", default="ORB",
                        choices=list(STRATEGY_MAP.keys()),
                        help="Strategy to backtest and simulate (default: ORB)")
    parser.add_argument("--symbol", default="INFY",
                        help="Stock symbol (default: INFY)")
    parser.add_argument("--days", type=int, default=60,
                        help="Days of historical data (default: 60)")
    parser.add_argument("--capital", type=int, default=100_000,
                        help="Starting capital in Rs (default: 100000)")
    parser.add_argument("--simulations", type=int, default=10_000,
                        help="Number of Monte Carlo shuffles (default: 10000)")
    parser.add_argument("--allow-synthetic", action="store_true",
                        help="Permit synthetic fallback if real data unavailable.")
    args = parser.parse_args()

    # Step 1: Load data and run the base backtest
    print(f"Loading {args.days} days of data for {args.symbol}...")
    df = load_sample_data(args.symbol, args.days, allow_synthetic=args.allow_synthetic)
    if df.empty:
        print("No data available.")
        return

    strategy_class = STRATEGY_MAP[args.strategy]
    print(f"Running base backtest: {args.strategy} on {args.symbol}...")

    bt = Backtest(
        df, strategy_class,
        cash=args.capital,
        commission=zerodha_commission,
        exclusive_orders=True,
    )
    stats = bt.run()

    # Step 2: Extract per-trade P&L
    pnls = extract_trade_pnls(stats)
    n_trades = len(pnls)

    if n_trades == 0:
        print("Backtest produced zero trades. Nothing to simulate.")
        return

    print(f"Base backtest: {n_trades} trades | Return: {stats['Return [%]']:.2f}%")
    print(f"Running {args.simulations:,} Monte Carlo simulations...")

    # Step 3: Run Monte Carlo
    mc = run_monte_carlo(
        pnls,
        capital=args.capital,
        n_simulations=args.simulations,
    )

    # Step 4: Report
    print_report(mc, args.capital, n_trades, args.strategy, args.symbol)


if __name__ == "__main__":
    main()
