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
from src.utils.audit import audit
from src.utils.logger import logger
from src.utils import kill_switch
from src.utils.rate_limiter import RateLimiter
from src.utils.retry import retry_with_backoff
from src.utils.tick_size import round_to_tick


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
    # Broker-side stop-loss order tracking. When set, the software-based
    # price-stop in PositionManager MUST be suppressed to avoid double-exit.
    sl_order_id: str | None = None
    tick_size: float = 0.05


class OrderManager:
    """Manages order placement for both live and paper trading."""

    def __init__(self, kite: KiteConnect | None = None, market_data=None):
        self.kite = kite
        self.market_data = market_data  # optional, used for tick_size lookup
        self.is_paper = settings.TRADING_MODE == "paper"
        self._paper_order_counter = 0
        self.orders: list[Order] = []
        # SEBI compliance: cap order rate to stay under the 10/s limit.
        self._order_rate_limiter = RateLimiter(
            max_calls=getattr(settings, "ORDER_RATE_LIMIT_PER_SEC", 8),
            period=1.0,
        )

    # ── Broker retry helpers ──────────────────────────────────────────────
    def _broker_call(self, label: str, fn):
        """Wrap a broker call with rate-limit + retry/backoff. Returns result or None."""
        self._order_rate_limiter.wait()
        return retry_with_backoff(
            fn,
            max_attempts=getattr(settings, "BROKER_RETRY_ATTEMPTS", 3),
            initial_delay=getattr(settings, "BROKER_RETRY_INITIAL_DELAY", 0.5),
            label=label,
        )

    def _tick_size_for(self, symbol: str, exchange: str) -> float:
        if self.market_data is not None:
            try:
                return self.market_data.get_tick_size(symbol, exchange)
            except Exception:
                pass
        return 0.05

    def _algo_tag(self) -> str | None:
        tag = getattr(settings, "ALGO_ID", "") or ""
        return tag[:20] if tag else None  # Kite tag max 20 chars

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

        # Re-check kill-switch at submission point (TOCTOU hardening): the
        # caller may have decided to trade earlier in the cycle, but the
        # operator could have engaged the switch between decision and submit.
        if kill_switch.is_engaged():
            audit(
                "order_blocked_kill_switch",
                symbol=signal.symbol,
                side=("BUY" if signal.signal == Signal.BUY else "SELL"),
                qty=signal.quantity,
            )
            logger.warning(
                f"Kill-switch engaged; refusing to place order for {signal.symbol}."
            )
            return None

        # Round stop-loss and target to the instrument's tick size. Choose
        # the rounding direction that is conservative for the trader:
        # a BUY's stop should round UP (tighter, smaller loss) and target
        # should round DOWN (closer, more likely to fill). Mirror for SELL.
        tick = self._tick_size_for(signal.symbol, exchange)
        if signal.signal == Signal.BUY:
            signal.stop_loss = round_to_tick(signal.stop_loss, tick, mode="ceil")
            signal.target = round_to_tick(signal.target, tick, mode="floor")
        else:
            signal.stop_loss = round_to_tick(signal.stop_loss, tick, mode="floor")
            signal.target = round_to_tick(signal.target, tick, mode="ceil")

        if self.is_paper:
            return self._place_paper_order(signal, exchange, tick)
        else:
            return self._place_live_order(signal, exchange, tick)

    def _place_paper_order(self, signal: TradeSignal, exchange: str, tick: float = 0.05) -> Order:
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
        order.tick_size = tick
        self.orders.append(order)

        action = "BUY" if signal.signal == Signal.BUY else "SELL"
        logger.info(
            f"[PAPER] {action} {signal.symbol} | "
            f"Qty: {signal.quantity} | Price: {signal.price:.2f} | "
            f"SL: {signal.stop_loss:.2f} | Target: {signal.target:.2f} | "
            f"Reason: {signal.reason}"
        )
        audit(
            "order_place",
            order_id=order_id,
            symbol=signal.symbol,
            side=action,
            qty=signal.quantity,
            price=signal.price,
            executed_price=executed_price,
            sl=signal.stop_loss,
            target=signal.target,
            strategy=signal.strategy,
            reason=signal.reason,
            paper=True,
        )
        return order

    def _place_live_order(self, signal: TradeSignal, exchange: str, tick: float = 0.05) -> Order | None:
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

            tag = self._algo_tag()
            place_kwargs = dict(
                variety=self.kite.VARIETY_REGULAR,
                exchange=f"{exchange}",
                tradingsymbol=signal.symbol,
                transaction_type=transaction_type,
                quantity=signal.quantity,
                product=self.kite.PRODUCT_MIS,  # Intraday
                order_type=self.kite.ORDER_TYPE_MARKET,
            )
            if tag:
                place_kwargs["tag"] = tag

            # Place main order with retry/backoff (idempotency guarded by tag
            # + the _verify_order check; Kite rejects duplicate tags within
            # a session for the same side/symbol).
            order_id = self._broker_call(
                f"place_order({signal.symbol} {signal.signal.value})",
                lambda: self.kite.place_order(**place_kwargs),
            )
            if order_id is None:
                logger.error(f"Order placement returned None for {signal.symbol}")
                return None

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
            order.tick_size = tick
            self.orders.append(order)

            action = "BUY" if signal.signal == Signal.BUY else "SELL"
            logger.info(
                f"[LIVE] {action} {signal.symbol} | "
                f"Order ID: {order_id} | Qty: {signal.quantity} | "
                f"Reason: {signal.reason}"
            )
            audit(
                "order_place",
                order_id=str(order_id),
                symbol=signal.symbol,
                side=action,
                qty=actual_qty,
                price=signal.price,
                executed_price=actual_price,
                sl=signal.stop_loss,
                target=signal.target,
                strategy=signal.strategy,
                reason=signal.reason,
                tag=tag,
                paper=False,
            )

            # Place stop-loss order and store its id on the parent order
            sl_id = self._place_stop_loss(order, exchange)
            order.sl_order_id = sl_id

            return order

        except Exception as e:
            logger.error(f"Order placement failed for {signal.symbol}: {e}")
            audit(
                "order_place_failed",
                symbol=signal.symbol,
                side=("BUY" if signal.signal == Signal.BUY else "SELL"),
                qty=signal.quantity,
                error=str(e),
            )
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

    def _place_stop_loss(self, order: Order, exchange: str) -> str | None:
        """Place a stop-loss order for an executed trade. Returns SL order id."""
        if not self.kite or self.is_paper:
            return None

        try:
            # Stop-loss is the reverse of the entry
            sl_transaction = (
                self.kite.TRANSACTION_TYPE_SELL
                if order.signal == Signal.BUY
                else self.kite.TRANSACTION_TYPE_BUY
            )

            tag = self._algo_tag()
            kwargs = dict(
                variety=self.kite.VARIETY_REGULAR,
                exchange=exchange,
                tradingsymbol=order.symbol,
                transaction_type=sl_transaction,
                quantity=order.quantity,
                product=self.kite.PRODUCT_MIS,
                order_type=self.kite.ORDER_TYPE_SLM,
                trigger_price=order.stop_loss,
            )
            if tag:
                kwargs["tag"] = tag

            sl_id = self._broker_call(
                f"place_SLM({order.symbol} @ {order.stop_loss:.2f})",
                lambda: self.kite.place_order(**kwargs),
            )
            if sl_id is None:
                logger.error(f"SLM placement failed for {order.symbol}; no broker stop active!")
                audit(
                    "slm_place_failed",
                    parent_order_id=order.order_id,
                    symbol=order.symbol,
                    sl=order.stop_loss,
                )
                return None
            logger.info(
                f"SLM placed for {order.symbol} at {order.stop_loss:.2f} "
                f"(order_id={sl_id})"
            )
            audit(
                "slm_place",
                parent_order_id=order.order_id,
                sl_order_id=str(sl_id),
                symbol=order.symbol,
                qty=order.quantity,
                sl=order.stop_loss,
            )
            return str(sl_id)
        except Exception as e:
            logger.error(f"Stop-loss placement failed for {order.symbol}: {e}")
            return None

    def _cancel_slm(self, order: Order) -> bool:
        """Cancel the broker-side SLM order attached to `order`. Returns True on success."""
        if not self.kite or self.is_paper or not order.sl_order_id:
            return True
        result = self._broker_call(
            f"cancel_SLM({order.symbol} {order.sl_order_id})",
            lambda: self.kite.cancel_order(
                variety=self.kite.VARIETY_REGULAR,
                order_id=order.sl_order_id,
            ),
        )
        if result is None:
            # Cancel failed — the SLM may still be live; flag but do not
            # proceed with a bot-side close (would risk double exit).
            logger.error(
                f"Failed to cancel SLM {order.sl_order_id} for {order.symbol}. "
                f"Refusing to place bot-side close to avoid double exit."
            )
            audit(
                "slm_cancel_failed",
                parent_order_id=order.order_id,
                sl_order_id=order.sl_order_id,
                symbol=order.symbol,
            )
            return False
        logger.info(f"Cancelled SLM {order.sl_order_id} for {order.symbol}")
        audit(
            "slm_cancel",
            parent_order_id=order.order_id,
            sl_order_id=order.sl_order_id,
            symbol=order.symbol,
        )
        order.sl_order_id = None
        return True

    def _modify_slm_quantity(self, order: Order, new_quantity: int) -> bool:
        """Modify the quantity on the standing SLM after a partial exit."""
        if not self.kite or self.is_paper or not order.sl_order_id:
            return True
        if new_quantity <= 0:
            return self._cancel_slm(order)
        result = self._broker_call(
            f"modify_SLM({order.symbol} qty={new_quantity})",
            lambda: self.kite.modify_order(
                variety=self.kite.VARIETY_REGULAR,
                order_id=order.sl_order_id,
                quantity=new_quantity,
            ),
        )
        if result is None:
            # Fallback: cancel + re-place with new qty
            logger.warning(f"modify_SLM failed for {order.symbol}; cancel+replace")
            if not self._cancel_slm(order):
                return False
            saved_qty = order.quantity
            order.quantity = new_quantity
            try:
                order.sl_order_id = self._place_stop_loss(order, order.exchange)
            finally:
                order.quantity = saved_qty
            return order.sl_order_id is not None
        return True

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
        audit(
            "order_close",
            order_id=order.order_id,
            symbol=order.symbol,
            exit_price=exit_price,
            pnl=order.pnl,
            reason=reason,
            paper=True,
        )

    def _close_live_position(self, order: Order, exit_price: float, reason: str):
        """Close a live position on Zerodha.

        CRITICAL: cancels the standing SLM FIRST. If the SLM cancel fails,
        the bot-side MARKET close is aborted to avoid ending up with a
        reverse position when the SLM subsequently triggers.
        """
        if not self.kite:
            return

        if not self._cancel_slm(order):
            logger.error(
                f"Aborting close for {order.symbol}: broker SLM still active. "
                f"The exchange will handle the stop-loss fill."
            )
            audit(
                "order_close_aborted",
                order_id=order.order_id,
                symbol=order.symbol,
                reason="slm_cancel_failed",
            )
            return

        try:
            close_transaction = (
                self.kite.TRANSACTION_TYPE_SELL
                if order.signal == Signal.BUY
                else self.kite.TRANSACTION_TYPE_BUY
            )

            tag = self._algo_tag()
            kwargs = dict(
                variety=self.kite.VARIETY_REGULAR,
                exchange=order.exchange,
                tradingsymbol=order.symbol,
                transaction_type=close_transaction,
                quantity=order.quantity,
                product=self.kite.PRODUCT_MIS,
                order_type=self.kite.ORDER_TYPE_MARKET,
            )
            if tag:
                kwargs["tag"] = tag

            close_id = self._broker_call(
                f"close_position({order.symbol})",
                lambda: self.kite.place_order(**kwargs),
            )
            if close_id is None:
                logger.error(f"Failed to close {order.symbol} after {order.quantity} units!")
                return

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
            audit(
                "order_close",
                order_id=order.order_id,
                close_order_id=str(close_id),
                symbol=order.symbol,
                exit_price=exit_price,
                pnl=order.pnl,
                reason=reason,
                paper=False,
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

        # Live mode: place partial exit order on Zerodha, then resize SLM
        if self.kite:
            try:
                close_transaction = (
                    self.kite.TRANSACTION_TYPE_SELL
                    if order.signal == Signal.BUY
                    else self.kite.TRANSACTION_TYPE_BUY
                )
                tag = self._algo_tag()
                kwargs = dict(
                    variety=self.kite.VARIETY_REGULAR,
                    exchange=order.exchange,
                    tradingsymbol=order.symbol,
                    transaction_type=close_transaction,
                    quantity=quantity,
                    product=self.kite.PRODUCT_MIS,
                    order_type=self.kite.ORDER_TYPE_MARKET,
                )
                if tag:
                    kwargs["tag"] = tag
                self._broker_call(
                    f"partial_close({order.symbol} qty={quantity})",
                    lambda: self.kite.place_order(**kwargs),
                )
            except Exception as e:
                logger.error(f"Partial close order failed for {order.symbol}: {e}")
                return

            # Resize the standing SLM to the remaining quantity, OR cancel
            # it if the position is now fully closed.
            if order.quantity <= 0:
                self._cancel_slm(order)
            else:
                self._modify_slm_quantity(order, order.quantity)

    def get_open_orders(self) -> list[Order]:
        """Get all open (unexited) orders from today."""
        return [o for o in self.orders if o.status == OrderStatus.EXECUTED and o.is_open]

    def get_todays_pnl(self) -> float:
        """Total P&L for today across all closed trades."""
        return sum(o.pnl for o in self.orders)

    def get_todays_trade_count(self) -> int:
        """Number of trades placed today."""
        return len(self.orders)

    # ── Broker state reconciliation ───────────────────────────────────────
    def reconcile_with_broker(self) -> dict:
        """
        Diff in-memory open orders against broker's actual day positions.
        Returns a report dict: {missing_at_broker, unexpected_at_broker,
        quantity_mismatch, clean (bool)}.

        Only meaningful in live mode. In paper mode returns a clean result.
        """
        report = {
            "missing_at_broker": [],     # we think we hold, broker doesn't
            "unexpected_at_broker": [],  # broker holds, we don't
            "quantity_mismatch": [],     # (symbol, our_qty, broker_qty)
            "clean": True,
        }
        if self.is_paper or not self.kite:
            return report

        try:
            positions = self._broker_call(
                "kite.positions()", lambda: self.kite.positions()
            )
            if not positions:
                return report
            day_positions = positions.get("day", []) or []
        except Exception as e:
            logger.error(f"reconcile_with_broker failed: {e}")
            report["clean"] = False
            return report

        # Build broker-side map: symbol -> signed net quantity
        broker_net: dict[str, int] = {}
        for p in day_positions:
            sym = p.get("tradingsymbol")
            qty = int(p.get("quantity", 0))
            if sym and qty != 0:
                broker_net[sym] = broker_net.get(sym, 0) + qty

        # Build bot-side map: open orders net
        bot_net: dict[str, int] = {}
        for o in self.get_open_orders():
            q = o.quantity if o.signal == Signal.BUY else -o.quantity
            bot_net[o.symbol] = bot_net.get(o.symbol, 0) + q

        for sym, bot_q in bot_net.items():
            broker_q = broker_net.get(sym, 0)
            if broker_q == 0:
                report["missing_at_broker"].append(sym)
                report["clean"] = False
            elif broker_q != bot_q:
                report["quantity_mismatch"].append((sym, bot_q, broker_q))
                report["clean"] = False

        for sym, broker_q in broker_net.items():
            if sym not in bot_net:
                report["unexpected_at_broker"].append((sym, broker_q))
                report["clean"] = False

        if not report["clean"]:
            logger.warning(f"[RECONCILE] Broker drift detected: {report}")
            audit("reconcile_drift", **{k: v for k, v in report.items() if k != "clean"})
        else:
            logger.info("[RECONCILE] Bot state matches broker.")
        return report

    def handle_order_update(self, update: dict):
        """
        Called by the WebSocket on_order_update. Reflects broker-driven
        state changes (SLM triggers, rejections, partial fills) into the
        in-memory Order objects so PositionManager stops polling a stop
        that already fired at the exchange.

        `update` is a KiteTicker order-update dict (contains order_id,
        status, filled_quantity, average_price, parent_order_id).
        """
        if self.is_paper:
            return
        try:
            oid = str(update.get("order_id"))
            status = update.get("status")
            if not oid or not status:
                return

            # If this update is for a standing SLM, find its parent order
            for o in self.orders:
                if o.sl_order_id == oid:
                    if status in ("COMPLETE", "TRIGGERED"):
                        fill_price = float(update.get("average_price") or o.stop_loss)
                        logger.warning(
                            f"[WS] SLM {oid} fired for {o.symbol} at {fill_price:.2f}"
                        )
                        # Mark position closed; PositionManager will clean up
                        # (see its listener). Suppress software stop.
                        if o.signal == Signal.BUY:
                            o.pnl = (fill_price - o.executed_price) * o.quantity
                        else:
                            o.pnl = (o.executed_price - fill_price) * o.quantity
                        o.exit_price = fill_price
                        o.is_open = False
                        o.sl_order_id = None
                        audit(
                            "slm_fired",
                            parent_order_id=o.order_id,
                            sl_order_id=oid,
                            symbol=o.symbol,
                            fill_price=fill_price,
                            pnl=o.pnl,
                        )
                    elif status in ("REJECTED", "CANCELLED"):
                        logger.error(
                            f"[WS] SLM {oid} for {o.symbol} was {status}; "
                            f"NO broker stop active. Software stop will take over."
                        )
                        audit(
                            "slm_lost",
                            parent_order_id=o.order_id,
                            sl_order_id=oid,
                            symbol=o.symbol,
                            status=status,
                        )
                        o.sl_order_id = None
                    return

            # Otherwise it's an update for the entry order itself
            for o in self.orders:
                if o.order_id == oid:
                    if status == "REJECTED":
                        logger.error(f"[WS] Entry {oid} ({o.symbol}) REJECTED")
                        o.status = OrderStatus.REJECTED
                        o.is_open = False
                        audit(
                            "order_rejected",
                            order_id=o.order_id,
                            symbol=o.symbol,
                        )
                    return
        except Exception as e:
            logger.error(f"handle_order_update failed: {e}")
