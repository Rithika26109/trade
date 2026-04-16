"""
Order Manager
─────────────
Places, modifies, and cancels orders on Zerodha.
Supports both LIVE and PAPER trading modes.
In paper mode, orders are simulated and logged — no real money involved.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from queue import Queue

from kiteconnect import KiteConnect

from config import settings
from src.strategy.base import Signal, TradeSignal
from src.utils.logger import logger


class OrderStatus(Enum):
    PENDING = "PENDING"
    EXECUTED = "EXECUTED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass
class Order:
    """Represents a single order (real or paper)."""
    order_id: str
    symbol: str
    exchange: str
    signal: Signal  # BUY or SELL
    quantity: int
    price: float
    stop_loss: float
    target: float
    order_type: str  # MARKET, LIMIT, SL
    status: OrderStatus = OrderStatus.PENDING
    executed_price: float = 0.0
    executed_at: datetime | None = None
    exit_price: float = 0.0
    pnl: float = 0.0
    reason: str = ""
    strategy: str = ""
    is_paper: bool = True
    is_open: bool = True
    original_quantity: int = 0  # For partial exits: initial full quantity
    partial_exits: list = field(default_factory=list)  # [(price, qty, reason)]


class OrderManager:
    """Manages order placement for both live and paper trading."""

    def __init__(self, kite: KiteConnect | None = None):
        self.kite = kite
        self.is_paper = settings.TRADING_MODE == "paper"
        self._paper_order_counter = 0
        self.orders: list[Order] = []

    def place_order(self, signal: TradeSignal, exchange: str = "NSE") -> Order | None:
        """
        Place a trade based on a TradeSignal.

        In paper mode: simulates the order and logs it.
        In live mode: places a real order on Zerodha.
        """
        if signal.signal == Signal.HOLD:
            return None

        if signal.quantity <= 0:
            logger.warning(f"Cannot place order with quantity {signal.quantity}")
            return None

        if self.is_paper:
            return self._place_paper_order(signal, exchange)
        else:
            return self._place_live_order(signal, exchange)

    def _place_paper_order(self, signal: TradeSignal, exchange: str) -> Order:
        """Simulate an order with realistic slippage (paper trading)."""
        self._paper_order_counter += 1
        order_id = f"PAPER-{self._paper_order_counter:06d}"

        # Simulate slippage: buys fill slightly higher, sells slightly lower
        slippage = signal.price * (settings.PAPER_SLIPPAGE_PCT / 100)
        if signal.signal == Signal.BUY:
            executed_price = signal.price + slippage
        else:
            executed_price = signal.price - slippage

        order = Order(
            order_id=order_id,
            symbol=signal.symbol,
            exchange=exchange,
            signal=signal.signal,
            quantity=signal.quantity,
            price=signal.price,
            stop_loss=signal.stop_loss,
            target=signal.target,
            order_type="MARKET",
            status=OrderStatus.EXECUTED,
            executed_price=executed_price,
            executed_at=settings.now_ist(),
            reason=signal.reason,
            strategy=signal.strategy,
            is_paper=True,
        )

        order.original_quantity = order.quantity
        self.orders.append(order)

        action = "BUY" if signal.signal == Signal.BUY else "SELL"
        logger.info(
            f"[PAPER] {action} {signal.symbol} | "
            f"Qty: {signal.quantity} | Price: {signal.price:.2f} | "
            f"SL: {signal.stop_loss:.2f} | Target: {signal.target:.2f} | "
            f"Reason: {signal.reason}"
        )
        return order

    def _place_live_order(self, signal: TradeSignal, exchange: str) -> Order | None:
        """Place a real order on Zerodha."""
        if not self.kite:
            logger.error("KiteConnect not initialized for live trading")
            return None

        try:
            transaction_type = (
                self.kite.TRANSACTION_TYPE_BUY
                if signal.signal == Signal.BUY
                else self.kite.TRANSACTION_TYPE_SELL
            )

            # Place main order (market order for immediate fill)
            order_id = self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange=f"{exchange}",
                tradingsymbol=signal.symbol,
                transaction_type=transaction_type,
                quantity=signal.quantity,
                product=self.kite.PRODUCT_MIS,  # Intraday
                order_type=self.kite.ORDER_TYPE_MARKET,
            )

            # Verify order execution and get actual fill price
            fill = self._verify_order(str(order_id))
            actual_price = fill["price"] if fill else signal.price
            actual_qty = fill["quantity"] if fill else signal.quantity

            order = Order(
                order_id=str(order_id),
                symbol=signal.symbol,
                exchange=exchange,
                signal=signal.signal,
                quantity=actual_qty,
                price=signal.price,
                stop_loss=signal.stop_loss,
                target=signal.target,
                order_type="MARKET",
                status=OrderStatus.EXECUTED if fill else OrderStatus.REJECTED,
                executed_price=actual_price,
                executed_at=settings.now_ist(),
                reason=signal.reason,
                strategy=signal.strategy,
                is_paper=False,
            )

            if not fill:
                logger.error(f"Order {order_id} for {signal.symbol} was not filled!")
                return None

            order.original_quantity = order.quantity
            self.orders.append(order)

            action = "BUY" if signal.signal == Signal.BUY else "SELL"
            logger.info(
                f"[LIVE] {action} {signal.symbol} | "
                f"Order ID: {order_id} | Qty: {signal.quantity} | "
                f"Reason: {signal.reason}"
            )

            # Place stop-loss order
            self._place_stop_loss(signal, exchange)

            return order

        except Exception as e:
            logger.error(f"Order placement failed for {signal.symbol}: {e}")
            return None

    def _verify_order(self, order_id: str, max_wait: int = 10) -> dict | None:
        """Poll Zerodha for order execution status and actual fill price."""
        import time as _time
        for _ in range(max_wait):
            try:
                history = self.kite.order_history(order_id)
                latest = history[-1]
                if latest["status"] == "COMPLETE":
                    return {
                        "price": latest["average_price"],
                        "quantity": latest["filled_quantity"],
                    }
                elif latest["status"] in ("REJECTED", "CANCELLED"):
                    logger.warning(f"Order {order_id} was {latest['status']}: {latest.get('status_message', '')}")
                    return None
            except Exception:
                pass
            _time.sleep(1)
        logger.warning(f"Order {order_id} verification timed out after {max_wait}s")
        return None

    def _place_stop_loss(self, signal: TradeSignal, exchange: str):
        """Place a stop-loss order for an executed trade."""
        if not self.kite or self.is_paper:
            return

        try:
            # Stop-loss is the reverse of the entry
            sl_transaction = (
                self.kite.TRANSACTION_TYPE_SELL
                if signal.signal == Signal.BUY
                else self.kite.TRANSACTION_TYPE_BUY
            )

            self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange=exchange,
                tradingsymbol=signal.symbol,
                transaction_type=sl_transaction,
                quantity=signal.quantity,
                product=self.kite.PRODUCT_MIS,
                order_type=self.kite.ORDER_TYPE_SLM,
                trigger_price=signal.stop_loss,
            )
            logger.info(f"Stop-loss placed for {signal.symbol} at {signal.stop_loss:.2f}")
        except Exception as e:
            logger.error(f"Stop-loss placement failed for {signal.symbol}: {e}")

    def close_position(self, order: Order, exit_price: float, reason: str = ""):
        """Close an open position (for paper or live)."""
        if self.is_paper:
            self._close_paper_position(order, exit_price, reason)
        else:
            self._close_live_position(order, exit_price, reason)

    def _close_paper_position(self, order: Order, exit_price: float, reason: str):
        """Close a paper position and calculate P&L."""
        order.exit_price = exit_price
        if order.signal == Signal.BUY:
            order.pnl = (exit_price - order.executed_price) * order.quantity
        else:
            order.pnl = (order.executed_price - exit_price) * order.quantity

        order.status = OrderStatus.EXECUTED
        order.is_open = False
        logger.info(
            f"[PAPER] CLOSED {order.symbol} | "
            f"Entry: {order.executed_price:.2f} | Exit: {exit_price:.2f} | "
            f"P&L: Rs {order.pnl:.2f} | {reason}"
        )

    def _close_live_position(self, order: Order, exit_price: float, reason: str):
        """Close a live position on Zerodha."""
        if not self.kite:
            return

        try:
            close_transaction = (
                self.kite.TRANSACTION_TYPE_SELL
                if order.signal == Signal.BUY
                else self.kite.TRANSACTION_TYPE_BUY
            )

            self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange=order.exchange,
                tradingsymbol=order.symbol,
                transaction_type=close_transaction,
                quantity=order.quantity,
                product=self.kite.PRODUCT_MIS,
                order_type=self.kite.ORDER_TYPE_MARKET,
            )

            order.exit_price = exit_price
            if order.signal == Signal.BUY:
                order.pnl = (exit_price - order.executed_price) * order.quantity
            else:
                order.pnl = (order.executed_price - exit_price) * order.quantity

            order.is_open = False
            logger.info(
                f"[LIVE] CLOSED {order.symbol} | "
                f"Entry: {order.executed_price:.2f} | Exit: {exit_price:.2f} | "
                f"P&L: Rs {order.pnl:.2f} | {reason}"
            )
        except Exception as e:
            logger.error(f"Failed to close position for {order.symbol}: {e}")

    def partial_close(self, order: Order, exit_price: float, quantity: int, reason: str):
        """Close a partial quantity of an open position."""
        if quantity <= 0 or quantity > order.quantity:
            return

        # Calculate P&L for the partial close
        if order.signal == Signal.BUY:
            partial_pnl = (exit_price - order.executed_price) * quantity
        else:
            partial_pnl = (order.executed_price - exit_price) * quantity

        # Record partial exit
        order.partial_exits.append((exit_price, quantity, reason))
        order.pnl += partial_pnl
        order.quantity -= quantity

        # If fully closed
        if order.quantity <= 0:
            order.exit_price = exit_price
            order.is_open = False

        mode = "PAPER" if order.is_paper else "LIVE"
        logger.info(
            f"[{mode}] PARTIAL CLOSE {order.symbol} | "
            f"Qty: {quantity} @ {exit_price:.2f} | "
            f"P&L: Rs {partial_pnl:+.2f} | Remaining: {order.quantity} | {reason}"
        )

        if self.is_paper:
            return  # Paper mode: just update in-memory

        # Live mode: place partial exit order on Zerodha
        if self.kite:
            try:
                close_transaction = (
                    self.kite.TRANSACTION_TYPE_SELL
                    if order.signal == Signal.BUY
                    else self.kite.TRANSACTION_TYPE_BUY
                )
                self.kite.place_order(
                    variety=self.kite.VARIETY_REGULAR,
                    exchange=order.exchange,
                    tradingsymbol=order.symbol,
                    transaction_type=close_transaction,
                    quantity=quantity,
                    product=self.kite.PRODUCT_MIS,
                    order_type=self.kite.ORDER_TYPE_MARKET,
                )
            except Exception as e:
                logger.error(f"Partial close order failed for {order.symbol}: {e}")

    def get_open_orders(self) -> list[Order]:
        """Get all open (unexited) orders from today."""
        return [o for o in self.orders if o.status == OrderStatus.EXECUTED and o.is_open]

    def get_todays_pnl(self) -> float:
        """Total P&L for today across all closed trades."""
        return sum(o.pnl for o in self.orders)

    def get_todays_trade_count(self) -> int:
        """Number of trades placed today."""
        return len(self.orders)
