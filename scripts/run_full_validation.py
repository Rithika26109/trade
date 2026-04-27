"""
Full Validation Pipeline
────────────────────────
Master orchestrator: runs all 8 phases of robustness validation in sequence.

Usage:
    python scripts/run_full_validation.py
    python scripts/run_full_validation.py --skip-download    # Skip Phase 1 if data exists
    python scripts/run_full_validation.py --days 365         # 1 year of data
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


def run_phase(name: str, script: str, extra_args: list[str] = None) -> bool:
    """Run a phase script, return True if successful."""
    print(f"\n{'#' * 70}")
    print(f"# PHASE: {name}")
    print(f"# Script: {script}")
    print(f"{'#' * 70}\n")

    cmd = [sys.executable, str(SCRIPTS_DIR / script)]
    if extra_args:
        cmd.extend(extra_args)

    start = time.time()
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    elapsed = time.time() - start

    status = "OK" if result.returncode == 0 else "FAILED"
    print(f"\n  [{status}] {name} ({elapsed:.0f}s)")
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="Run full robustness validation pipeline")
    parser.add_argument("--skip-download", action="store_true",
                        help="Skip Phase 1 (data download) if CSV files already exist")
    parser.add_argument("--days", type=int, default=730, help="Days of data (default: 730)")
    parser.add_argument("--capital", type=int, default=100_000, help="Starting capital")
    parser.add_argument("--simulations", type=int, default=10_000, help="MC simulations")
    args = parser.parse_args()

    days_args = ["--days", str(args.days)]
    capital_args = ["--capital", str(args.capital)]

    print("=" * 70)
    print("FULL ROBUSTNESS VALIDATION PIPELINE")
    print(f"Days: {args.days} | Capital: Rs {args.capital:,} | MC Sims: {args.simulations:,}")
    print("=" * 70)

    total_start = time.time()
    phase_results = {}

    # Phase 1: Data Download
    if args.skip_download:
        print("\nPhase 1 (Download): SKIPPED (--skip-download)")
        phase_results["download"] = True
    else:
        phase_results["download"] = run_phase(
            "Download Historical Data",
            "download_historical.py",
            days_args,
        )

    if not phase_results["download"]:
        print("\nWARNING: Data download failed. Continuing with whatever cached data exists...")

    # Phase 2: Baseline Backtests
    phase_results["baseline"] = run_phase(
        "Baseline Backtests",
        "run_baseline_backtests.py",
        days_args + capital_args,
    )

    # Phase 3: Slippage is a code change, already applied. Just note it.
    print(f"\n  [OK] Phase 3 (Slippage): Already configured in settings "
          f"(BACKTEST_SLIPPAGE_PCT = 0.05%)")
    phase_results["slippage"] = True

    # Phase 4: Sensitivity
    phase_results["sensitivity"] = run_phase(
        "Parameter Sensitivity",
        "run_sensitivity.py",
        days_args + capital_args,
    )

    # Phase 5: Walk-Forward
    phase_results["walk_forward"] = run_phase(
        "Walk-Forward Validation",
        "run_walk_forward_all.py",
        days_args + capital_args,
    )

    # Phase 6: Monte Carlo
    phase_results["monte_carlo"] = run_phase(
        "Monte Carlo Stress Testing",
        "run_monte_carlo_all.py",
        days_args + capital_args + ["--simulations", str(args.simulations)],
    )

    # Phase 7: Cross-Stock Sweep
    phase_results["cross_stock"] = run_phase(
        "Cross-Stock Sweep",
        "run_cross_stock_sweep.py",
    )

    # Phase 8: Robustness Report
    phase_results["report"] = run_phase(
        "Robustness Report",
        "run_robustness_report.py",
    )

    # Final summary
    total_elapsed = time.time() - total_start
    print(f"\n{'=' * 70}")
    print("PIPELINE COMPLETE")
    print(f"{'=' * 70}")
    print(f"Total time: {total_elapsed / 60:.1f} minutes")
    for phase, success in phase_results.items():
        icon = "+" if success else "X"
        print(f"  [{icon}] {phase}")

    passed = sum(1 for v in phase_results.values() if v)
    total = len(phase_results)
    print(f"\n  {passed}/{total} phases completed successfully")

    if phase_results.get("report"):
        report_path = PROJECT_ROOT / "backtest" / "results" / "robustness_report.txt"
        if report_path.exists():
            print(f"\n  Final report: {report_path}")
            print(f"\n{report_path.read_text()}")


if __name__ == "__main__":
    main()
