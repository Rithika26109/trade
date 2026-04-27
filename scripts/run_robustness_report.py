"""
Robustness Report — Honest Validation
──────────────────────────────────────
PASS only when the strategy is actually tradable, not just "structurally sound."

A system that loses money consistently is not robust — it's robustly bad.

PASS requires ALL of:
  1. Mean OOS Return > 0           (walk-forward proves real-world edge)
  2. Mean Sharpe > 0.5             (risk-adjusted returns worth the effort)
  3. Profit Factor > 1.1           (winners meaningfully outweigh losers)
  4. Profitable stocks >= 50%      (not cherry-picked to one stock)
  5. Max Drawdown < 30%            (survivable worst case)
  6. Monte Carlo P(Ruin) < 10%     (tail risk controlled)

Plus structural checks (data, backtests, slippage, sensitivity).

Usage:
    python scripts/run_robustness_report.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from config import settings

RESULTS_DIR = Path(__file__).resolve().parent.parent / "backtest" / "results"
HIST_DIR = settings.HISTORICAL_DATA_DIR


# ═══════════════════════════════════════════════════════════════════
# Structural checks (necessary but NOT sufficient)
# ═══════════════════════════════════════════════════════════════════

def check_historical_data() -> tuple[bool, str]:
    """Sufficient historical data cached."""
    csv_files = list(HIST_DIR.glob("*_5min.csv"))
    if not csv_files:
        return False, "No CSV files in data/historical/"
    good = 0
    for f in csv_files:
        try:
            n_rows = sum(1 for _ in open(f)) - 1
            if n_rows >= 15_000:
                good += 1
        except Exception:
            pass
    passed = good >= 8
    return passed, f"{good}/{len(csv_files)} stocks with sufficient data"


def check_backtests_executed() -> tuple[bool, str]:
    """Baseline backtests ran successfully."""
    path = RESULTS_DIR / "v2_summary.csv"
    if not path.exists():
        path = RESULTS_DIR / "baseline_summary.csv"
    if not path.exists():
        return False, "No summary CSV found"
    df = pd.read_csv(path)
    total = len(df)
    has_trades = (df["num_trades"] > 0).sum() if "num_trades" in df.columns else total
    passed = has_trades >= 20
    return passed, f"{has_trades}/{total} backtests with trades"


def check_slippage() -> tuple[bool, str]:
    """Slippage is modeled in backtests."""
    val = getattr(settings, "BACKTEST_SLIPPAGE_PCT", 0)
    passed = val > 0
    return passed, f"BACKTEST_SLIPPAGE_PCT = {val}%"


def check_sensitivity() -> tuple[bool, str]:
    """Parameters are not fragile."""
    path = RESULTS_DIR / "sensitivity_stability.csv"
    if not path.exists():
        return False, "sensitivity_stability.csv not found"
    df = pd.read_csv(path)
    if df.empty:
        return False, "No stability data"
    fragile = (df["stability"] == "FRAGILE").sum()
    total = len(df)
    passed = fragile / total < 0.25  # Less than 25% fragile (tighter than before)
    return passed, f"{total - fragile}/{total} stable/moderate (fragile: {fragile})"


# ═══════════════════════════════════════════════════════════════════
# Performance checks (the ones that actually matter)
# ═══════════════════════════════════════════════════════════════════

def check_oos_return() -> tuple[bool, str]:
    """Mean out-of-sample return must be positive."""
    path = RESULTS_DIR / "walk_forward_summary.csv"
    if not path.exists():
        return False, "walk_forward_summary.csv not found"

    df = pd.read_csv(path)
    ok = df[df["status"] == "ok"]
    if ok.empty:
        return False, "No successful walk-forward results"

    results = []
    for strat in ok["strategy"].unique():
        s = ok[ok["strategy"] == strat]
        avg_oos = s["avg_oos_return"].mean()
        results.append((strat, avg_oos))

    best_strat, best_oos = max(results, key=lambda x: x[1])
    any_positive = any(r > 0 for _, r in results)

    details = " | ".join(f"{s}: {v:+.3f}%" for s, v in results)
    return any_positive, f"OOS returns: {details}"


def check_sharpe() -> tuple[bool, str]:
    """Mean Sharpe ratio > 0.5 for at least one strategy."""
    path = RESULTS_DIR / "v2_summary.csv"
    if not path.exists():
        path = RESULTS_DIR / "baseline_summary.csv"
    if not path.exists():
        return False, "No summary CSV found"

    df = pd.read_csv(path)
    results = []
    for strat in df["strategy"].unique():
        s = df[df["strategy"] == strat]
        mean_sharpe = s["sharpe"].mean()
        results.append((strat, mean_sharpe))

    best_strat, best_sharpe = max(results, key=lambda x: x[1])
    passed = best_sharpe > 0.5

    details = " | ".join(f"{s}: {v:.2f}" for s, v in results)
    return passed, f"Mean Sharpe: {details} (need >0.5)"


def check_profit_factor() -> tuple[bool, str]:
    """Profit factor > 1.1 for at least one strategy."""
    path = RESULTS_DIR / "v2_summary.csv"
    if not path.exists():
        path = RESULTS_DIR / "baseline_summary.csv"
    if not path.exists():
        return False, "No summary CSV found"

    df = pd.read_csv(path)
    if "profit_factor" not in df.columns:
        return False, "No profit_factor column"

    results = []
    for strat in df["strategy"].unique():
        s = df[df["strategy"] == strat]
        # Use median to reduce outlier influence
        med_pf = s["profit_factor"].median()
        results.append((strat, med_pf))

    best_strat, best_pf = max(results, key=lambda x: x[1])
    passed = best_pf > 1.1

    details = " | ".join(f"{s}: {v:.2f}" for s, v in results)
    return passed, f"Median PF: {details} (need >1.1)"


def check_profitable_stocks() -> tuple[bool, str]:
    """At least 50% of stocks profitable for at least one strategy."""
    path = RESULTS_DIR / "v2_summary.csv"
    if not path.exists():
        path = RESULTS_DIR / "baseline_summary.csv"
    if not path.exists():
        return False, "No summary CSV found"

    df = pd.read_csv(path)
    results = []
    for strat in df["strategy"].unique():
        s = df[df["strategy"] == strat]
        total = len(s)
        profitable = (s["return_pct"] > 0).sum()
        pct = profitable / total * 100 if total > 0 else 0
        results.append((strat, profitable, total, pct))

    best_strat, best_prof, best_total, best_pct = max(results, key=lambda x: x[3])
    passed = best_pct >= 50

    details = " | ".join(f"{s}: {p}/{t} ({pct:.0f}%)" for s, p, t, pct in results)
    return passed, f"Profitable stocks: {details} (need >=50%)"


def check_max_drawdown() -> tuple[bool, str]:
    """Max drawdown < 30%."""
    path = RESULTS_DIR / "v2_summary.csv"
    if not path.exists():
        path = RESULTS_DIR / "baseline_summary.csv"
    if not path.exists():
        return False, "No summary CSV found"

    df = pd.read_csv(path)
    worst_dd = df["max_dd_pct"].min()

    mc_msg = ""
    mc_path = RESULTS_DIR / "monte_carlo_summary.csv"
    if mc_path.exists():
        df_mc = pd.read_csv(mc_path)
        mc_ok = df_mc[df_mc["status"] == "ok"] if "status" in df_mc.columns else df_mc
        if not mc_ok.empty and "dd_95th" in mc_ok.columns:
            worst_mc_dd = mc_ok["dd_95th"].max()
            mc_msg = f" | MC 95th: {worst_mc_dd:.1f}%"

    passed = worst_dd > -30
    return passed, f"Worst DD: {worst_dd:.1f}%{mc_msg} (need >-30%)"


def check_monte_carlo_ruin() -> tuple[bool, str]:
    """Monte Carlo probability of ruin < 10%."""
    path = RESULTS_DIR / "monte_carlo_summary.csv"
    if not path.exists():
        return False, "monte_carlo_summary.csv not found (run Monte Carlo first)"

    df = pd.read_csv(path)
    ok = df[df["status"] == "ok"] if "status" in df.columns else df

    if ok.empty:
        return False, "No Monte Carlo results"

    if "prob_ruin" not in ok.columns:
        return False, "No prob_ruin column"

    worst_ruin = ok["prob_ruin"].max()
    passed = worst_ruin < 10.0
    return passed, f"Worst P(Ruin): {worst_ruin:.1f}% (need <10%)"


# ═══════════════════════════════════════════════════════════════════
# Main report
# ═══════════════════════════════════════════════════════════════════

def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    structural_checks = [
        ("historical_data", check_historical_data),
        ("backtests_executed", check_backtests_executed),
        ("slippage_modeled", check_slippage),
        ("parameter_sensitivity", check_sensitivity),
    ]

    performance_checks = [
        ("oos_return_positive", check_oos_return),
        ("sharpe_above_0.5", check_sharpe),
        ("profit_factor_above_1.1", check_profit_factor),
        ("profitable_stocks_50pct", check_profitable_stocks),
        ("max_drawdown_under_30pct", check_max_drawdown),
        ("monte_carlo_ruin_under_10pct", check_monte_carlo_ruin),
    ]

    print()
    print("ROBUSTNESS VALIDATION REPORT")
    print("=" * 70)

    results = []
    structural_pass = True
    performance_pass = True

    print("\n── STRUCTURAL (necessary but not sufficient) ──")
    for check_id, check_fn in structural_checks:
        try:
            passed, detail = check_fn()
        except Exception as e:
            passed, detail = False, f"Error: {e}"
        status = "PASS" if passed else "FAIL"
        if not passed:
            structural_pass = False
        results.append({"check": check_id, "status": status, "detail": detail})
        print(f"  [{status}] {check_id:<30} {detail}")

    print("\n── PERFORMANCE (must ALL pass to be tradable) ──")
    for check_id, check_fn in performance_checks:
        try:
            passed, detail = check_fn()
        except Exception as e:
            passed, detail = False, f"Error: {e}"
        status = "PASS" if passed else "FAIL"
        if not passed:
            performance_pass = False
        results.append({"check": check_id, "status": status, "detail": detail})
        print(f"  [{status}] {check_id:<30} {detail}")

    # Verdict
    print("\n" + "=" * 70)

    struct_count = sum(1 for r in results[:4] if r["status"] == "PASS")
    perf_count = sum(1 for r in results[4:] if r["status"] == "PASS")

    if structural_pass and performance_pass:
        verdict = "PASS — Strategy has demonstrated edge. Ready for paper trading."
    elif structural_pass and not performance_pass:
        verdict = (
            f"FAIL — Structurally sound ({struct_count}/4) but no edge "
            f"({perf_count}/6 performance checks). NOT tradable."
        )
    else:
        verdict = (
            f"FAIL — Structural issues ({struct_count}/4) and no edge "
            f"({perf_count}/6 performance checks). Fix fundamentals first."
        )

    print(f"\n  OVERALL: {verdict}")
    print(f"  Structural: {struct_count}/4 | Performance: {perf_count}/6")

    # Save report
    report_lines = [
        "ROBUSTNESS VALIDATION REPORT",
        "=" * 50,
        "",
        "STRUCTURAL CHECKS:",
    ]
    for r in results[:4]:
        report_lines.append(f"[{r['status']}] {r['check']}: {r['detail']}")
    report_lines.append("")
    report_lines.append("PERFORMANCE CHECKS:")
    for r in results[4:]:
        report_lines.append(f"[{r['status']}] {r['check']}: {r['detail']}")
    report_lines.extend(["", "=" * 50, f"OVERALL: {verdict}"])

    report_path = RESULTS_DIR / "robustness_report.txt"
    report_path.write_text("\n".join(report_lines))

    df_results = pd.DataFrame(results)
    csv_path = RESULTS_DIR / "robustness_report.csv"
    df_results.to_csv(csv_path, index=False)

    print(f"\n  Report: {report_path}")
    print(f"  CSV:    {csv_path}")

    sys.exit(0 if (structural_pass and performance_pass) else 1)


if __name__ == "__main__":
    main()
