"""
Tests for the Order Manager — paper trading order lifecycle.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from config import settings
from src.execution.order_manager import Order, OrderManager, OrderStatus
from src.strategy.base import Signal, TradeSignal


def _make_trade_signal(
    symbol="RELIANCE",
    signal=Signal.BUY,
    price=2500.0,
    stop_loss=2450.0,
    target=2600.0,
    quantity=10,
):
    return TradeSignal(
        signal=signal,
        symbol=symbol,
        price=price,
        stop_loss=stop_loss,
        target=target,
        quantity=quantity,
        strategy="TEST",
    )


class TestPaperOrderPlacement:

    def test_paper_order_placement(self, mock_order_manager):
        """Paper order is created with slippage applied to executed_price."""
        om = mock_order_manager
        sig = _make_trade_signal(price=2500.0, quantity=10)
        order = om.place_order(sig)

        assert order is not None
        assert order.is_paper is True
        assert order.status == OrderStatus.EXECUTED
        assert order.is_open is True
        assert order.quantity == 10
        assert order.original_quantity == 10

        # BUY: executed_price = price + slippage
        expected_slippage = 2500.0 * (settings.PAPER_SLIPPAGE_PCT / 100)
        assert order.executed_price == pytest.approx(2500.0 + expected_slippage, rel=1e-6)

    def test_paper_sell_order_slippage(self, mock_order_manager):
        """SELL paper orders have slippage reducing the executed price."""
        om = mock_order_manager
        sig = _make_trade_signal(signal=Signal.SELL, price=2500.0, quantity=5)
        order = om.place_order(sig)

        assert order is not None
        expected_slippage = 2500.0 * (settings.PAPER_SLIPPAGE_PCT / 100)
        assert order.executed_price == pytest.approx(2500.0 - expected_slippage, rel=1e-6)

    def test_hold_signal_returns_none(self, mock_order_manager):
        """A HOLD signal should not produce an order."""
        om = mock_order_manager
        sig = TradeSignal(
            signal=Signal.HOLD, symbol="X", price=0, stop_loss=0, target=0
        )
        result = om.place_order(sig)
        assert result is None

    def test_zero_quantity_returns_none(self, mock_order_manager):
        """Quantity <= 0 should not produce an order."""
        om = mock_order_manager
        sig = _make_trade_signal(quantity=0)
        result = om.place_order(sig)
        assert result is None


class TestPaperOrderClose:

    def test_paper_order_close(self, mock_order_manager):
        """Closing a BUY order at a higher price produces positive P&L and sets is_open=False."""
        om = mock_order_manager
        sig = _make_trade_signal(price=2500.0, quantity=10)
        order = om.place_order(sig)
        assert order.is_open is True

        om.close_position(order, exit_price=2550.0, reason="target hit")

        assert order.is_open is False
        assert order.exit_price == 2550.0
        # P&L = (exit - executed_price) * qty
        expected_pnl = (2550.0 - order.executed_price) * 10
        assert order.pnl == pytest.approx(expected_pnl, rel=1e-6)

    def test_paper_sell_close(self, mock_order_manager):
        """Closing a SELL order at a lower price produces positive P&L."""
        om = mock_order_manager
        sig = _make_trade_signal(signal=Signal.SELL, price=2500.0, quantity=10)
        order = om.place_order(sig)

        om.close_position(order, exit_price=2450.0, reason="target hit")

        assert order.is_open is False
        expected_pnl = (order.executed_price - 2450.0) * 10
        assert order.pnl == pytest.approx(expected_pnl, rel=1e-6)


class TestPartialClose:

    def test_partial_close(self, mock_order_manager):
        """Partial close reduces quantity and records the exit."""
        om = mock_order_manager
        sig = _make_trade_signal(price=2500.0, quantity=10)
        order = om.place_order(sig)

        om.partial_close(order, exit_price=2550.0, quantity=4, reason="1R target")

        assert order.quantity == 6
        assert order.is_open is True  # Still partially open
        assert len(order.partial_exits) == 1
        assert order.partial_exits[0] == (2550.0, 4, "1R target")
        assert order.pnl > 0

    def test_full_close_via_partials(self, mock_order_manager):
        """Closing all remaining quantity via partial_close sets is_open=False."""
        om = mock_order_manager
        sig = _make_trade_signal(price=2500.0, quantity=10)
        order = om.place_order(sig)

        om.partial_close(order, exit_price=2550.0, quantity=6, reason="1R target")
        om.partial_close(order, exit_price=2580.0, quantity=4, reason="2R target")

        assert order.quantity == 0
        assert order.is_open is False
        assert len(order.partial_exits) == 2


class TestOpenOrdersFiltering:

    def test_get_open_orders_excludes_closed(self, mock_order_manager):
        """Closed orders do not appear in get_open_orders()."""
        om = mock_order_manager

        sig1 = _make_trade_signal(symbol="TCS", quantity=5)
        sig2 = _make_trade_signal(symbol="INFY", quantity=5)

        order1 = om.place_order(sig1)
        order2 = om.place_order(sig2)

        om.close_position(order1, exit_price=2550.0, reason="target")

        open_orders = om.get_open_orders()
        assert len(open_orders) == 1
        assert open_orders[0].symbol == "INFY"

    def test_breakeven_not_open(self, mock_order_manager):
        """A position closed at breakeven (pnl ~0) has is_open=False."""
        om = mock_order_manager
        sig = _make_trade_signal(price=2500.0, quantity=10)
        order = om.place_order(sig)

        # Close at the executed price so pnl = 0
        om.close_position(order, exit_price=order.executed_price, reason="breakeven")

        assert order.is_open is False
        assert order.pnl == pytest.approx(0.0, abs=1e-6)
        assert order not in om.get_open_orders()


class TestPnLAggregation:

    def test_get_todays_pnl(self, mock_order_manager):
        """get_todays_pnl sums P&L across all orders (open and closed)."""
        om = mock_order_manager

        sig1 = _make_trade_signal(symbol="TCS", quantity=10)
        order1 = om.place_order(sig1)
        om.close_position(order1, exit_price=2550.0, reason="win")

        sig2 = _make_trade_signal(symbol="INFY", quantity=5)
        order2 = om.place_order(sig2)
        om.close_position(order2, exit_price=2480.0, reason="loss")

        total_pnl = om.get_todays_pnl()
        expected = order1.pnl + order2.pnl
        assert total_pnl == pytest.approx(expected, rel=1e-6)
