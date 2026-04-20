"""
Trade Database
──────────────
SQLite database for storing all trade history and daily P&L.
This data is used for performance analysis and reporting.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

from config import settings
from src.execution.order_manager import Order
from src.strategy.base import Signal
from src.utils.logger import logger


class TradeDB:
    """SQLite database for trade logging and analysis."""

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or settings.DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Create tables if they don't exist."""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    order_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    exchange TEXT DEFAULT 'NSE',
                    signal TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL DEFAULT 0,
                    stop_loss REAL NOT NULL,
                    target REAL NOT NULL,
                    pnl REAL DEFAULT 0,
                    strategy TEXT NOT NULL,
                    reason TEXT DEFAULT '',
                    is_paper INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS open_positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT UNIQUE NOT NULL,
                    symbol TEXT NOT NULL,
                    exchange TEXT DEFAULT 'NSE',
                    signal TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    target REAL NOT NULL,
                    strategy TEXT NOT NULL,
                    reason TEXT DEFAULT '',
                    is_paper INTEGER DEFAULT 1,
                    opened_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_summary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT UNIQUE NOT NULL,
                    total_trades INTEGER DEFAULT 0,
                    winning_trades INTEGER DEFAULT 0,
                    losing_trades INTEGER DEFAULT 0,
                    total_pnl REAL DEFAULT 0,
                    max_drawdown REAL DEFAULT 0,
                    capital REAL DEFAULT 0,
                    is_paper INTEGER DEFAULT 1
                )
            """)
            # Phase 3E: persisted intraday risk state (HWM / daily-loss)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS risk_state (
                    date TEXT PRIMARY KEY,
                    hwm REAL DEFAULT 0,
                    drawdown REAL DEFAULT 0,
                    daily_loss REAL DEFAULT 0,
                    updated_at TEXT NOT NULL
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def log_trade(self, order: Order):
        """Save a completed trade to the database."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO trades
                (date, order_id, symbol, exchange, signal, quantity, entry_price,
                 exit_price, stop_loss, target, pnl, strategy, reason, is_paper, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(settings.now_ist().date()),
                    order.order_id,
                    order.symbol,
                    order.exchange,
                    order.signal.value,
                    order.quantity if not order.original_quantity else order.original_quantity,
                    order.executed_price,
                    order.exit_price if order.exit_price > 0 else order.executed_price,
                    order.stop_loss,
                    order.target,
                    order.pnl,
                    order.strategy,
                    order.reason,
                    1 if order.is_paper else 0,
                    settings.now_ist().isoformat(),
                ),
            )
        logger.debug(f"Trade logged to DB: {order.order_id} {order.symbol}")

    def save_daily_summary(
        self,
        total_trades: int,
        winning_trades: int,
        losing_trades: int,
        total_pnl: float,
        max_drawdown: float,
        capital: float,
        is_paper: bool = True,
    ):
        """Save end-of-day summary."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO daily_summary
                (date, total_trades, winning_trades, losing_trades, total_pnl,
                 max_drawdown, capital, is_paper)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(settings.now_ist().date()),
                    total_trades,
                    winning_trades,
                    losing_trades,
                    total_pnl,
                    max_drawdown,
                    capital,
                    1 if is_paper else 0,
                ),
            )

    def save_open_position(self, order: Order):
        """Persist an open position for crash recovery."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO open_positions
                (order_id, symbol, exchange, signal, quantity, entry_price,
                 stop_loss, target, strategy, reason, is_paper, opened_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order.order_id, order.symbol, order.exchange,
                    order.signal.value, order.quantity, order.executed_price,
                    order.stop_loss, order.target, order.strategy,
                    order.reason, 1 if order.is_paper else 0,
                    settings.now_ist().isoformat(),
                ),
            )

    def remove_open_position(self, order_id: str):
        """Remove a position after it's been closed."""
        with self._connect() as conn:
            conn.execute("DELETE FROM open_positions WHERE order_id = ?", (order_id,))

    def get_open_positions(self) -> list[dict]:
        """Load open positions from last session (for crash recovery)."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM open_positions").fetchall()
            return [dict(row) for row in rows]

    def clear_open_positions(self):
        """Clear all open positions (end of day)."""
        with self._connect() as conn:
            conn.execute("DELETE FROM open_positions")

    def get_todays_trades(self) -> list[dict]:
        """Get all trades from today."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM trades WHERE date = ? ORDER BY created_at",
                (str(settings.now_ist().date()),),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_daily_summaries(self, days: int = 30) -> list[dict]:
        """Get daily summaries for the last N days."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM daily_summary ORDER BY date DESC LIMIT ?",
                (days,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_overall_stats(self) -> dict:
        """Get overall performance statistics."""
        with self._connect() as conn:
            row = conn.execute("""
                SELECT
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
                    SUM(CASE WHEN pnl = 0 THEN 1 ELSE 0 END) as breakeven,
                    SUM(pnl) as total_pnl,
                    AVG(pnl) as avg_pnl,
                    MAX(pnl) as best_trade,
                    MIN(pnl) as worst_trade
                FROM trades
            """).fetchone()

            total = row[0] or 0
            wins = row[1] or 0
            return {
                "total_trades": total,
                "wins": wins,
                "losses": row[2] or 0,
                "breakeven": row[3] or 0,
                "win_rate": (wins / total * 100) if total > 0 else 0,
                "total_pnl": row[4] or 0,
                "avg_pnl": row[5] or 0,
                "best_trade": row[6] or 0,
                "worst_trade": row[7] or 0,
            }

    # ── Phase 3E helpers ──
    def get_closed_trades(self, limit: int = 200) -> list[dict]:
        """Return most-recent closed trades (pnl != 0) for Kelly/correlation."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT symbol, quantity, entry_price, exit_price, pnl, created_at "
                "FROM trades WHERE pnl != 0 ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def save_risk_state(self, hwm: float, drawdown: float, daily_loss: float) -> None:
        """Persist today's intraday risk state so circuit breakers survive a restart."""
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO risk_state (date, hwm, drawdown, daily_loss, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        str(settings.now_ist().date()),
                        float(hwm),
                        float(drawdown),
                        float(daily_loss),
                        settings.now_ist().isoformat(),
                    ),
                )
        except Exception as e:
            logger.debug(f"save_risk_state failed: {e}")

    def load_risk_state(self) -> dict | None:
        """Load today's risk state if present, else None."""
        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT hwm, drawdown, daily_loss FROM risk_state WHERE date = ?",
                    (str(settings.now_ist().date()),),
                ).fetchone()
                return dict(row) if row else None
        except Exception:
            return None
