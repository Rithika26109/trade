"""
Position Manager
────────────────
Tracks open positions, monitors stop-loss/target hits, and manages exits.
Works in both paper and live modes.
"""

from datetime import datetime, time as dtime
from queue import Queue, Empty

from config import settings
from src.execution.order_manager import Order, OrderManager
from src.strategy.base import Signal
from src.utils.logger import logger

# Time-decay: tighten stops after this time (matches backtest)
_MID_SESSION_TIME = dtime(13, 0)
_LATE_SESSION_TIME = dtime(14, 30)


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
            # Position may have been closed externally (e.g., broker SLM
            # fired, surfaced via WebSocket on_order_update). Reap it.
            if not pos.is_open:
                closed.append(pos)
                continue

            price = current_prices.get(pos.symbol)
            if price is None:
                continue

            # Update trailing stop if enabled
            if settings.STOP_LOSS_TYPE == "TRAILING":
                prev_sl = pos.stop_loss
                self._update_trailing_stop(pos, price)
                # If broker SLM is active and trailing tightened, modify it.
                if (
                    not getattr(pos, "is_paper", True)
                    and getattr(pos, "sl_order_id", None)
                    and pos.stop_loss != prev_sl
                ):
                    self._modify_broker_slm_trigger(pos)

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
                        except Exception as e:
                            logger.error(
                                f"[POS] Failed to remove WebSocket-exited position "
                                f"{pos.symbol} from DB: {e} — may ghost on restart"
                            )
                    break

    def _check_partial_exit(self, pos: Order, current_price: float) -> tuple[str, int] | None:
        """
        Check if position should be partially closed at profit-taking levels.
        Returns (reason, quantity_to_close) or None.

        Uses the *original* risk (entry - initial stop) as the R-unit so that
        moving the stop to breakeven after 1R does not re-compute R and
        falsely re-fire the 2R/3R triggers.
        """
        # Use the ORIGINAL risk captured at entry, not the (possibly trailed)
        # current stop. We infer original risk from the first partial_exits
        # if available; otherwise from the current stop.
        original_sl = getattr(pos, "_original_stop_loss", None)
        if original_sl is None:
            original_sl = pos.stop_loss
            try:
                pos._original_stop_loss = original_sl
            except Exception:
                pass
        risk = abs(pos.executed_price - original_sl)
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

    def _modify_broker_slm_trigger(self, pos: Order):
        """Modify the broker-side SLM trigger to match the trailed stop."""
        om = self.order_manager
        if not om.kite or om.is_paper or not pos.sl_order_id:
            return
        try:
            om._broker_call(
                f"modify_SLM_trigger({pos.symbol} -> {pos.stop_loss:.2f})",
                lambda: om.kite.modify_order(
                    variety=om.kite.VARIETY_REGULAR,
                    order_id=pos.sl_order_id,
                    trigger_price=pos.stop_loss,
                ),
            )
        except Exception as e:
            logger.error(f"modify_SLM_trigger failed for {pos.symbol}: {e}")

    def _update_trailing_stop(self, pos: Order, current_price: float):
        """ATR-based trailing stop matching backtest logic exactly.

        - At 1×ATR profit: move stop to breakeven
        - At 1.5×ATR profit: lock in 0.5×ATR profit
        - Late session (after 14:30): tighten to 1×ATR from current price

        Falls back to percentage-based trailing if entry_atr is not set.
        """
        entry_atr = getattr(pos, 'entry_atr', 0.0)

        if entry_atr <= 0:
            # Fallback: simple percentage trailing for legacy orders
            hwm = self._high_water_marks.get(pos.order_id, pos.executed_price)
            trail_pct = settings.TRAILING_STOP_PCT / 100
            if pos.signal == Signal.BUY:
                hwm = max(hwm, current_price)
                new_sl = hwm * (1 - trail_pct)
                if new_sl > pos.stop_loss:
                    pos.stop_loss = new_sl
            else:
                hwm = min(hwm, current_price)
                new_sl = hwm * (1 + trail_pct)
                if new_sl < pos.stop_loss:
                    pos.stop_loss = new_sl
            self._high_water_marks[pos.order_id] = hwm
            return

        # ── ATR-based trailing (matches backtest) ──
        # Check session phase for time-decay
        mid_session = False
        late_session = False
        try:
            now_time = settings.now_ist().time()
            mid_session = now_time >= _MID_SESSION_TIME
            late_session = now_time >= _LATE_SESSION_TIME
        except Exception as e:
            logger.debug(f"[POS] Time check for session phase failed: {e}")

        if pos.signal == Signal.BUY:
            profit = current_price - pos.executed_price
            # Trail: breakeven at 1x ATR, lock profit above that
            if profit >= 2.0 * entry_atr:
                pos.stop_loss = max(pos.stop_loss, pos.executed_price + 1.0 * entry_atr)
            elif profit >= 1.5 * entry_atr:
                pos.stop_loss = max(pos.stop_loss, pos.executed_price + 0.5 * entry_atr)
            elif profit >= 1.0 * entry_atr:
                pos.stop_loss = max(pos.stop_loss, pos.executed_price)  # breakeven
            # Time-decay: tighten in afternoon
            if late_session:
                time_sl = current_price - (1.0 * entry_atr)
                pos.stop_loss = max(pos.stop_loss, time_sl)
            elif mid_session:
                time_sl = current_price - (1.5 * entry_atr)
                pos.stop_loss = max(pos.stop_loss, time_sl)
        else:
            profit = pos.executed_price - current_price
            if profit >= 2.0 * entry_atr:
                pos.stop_loss = min(pos.stop_loss, pos.executed_price - 1.0 * entry_atr)
            elif profit >= 1.5 * entry_atr:
                pos.stop_loss = min(pos.stop_loss, pos.executed_price - 0.5 * entry_atr)
            elif profit >= 1.0 * entry_atr:
                pos.stop_loss = min(pos.stop_loss, pos.executed_price)  # breakeven
            if late_session:
                time_sl = current_price + (1.0 * entry_atr)
                pos.stop_loss = min(pos.stop_loss, time_sl)
            elif mid_session:
                time_sl = current_price + (1.5 * entry_atr)
                pos.stop_loss = min(pos.stop_loss, time_sl)

    def _should_exit(self, pos: Order, current_price: float) -> str | None:
        """
        Determine if a position should be exited.
        Returns exit reason string or None.

        When a broker-side SLM is active (pos.sl_order_id set) AND the bot
        is in live mode, the stop-loss leg is delegated entirely to the
        exchange to prevent double-exit (software close + SLM trigger →
        reverse position). Only target and other non-SL exits run here.
        """
        broker_stop_active = (
            not getattr(pos, "is_paper", True) and getattr(pos, "sl_order_id", None)
        )
        if pos.signal == Signal.BUY:
            # Long position
            if not broker_stop_active and current_price <= pos.stop_loss:
                return f"Stop-loss hit at {current_price:.2f}"
            if current_price >= pos.target:
                return f"Target hit at {current_price:.2f}"
        else:
            # Short position
            if not broker_stop_active and current_price >= pos.stop_loss:
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
