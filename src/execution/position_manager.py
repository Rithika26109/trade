"""
Position Manager
────────────────
Tracks open positions, monitors stop-loss/target hits, and manages exits.
Works in both paper and live modes.
"""

from datetime import datetime
from queue import Queue, Empty

from config import settings
from src.execution.order_manager import Order, OrderManager
from src.strategy.base import Signal
from src.utils.logger import logger


class PositionManager:
    """Monitors open positions and handles exits."""

    def __init__(self, order_manager: OrderManager, db=None):
        self.order_manager = order_manager
        self.db = db
        self.open_positions: list[Order] = []
        self._high_water_marks: dict[str, float] = {}  # order_id → best price
        self.pending_exits: Queue = Queue()  # For WebSocket-driven exits: (order_id, price, reason)

    def add_position(self, order: Order):
        """Track a new open position."""
        self.open_positions.append(order)
        if self.db:
            try:
                self.db.save_open_position(order)
            except Exception as e:
                logger.error(f"Failed to persist open position: {e}")

    def check_exits(self, current_prices: dict[str, float]):
        """
        Check if any open positions have hit their stop-loss or target.
        Processes WebSocket-driven exits first, then polls remaining positions.
        Supports partial profit-taking at 1R, 2R, 3R levels.

        Args:
            current_prices: {"RELIANCE": 2450.50, "INFY": 1520.30, ...}
        """
        # Process any WebSocket-driven exit events first
        self._process_pending_exits(current_prices)

        closed = []
        for pos in self.open_positions:
            price = current_prices.get(pos.symbol)
            if price is None:
                continue

            # Update trailing stop if enabled
            if settings.STOP_LOSS_TYPE == "TRAILING":
                self._update_trailing_stop(pos, price)

            # Check partial exits first (if enabled)
            if getattr(settings, 'ENABLE_PARTIAL_EXITS', False) and pos.original_quantity > 0:
                partial = self._check_partial_exit(pos, price)
                if partial:
                    reason, qty = partial
                    self.order_manager.partial_close(pos, price, qty, reason)
                    if pos.quantity <= 0:
                        closed.append(pos)
                    continue

            exit_reason = self._should_exit(pos, price)
            if exit_reason:
                self.order_manager.close_position(pos, price, exit_reason)
                closed.append(pos)

        # Remove closed positions and clean up
        for pos in closed:
            self.open_positions.remove(pos)
            self._high_water_marks.pop(pos.order_id, None)
            if self.db:
                try:
                    self.db.remove_open_position(pos.order_id)
                except Exception as e:
                    logger.error(f"Failed to remove position from DB: {e}")

    def _process_pending_exits(self, current_prices: dict[str, float]):
        """Drain the WebSocket exit queue and close matching positions."""
        while True:
            try:
                order_id, price, reason = self.pending_exits.get_nowait()
            except Empty:
                break
            for pos in self.open_positions:
                if pos.order_id == order_id:
                    self.order_manager.close_position(pos, price, reason)
                    self.open_positions.remove(pos)
                    self._high_water_marks.pop(pos.order_id, None)
                    if self.db:
                        try:
                            self.db.remove_open_position(pos.order_id)
                        except Exception:
                            pass
                    break

    def _check_partial_exit(self, pos: Order, current_price: float) -> tuple[str, int] | None:
        """
        Check if position should be partially closed at profit-taking levels.
        Returns (reason, quantity_to_close) or None.
        """
        risk = abs(pos.executed_price - pos.stop_loss)
        if risk <= 0:
            return None

        if pos.signal == Signal.BUY:
            current_r = (current_price - pos.executed_price) / risk
        else:
            current_r = (pos.executed_price - current_price) / risk

        # Define scale-out levels
        levels = [
            (1.0, getattr(settings, 'PARTIAL_EXIT_1R_PCT', 40) / 100, "1R"),
            (2.0, getattr(settings, 'PARTIAL_EXIT_2R_PCT', 30) / 100, "2R"),
            (3.0, getattr(settings, 'PARTIAL_EXIT_3R_PCT', 30) / 100, "3R"),
        ]

        for r_level, pct, label in levels:
            if current_r >= r_level:
                already_exited = any(
                    e[2].startswith(f"{label} target") for e in pos.partial_exits
                )
                if not already_exited:
                    qty_to_exit = max(1, int(pos.original_quantity * pct))
                    qty_to_exit = min(qty_to_exit, pos.quantity)

                    # After 1R exit, move stop to breakeven
                    if label == "1R":
                        pos.stop_loss = pos.executed_price
                    elif label == "2R" and pos.signal == Signal.BUY:
                        pos.stop_loss = pos.executed_price + risk  # Trail to 1R
                    elif label == "2R" and pos.signal == Signal.SELL:
                        pos.stop_loss = pos.executed_price - risk

                    return (f"{label} target hit at {current_price:.2f}", qty_to_exit)

        return None

    def _update_trailing_stop(self, pos: Order, current_price: float):
        """Update trailing stop-loss as price moves favorably."""
        hwm = self._high_water_marks.get(pos.order_id, pos.executed_price)
        trail_pct = settings.TRAILING_STOP_PCT / 100

        if pos.signal == Signal.BUY:
            hwm = max(hwm, current_price)
            new_sl = hwm * (1 - trail_pct)
            if new_sl > pos.stop_loss:  # Only tighten, never widen
                pos.stop_loss = new_sl
        else:
            hwm = min(hwm, current_price)
            new_sl = hwm * (1 + trail_pct)
            if new_sl < pos.stop_loss:  # Only tighten, never widen
                pos.stop_loss = new_sl

        self._high_water_marks[pos.order_id] = hwm

    def _should_exit(self, pos: Order, current_price: float) -> str | None:
        """
        Determine if a position should be exited.
        Returns exit reason string or None.
        """
        if pos.signal == Signal.BUY:
            # Long position
            if current_price <= pos.stop_loss:
                return f"Stop-loss hit at {current_price:.2f}"
            if current_price >= pos.target:
                return f"Target hit at {current_price:.2f}"
        else:
            # Short position
            if current_price >= pos.stop_loss:
                return f"Stop-loss hit at {current_price:.2f}"
            if current_price <= pos.target:
                return f"Target hit at {current_price:.2f}"

        return None

    def force_close_all(self, current_prices: dict[str, float], reason: str = "Force square-off"):
        """Close all open positions (end of day or circuit breaker)."""
        if not self.open_positions:
            return
        count = len(self.open_positions)
        for pos in list(self.open_positions):
            price = current_prices.get(pos.symbol, pos.price)
            self.order_manager.close_position(pos, price, reason)
        self.open_positions.clear()
        self._high_water_marks.clear()
        if self.db:
            try:
                self.db.clear_open_positions()
            except Exception as e:
                logger.error(f"Failed to clear open positions from DB: {e}")
        logger.warning(f"Force closed {count} positions: {reason}")

    def get_position_count(self) -> int:
        """Number of currently open positions."""
        return len(self.open_positions)

    def get_position(self, symbol: str) -> Order | None:
        """Get open position for a specific symbol."""
        for pos in self.open_positions:
            if pos.symbol == symbol:
                return pos
        return None

    def has_position(self, symbol: str) -> bool:
        """Check if we have an open position for a symbol."""
        return any(p.symbol == symbol for p in self.open_positions)

    def get_unrealized_pnl(self, current_prices: dict[str, float]) -> float:
        """Calculate total unrealized P&L for all open positions."""
        total = 0.0
        for pos in self.open_positions:
            price = current_prices.get(pos.symbol, pos.executed_price)
            if pos.signal == Signal.BUY:
                total += (price - pos.executed_price) * pos.quantity
            else:
                total += (pos.executed_price - price) * pos.quantity
        return total
