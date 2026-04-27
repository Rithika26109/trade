"""
Download Historical Data
────────────────────────
Download and cache 2 years of 5-min candle data for all watchlist stocks.
Supports incremental updates (only downloads missing date ranges).

Usage:
    python scripts/download_historical.py                   # All watchlist stocks
    python scripts/download_historical.py --symbol INFY     # Single stock
    python scripts/download_historical.py --days 365        # 1 year instead of 2
    python scripts/download_historical.py --force           # Re-download even if cached
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from config import settings


def download_stock(md, symbol: str, days: int, force: bool = False) -> dict:
    """Download historical data for one stock. Returns status dict."""
    csv_path = settings.HISTORICAL_DATA_DIR / f"{symbol}_5min.csv"
    result = {"symbol": symbol, "status": "unknown", "rows": 0, "date_range": ""}

    # Check existing cache
    if csv_path.exists() and not force:
        existing = pd.read_csv(csv_path, parse_dates=["Date"], nrows=5)
        if len(existing) > 0:
            # Read full file to check date range
            existing = pd.read_csv(csv_path, parse_dates=["Date"])
            last_date = existing["Date"].max()
            first_date = existing["Date"].min()
            total_days = (last_date - first_date).days

            if total_days >= days * 0.8:  # Within 80% of requested range
                result["status"] = "cached"
                result["rows"] = len(existing)
                result["date_range"] = f"{first_date.date()} to {last_date.date()}"
                print(f"  {symbol}: Already cached ({len(existing)} rows, {first_date.date()} to {last_date.date()})")
                return result

    # Download from Zerodha
    print(f"  {symbol}: Downloading {days} days of 5-min data...")
    try:
        df = md.get_historical_data(symbol, interval="5minute", days=days)
        if df.empty:
            result["status"] = "no_data"
            print(f"  {symbol}: No data returned from API")
            return result

        # Filter to market hours (9:15 - 15:30 IST)
        df["hour_min"] = df["date"].dt.hour * 60 + df["date"].dt.minute
        df = df[(df["hour_min"] >= 555) & (df["hour_min"] <= 930)]  # 9:15 - 15:30
        df = df.drop(columns=["hour_min"])

        # Rename columns to match backtest format
        df = df.rename(columns={
            "date": "Date", "open": "Open", "high": "High",
            "low": "Low", "close": "Close", "volume": "Volume"
        })

        # Ensure directory exists
        csv_path.parent.mkdir(parents=True, exist_ok=True)

        # Save
        df.to_csv(csv_path, index=False)
        result["status"] = "downloaded"
        result["rows"] = len(df)
        result["date_range"] = f"{df['Date'].min()} to {df['Date'].max()}"
        print(f"  {symbol}: Saved {len(df)} candles ({df['Date'].min()} to {df['Date'].max()})")
        return result

    except Exception as e:
        result["status"] = f"error: {e}"
        print(f"  {symbol}: ERROR - {e}")
        return result


def main():
    parser = argparse.ArgumentParser(description="Download historical data for backtesting")
    parser.add_argument("--symbol", help="Download single stock (default: all watchlist)")
    parser.add_argument("--days", type=int, default=730, help="Days of data (default: 730 = 2 years)")
    parser.add_argument("--force", action="store_true", help="Re-download even if cached")
    args = parser.parse_args()

    # Authenticate
    print("Authenticating with Zerodha...")
    try:
        from src.auth.login import ZerodhaAuth
        from src.data.market_data import MarketData

        auth = ZerodhaAuth()
        kite = auth.login()
        md = MarketData(kite)
        md.load_instruments("NSE")
        print("Authenticated successfully.\n")
    except Exception as e:
        print(f"Authentication failed: {e}")
        print("Ensure your Kite token is valid (run scripts/refresh_kite_token.py).")
        sys.exit(1)

    # Determine stocks to download
    symbols = [args.symbol] if args.symbol else settings.WATCHLIST
    print(f"Downloading {args.days} days of 5-min data for {len(symbols)} stock(s):\n")

    results = []
    for i, symbol in enumerate(symbols):
        result = download_stock(md, symbol, args.days, args.force)
        results.append(result)
        # Brief pause between stocks to be nice to the API
        if i < len(symbols) - 1:
            time.sleep(1)

    # Summary
    print("\n" + "=" * 60)
    print("DOWNLOAD SUMMARY")
    print("=" * 60)
    for r in results:
        status_icon = {"downloaded": "+", "cached": "=", "no_data": "!", "unknown": "?"}.get(
            r["status"], "X" if "error" in r["status"] else "?"
        )
        print(f"  [{status_icon}] {r['symbol']:<12} {r['rows']:>8} rows  {r['status']}")

    downloaded = sum(1 for r in results if r["status"] in ("downloaded", "cached"))
    failed = len(results) - downloaded
    print(f"\n  {downloaded}/{len(results)} stocks ready", end="")
    if failed:
        print(f" ({failed} failed)")
    else:
        print()

    # Validate minimum data
    print("\nVALIDATION:")
    # ~75 candles/day x 244 trading days/year = ~18,300 rows/year
    min_rows = 15_000  # ~10 months minimum
    for r in results:
        if r["rows"] < min_rows and r["status"] in ("downloaded", "cached"):
            print(f"  WARNING: {r['symbol']} has only {r['rows']} rows (want {min_rows:,}+ for ~1 year)")
        elif r["rows"] >= min_rows:
            print(f"  OK: {r['symbol']} has {r['rows']:,} rows")


if __name__ == "__main__":
    main()
