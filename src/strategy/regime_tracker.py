"""
Regime Performance Tracker (Phase 3C)
─────────────────────────────────────
Stores (strategy, directional_regime, volatility_regime, pnl, outcome)
per closed trade in SQLite; exposes rolling win-rate & expectancy per cell.

Used by the orchestrator to weight signals by the live edge a given
(strategy, regime) cell has, and to blacklist cells performing below a floor.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from config import settings
from src.utils.logger import logger


class RegimePerformanceTracker:
    """Per-(strategy, dir_regime, vol_regime) rolling performance store."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or settings.DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def _init_db(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS regime_perf (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy TEXT NOT NULL,
                    dir_regime TEXT NOT NULL,
                    vol_regime TEXT NOT NULL,
                    pnl REAL NOT NULL,
                    is_win INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_regime_perf_cell "
                "ON regime_perf (strategy, dir_regime, vol_regime)"
            )

    # ── Writes ──
    def record(
        self,
        strategy: str,
        dir_regime: str,
        vol_regime: str,
        pnl: float,
    ) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO regime_perf (strategy, dir_regime, vol_regime, pnl, is_win, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        strategy,
                        dir_regime,
                        vol_regime,
                        float(pnl),
                        1 if pnl > 0 else 0,
                        settings.now_ist().isoformat(),
                    ),
                )
        except Exception as e:
            logger.debug(f"[RegimeTracker] record failed: {e}")

    # ── Reads ──
    def get_cell_stats(
        self, strategy: str, dir_regime: str, vol_regime: str, window: int | None = None
    ) -> dict:
        """Return rolling stats for the cell: trades, wins, win_rate, avg_pnl, expectancy."""
        window = window or getattr(settings, "REGIME_TRACKER_WINDOW", 100)
        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT pnl, is_win FROM regime_perf "
                    "WHERE strategy=? AND dir_regime=? AND vol_regime=? "
                    "ORDER BY id DESC LIMIT ?",
                    (strategy, dir_regime, vol_regime, window),
                ).fetchall()
        except Exception:
            rows = []

        n = len(rows)
        if n == 0:
            return {
                "trades": 0,
                "wins": 0,
                "win_rate": 0.0,
                "avg_pnl": 0.0,
                "expectancy": 0.0,
            }
        wins = sum(r["is_win"] for r in rows)
        total_pnl = sum(r["pnl"] for r in rows)
        return {
            "trades": n,
            "wins": wins,
            "win_rate": wins / n,
            "avg_pnl": total_pnl / n,
            "expectancy": total_pnl / n,
        }

    def is_blacklisted(self, strategy: str, dir_regime: str, vol_regime: str) -> bool:
        """Return True if cell performs below blacklist floor with enough samples."""
        min_trades = getattr(settings, "REGIME_BLACKLIST_MIN_TRADES", 30)
        floor_wr = getattr(settings, "REGIME_BLACKLIST_WR", 0.40)
        stats = self.get_cell_stats(strategy, dir_regime, vol_regime)
        return stats["trades"] >= min_trades and stats["win_rate"] < floor_wr

    def weight_for(self, strategy: str, dir_regime: str, vol_regime: str) -> float:
        """
        Return a multiplicative weight (0.0 - 2.0) for a (strategy, regime) cell
        to be used for confluence/agreement scoring. Cold-start: 1.0.
        """
        if not getattr(settings, "REGIME_TRACKER_ENABLED", True):
            return 1.0
        if self.is_blacklisted(strategy, dir_regime, vol_regime):
            return 0.0

        min_trades = getattr(settings, "REGIME_TRACKER_MIN_TRADES", 10)
        stats = self.get_cell_stats(strategy, dir_regime, vol_regime)
        if stats["trades"] < min_trades:
            return 1.0  # cold-start

        # Map win_rate [0.3 .. 0.7] → [0.5 .. 1.5], clamp outside
        wr = stats["win_rate"]
        w = 0.5 + (wr - 0.3) / 0.4  # 0.3→0.5, 0.7→1.5
        return max(0.25, min(w, 1.75))
