"""
Stock Scanner — Enhanced
────────────────────────
Professional stock selection with:
- Volume scoring
- Volatility scoring (ATR-based)
- Momentum scoring (5-day and 20-day ROC)
- Relative strength vs NIFTY 50
- Sector strength analysis
- Gap detection for ORB candidates
"""

import pandas as pd

from config import settings
from src.data.market_data import MarketData
from src.risk.sector_map import get_sector, SECTOR_MAP
from src.utils.logger import logger


class StockScanner:
    """Filters watchlist stocks for best intraday candidates."""

    def __init__(self, market_data: MarketData):
        self.market_data = market_data
        self._nifty_return: float | None = None
        self._sector_returns: dict[str, float] = {}

    def scan(self, watchlist: list[str] = None) -> list[str]:
        """
        Scan stocks and return the best candidates for today.
        Uses composite scoring: volume, volatility, momentum, relative strength, sector.
        """
        watchlist = watchlist or settings.WATCHLIST
        candidates = []

        logger.info(f"Scanning {len(watchlist)} stocks...")

        # Pre-fetch NIFTY 50 return for relative strength
        self._fetch_nifty_benchmark()

        for symbol in watchlist:
            try:
                result = self._score_stock(symbol)
                if result is not None:
                    candidates.append(result)
            except Exception as e:
                logger.debug(f"Skipping {symbol}: {e}")

        # Compute sector strength from candidates
        self._compute_sector_strength(candidates)

        # Final composite scoring
        for c in candidates:
            c["total_score"] = self._composite_score(c)

        # Sort by total score (higher is better)
        candidates.sort(key=lambda x: x["total_score"], reverse=True)

        # Drop stocks frozen at circuit today
        if getattr(settings, "SCANNER_DROP_CIRCUIT_FROZEN", True):
            candidates = [c for c in candidates if not self._is_circuit_frozen(c["symbol"])]

        # Optional spread filter (requires live quote; best-effort)
        max_spread_bps = getattr(settings, "SCANNER_MAX_SPREAD_BPS", 0)
        if max_spread_bps > 0:
            candidates = [c for c in candidates if self._spread_ok(c["symbol"], max_spread_bps)]

        # Top-N cutoff
        top_n = getattr(settings, "SCANNER_TOP_N", 0)
        if top_n and top_n > 0:
            candidates = candidates[:top_n]

        selected = [c["symbol"] for c in candidates]

        # Log top candidates with details
        for c in candidates[:5]:
            logger.info(
                f"  {c['symbol']}: score={c['total_score']:.2f} "
                f"(vol={c['volume_score']:.1f}, atr={c['volatility_score']:.1f}, "
                f"mom={c['momentum_score']:.1f}, rs={c['rs_score']:.1f})"
            )

        logger.info(f"Selected {len(selected)} stocks: {selected}")
        return selected

    def _fetch_nifty_benchmark(self):
        """Fetch NIFTY 50 return for relative strength comparison."""
        try:
            df = self.market_data.get_historical_data("NIFTY 50", interval="day", days=25)
            if not df.empty and len(df) >= 20:
                self._nifty_return = (
                    (df["close"].iloc[-1] / df["close"].iloc[-20] - 1) * 100
                )
        except Exception:
            self._nifty_return = None

    def _score_stock(self, symbol: str) -> dict | None:
        """Score a stock across multiple dimensions."""
        df = self.market_data.get_historical_data(symbol, interval="day", days=25)
        if df.empty or len(df) < 5:
            return None

        latest = df.iloc[-1]
        price = latest["close"]

        # Price filter
        if price < settings.MIN_PRICE or price > settings.MAX_PRICE:
            return None

        # Volume filter + score
        avg_volume = df["volume"].tail(5).mean()
        if avg_volume < settings.MIN_VOLUME:
            return None
        volume_score = min(avg_volume / settings.MIN_VOLUME, 5)

        # Turnover filter (Rs crore/day = price * avg_volume / 1e7)
        min_turnover_cr = getattr(settings, "SCANNER_MIN_TURNOVER_CR", 0)
        if min_turnover_cr > 0:
            turnover_cr = (price * avg_volume) / 1e7
            if turnover_cr < min_turnover_cr:
                return None

        # Volatility (ATR) score
        df["tr"] = pd.concat([
            df["high"] - df["low"],
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr = df["tr"].tail(5).mean()
        atr_pct = (atr / price) * 100
        volatility_score = min(atr_pct, 4) if atr_pct >= 0.5 else 0

        # Momentum: 5-day and 20-day rate of change
        roc_5 = (df["close"].iloc[-1] / df["close"].iloc[-5] - 1) * 100 if len(df) >= 5 else 0
        roc_20 = (df["close"].iloc[-1] / df["close"].iloc[-20] - 1) * 100 if len(df) >= 20 else 0
        momentum_score = abs(roc_5 * 0.6 + roc_20 * 0.4)  # Absolute value — we want movers
        momentum_score = min(momentum_score, 5)

        # Relative strength vs NIFTY
        rs_score = 0
        if self._nifty_return is not None and len(df) >= 20:
            stock_return = (df["close"].iloc[-1] / df["close"].iloc[-20] - 1) * 100
            if self._nifty_return != 0:
                rs_ratio = stock_return / abs(self._nifty_return) if self._nifty_return != 0 else 1
                rs_score = min(max(rs_ratio, 0), 3)
            else:
                rs_score = 1.5

        # Gap detection
        gap_pct = 0
        if len(df) >= 2:
            prev_close = df["close"].iloc[-2]
            today_open = df["open"].iloc[-1]
            if prev_close > 0:
                gap_pct = ((today_open - prev_close) / prev_close) * 100

        return {
            "symbol": symbol,
            "price": price,
            "volume_score": volume_score,
            "volatility_score": volatility_score,
            "momentum_score": momentum_score,
            "rs_score": rs_score,
            "sector": get_sector(symbol),
            "gap_pct": gap_pct,
            "sector_score": 0,  # Filled in later
            "total_score": 0,
        }

    def _compute_sector_strength(self, candidates: list[dict]):
        """Compute average momentum per sector and assign sector scores."""
        sector_momentum: dict[str, list[float]] = {}
        for c in candidates:
            sector = c["sector"]
            if sector != "Unknown":
                sector_momentum.setdefault(sector, []).append(c["momentum_score"])

        for sector, scores in sector_momentum.items():
            self._sector_returns[sector] = sum(scores) / len(scores) if scores else 0

        # Assign sector score based on sector's relative strength
        if self._sector_returns:
            max_sector_score = max(self._sector_returns.values()) if self._sector_returns else 1
            for c in candidates:
                sector_avg = self._sector_returns.get(c["sector"], 0)
                c["sector_score"] = (sector_avg / max_sector_score * 3) if max_sector_score > 0 else 0

    def _composite_score(self, candidate: dict) -> float:
        """Weighted composite score."""
        weights = {
            "volume": getattr(settings, 'SCANNER_VOLUME_WEIGHT', 0.20),
            "volatility": getattr(settings, 'SCANNER_VOLATILITY_WEIGHT', 0.20),
            "momentum": getattr(settings, 'SCANNER_MOMENTUM_WEIGHT', 0.25),
            "rs": getattr(settings, 'SCANNER_RS_WEIGHT', 0.20),
            "sector": getattr(settings, 'SCANNER_SECTOR_WEIGHT', 0.15),
        }
        return (
            candidate["volume_score"] * weights["volume"]
            + candidate["volatility_score"] * weights["volatility"]
            + candidate["momentum_score"] * weights["momentum"]
            + candidate["rs_score"] * weights["rs"]
            + candidate["sector_score"] * weights["sector"]
        )

    def _is_circuit_frozen(self, symbol: str) -> bool:
        """Return True if the stock is frozen at today's circuit limit (price == upper/lower)."""
        try:
            band = self.market_data.get_circuit_limits(symbol)
            if not band:
                return False
            # Use last-traded price via quote / LTP helpers
            ltp = None
            if hasattr(self.market_data, "get_ltp"):
                ltp = self.market_data.get_ltp(symbol)
            if ltp is None or ltp <= 0:
                return False
            lo, hi = band["lower"], band["upper"]
            # Within 0.05% of circuit = frozen
            tol = max(0.05, lo * 0.0005)
            return (ltp <= lo + tol) or (ltp >= hi - tol)
        except Exception:
            return False

    def _spread_ok(self, symbol: str, max_bps: float) -> bool:
        """Best-effort bid/ask spread check. Pass-through when data unavailable."""
        try:
            if not hasattr(self.market_data, "get_quote"):
                return True
            q = self.market_data.get_quote(symbol)
            if not q:
                return True
            depth = q.get("depth") or {}
            bids = depth.get("buy") or []
            asks = depth.get("sell") or []
            if not bids or not asks:
                return True
            best_bid = bids[0].get("price", 0)
            best_ask = asks[0].get("price", 0)
            if best_bid <= 0 or best_ask <= 0:
                return True
            mid = (best_bid + best_ask) / 2
            spread_bps = (best_ask - best_bid) / mid * 10000
            return spread_bps <= max_bps
        except Exception:
            return True
