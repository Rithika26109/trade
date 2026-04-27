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


# ═════════════════════════════════════════════════════════════════════════
# Paper Simulation Tests (rejection, partial fills, dynamic slippage)
# ═════════════════════════════════════════════════════════════════════════


class TestPaperRejection:

    def test_margin_rejection(self, mock_order_manager, monkeypatch):
        """Order exceeding available capital is rejected."""
        om = mock_order_manager
        monkeypatch.setattr(settings, "PAPER_SIMULATE_REJECTIONS", True)
        monkeypatch.setattr(settings, "PAPER_RANDOM_REJECTION_PCT", 0)  # disable random
        om._get_available_capital = lambda: 10_000  # only 10k

        sig = _make_trade_signal(price=2500.0, quantity=10)  # 25k notional
        order = om.place_order(sig)

        assert order is None
        rejected = [o for o in om.orders if o.status == OrderStatus.REJECTED]
        assert len(rejected) == 1
        assert "Insufficient margin" in rejected[0].rejection_reason

    def test_random_rejection_forced(self, mock_order_manager, monkeypatch):
        """Force 100% random rejection rate."""
        om = mock_order_manager
        monkeypatch.setattr(settings, "PAPER_SIMULATE_REJECTIONS", True)
        monkeypatch.setattr(settings, "PAPER_RANDOM_REJECTION_PCT", 100)
        monkeypatch.setattr(settings, "PAPER_MARGIN_CHECK", False)

        sig = _make_trade_signal()
        order = om.place_order(sig)

        assert order is None
        rejected = [o for o in om.orders if o.status == OrderStatus.REJECTED]
        assert len(rejected) == 1
        assert "Simulated exchange rejection" in rejected[0].rejection_reason

    def test_no_rejection_when_disabled(self, mock_order_manager, monkeypatch):
        """With toggle off, no rejections (backward compat)."""
        om = mock_order_manager
        monkeypatch.setattr(settings, "PAPER_SIMULATE_REJECTIONS", False)

        sig = _make_trade_signal()
        order = om.place_order(sig)

        assert order is not None
        assert order.status == OrderStatus.EXECUTED

    def test_sufficient_margin_passes(self, mock_order_manager, monkeypatch):
        """Order within capital is accepted."""
        om = mock_order_manager
        monkeypatch.setattr(settings, "PAPER_SIMULATE_REJECTIONS", True)
        monkeypatch.setattr(settings, "PAPER_RANDOM_REJECTION_PCT", 0)
        om._get_available_capital = lambda: 100_000

        sig = _make_trade_signal(price=2500.0, quantity=10)  # 25k notional
        order = om.place_order(sig)

        assert order is not None
        assert order.status == OrderStatus.EXECUTED


class TestPaperPartialFills:

    def test_partial_fill_reduces_quantity(self, mock_order_manager, monkeypatch):
        """When partial fill fires, order.quantity < requested."""
        import random as rng
        rng.seed(42)

        om = mock_order_manager
        monkeypatch.setattr(settings, "PAPER_SIMULATE_PARTIAL_FILLS", True)
        monkeypatch.setattr(settings, "PAPER_PARTIAL_FILL_PROB", 1.0)  # force partial

        sig = _make_trade_signal(quantity=100)
        order = om.place_order(sig)

        assert order is not None
        assert order.quantity < 100
        assert order.requested_quantity == 100
        assert order.original_quantity == order.quantity

    def test_full_fill_when_disabled(self, mock_order_manager, monkeypatch):
        """With toggle off, full quantity always fills."""
        om = mock_order_manager
        monkeypatch.setattr(settings, "PAPER_SIMULATE_PARTIAL_FILLS", False)

        sig = _make_trade_signal(quantity=50)
        order = om.place_order(sig)

        assert order is not None
        assert order.quantity == 50

    def test_full_fill_most_of_the_time(self, mock_order_manager, monkeypatch):
        """With low probability, most orders fill fully."""
        import random as rng
        rng.seed(0)

        om = mock_order_manager
        monkeypatch.setattr(settings, "PAPER_SIMULATE_PARTIAL_FILLS", True)
        monkeypatch.setattr(settings, "PAPER_PARTIAL_FILL_PROB", 0.0)  # 0% partial

        sig = _make_trade_signal(quantity=50)
        order = om.place_order(sig)

        assert order is not None
        assert order.quantity == 50


class TestPaperDynamicSlippage:

    def test_dynamic_slippage_differs_from_fixed(self, mock_order_manager, monkeypatch):
        """Dynamic slippage uses base rate, not the legacy fixed rate."""
        om = mock_order_manager
        monkeypatch.setattr(settings, "PAPER_DYNAMIC_SLIPPAGE", True)
        monkeypatch.setattr(settings, "PAPER_BASE_SLIPPAGE_PCT", 0.03)
        # Disable multipliers that need market data
        monkeypatch.setattr(settings, "PAPER_SLIPPAGE_VOLATILITY_MULT", False)
        monkeypatch.setattr(settings, "PAPER_SLIPPAGE_TIME_MULT", False)
        monkeypatch.setattr(settings, "PAPER_SLIPPAGE_SIZE_MULT", False)

        sig = _make_trade_signal(price=2500.0)
        order = om.place_order(sig)

        assert order is not None
        expected_slip = 2500.0 * (0.03 / 100)
        assert order.executed_price == pytest.approx(2500.0 + expected_slip, rel=1e-6)

    def test_slippage_capped(self, mock_order_manager, monkeypatch):
        """Slippage never exceeds PAPER_SLIPPAGE_MAX_PCT."""
        om = mock_order_manager
        monkeypatch.setattr(settings, "PAPER_DYNAMIC_SLIPPAGE", True)
        monkeypatch.setattr(settings, "PAPER_BASE_SLIPPAGE_PCT", 10.0)  # absurdly high
        monkeypatch.setattr(settings, "PAPER_SLIPPAGE_MAX_PCT", 0.50)
        monkeypatch.setattr(settings, "PAPER_SLIPPAGE_VOLATILITY_MULT", False)
        monkeypatch.setattr(settings, "PAPER_SLIPPAGE_TIME_MULT", False)
        monkeypatch.setattr(settings, "PAPER_SLIPPAGE_SIZE_MULT", False)

        sig = _make_trade_signal(price=2500.0)
        order = om.place_order(sig)

        assert order is not None
        max_slip = 2500.0 * (0.50 / 100)
        assert order.executed_price <= 2500.0 + max_slip + 0.01

    def test_fixed_slippage_when_disabled(self, mock_order_manager, monkeypatch):
        """With toggle off, original fixed slippage is used."""
        om = mock_order_manager
        monkeypatch.setattr(settings, "PAPER_DYNAMIC_SLIPPAGE", False)

        sig = _make_trade_signal(price=2500.0)
        order = om.place_order(sig)

        expected = 2500.0 * (settings.PAPER_SLIPPAGE_PCT / 100)
        assert order.executed_price == pytest.approx(2500.0 + expected, rel=1e-6)
