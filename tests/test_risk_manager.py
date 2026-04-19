"""
Tests for the Risk Manager — the most critical module in the bot.
Verifies circuit breakers, position sizing, and all safety guards.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from config import settings
from src.execution.order_manager import Order, OrderManager, OrderStatus
from src.risk.risk_manager import RiskManager
from src.strategy.base import Signal, TradeSignal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_signal(
    symbol="RELIANCE",
    signal=Signal.BUY,
    price=2500.0,
    stop_loss=2450.0,
    target=2600.0,
    confluence_score=0.0,
    strategy="ORB",
):
    """Create a TradeSignal with sensible defaults."""
    return TradeSignal(
        signal=signal,
        symbol=symbol,
        price=price,
        stop_loss=stop_loss,
        target=target,
        confluence_score=confluence_score,
        strategy=strategy,
    )


def _make_open_order(
    om: OrderManager,
    symbol="RELIANCE",
    signal_type=Signal.BUY,
    price=2500.0,
    stop_loss=2450.0,
    target=2600.0,
    pnl=0.0,
    is_open=True,
    quantity=10,
):
    """Insert a synthetic Order into the OrderManager's list."""
    om._paper_order_counter += 1
    order = Order(
        order_id=f"PAPER-{om._paper_order_counter:06d}",
        symbol=symbol,
        exchange="NSE",
        signal=signal_type,
        quantity=quantity,
        price=price,
        stop_loss=stop_loss,
        target=target,
        order_type="MARKET",
        status=OrderStatus.EXECUTED,
        executed_price=price,
        executed_at=settings.now_ist(),
        pnl=pnl,
        is_paper=True,
        is_open=is_open,
        original_quantity=quantity,
    )
    om.orders.append(order)
    return order


# ---------------------------------------------------------------------------
# Circuit Breaker Tests
# ---------------------------------------------------------------------------

class TestCircuitBreakers:

    def test_daily_loss_circuit_breaker(self, mock_order_manager, mock_risk_manager):
        """When total P&L exceeds MAX_DAILY_LOSS_PCT the next trade is rejected."""
        om = mock_order_manager
        rm = mock_risk_manager

        # Place closed orders totaling > 3% of 100 000 = 3000
        _make_open_order(om, symbol="TCS", pnl=-1500.0, is_open=False)
        _make_open_order(om, symbol="INFY", pnl=-1600.0, is_open=False)
        # Total P&L = -3100 which exceeds 3% of 100k

        sig = _make_signal()
        result = rm.evaluate(sig)
        assert result is None, "Trade should be rejected when daily loss limit is breached"

    def test_max_trades_circuit_breaker(self, mock_order_manager, mock_risk_manager):
        """After MAX_TRADES_PER_DAY trades, the next one is rejected."""
        om = mock_order_manager
        rm = mock_risk_manager

        # Place exactly 5 orders (MAX_TRADES_PER_DAY)
        for i in range(settings.MAX_TRADES_PER_DAY):
            _make_open_order(om, symbol=f"SYM{i}", is_open=False, pnl=10)

        sig = _make_signal()
        result = rm.evaluate(sig)
        assert result is None, "6th trade should be rejected when max trades reached"

    def test_max_positions_circuit_breaker(self, mock_order_manager, mock_risk_manager):
        """When MAX_OPEN_POSITIONS are open, the next signal is rejected."""
        om = mock_order_manager
        rm = mock_risk_manager

        # Open exactly MAX_OPEN_POSITIONS (default 2)
        _make_open_order(om, symbol="TCS", is_open=True)
        _make_open_order(om, symbol="INFY", is_open=True)

        sig = _make_signal(symbol="SBIN")
        result = rm.evaluate(sig)
        assert result is None, "3rd position should be rejected"

    def test_consecutive_loss_pause(self, mock_risk_manager):
        """After MAX_CONSECUTIVE_LOSSES, the manager pauses trading."""
        rm = mock_risk_manager

        for _ in range(settings.MAX_CONSECUTIVE_LOSSES):
            rm.record_trade_result(-100)

        assert rm._paused_until is not None
        assert rm._paused_until > settings.now_ist()

        sig = _make_signal()
        result = rm.evaluate(sig)
        assert result is None, "Trade should be rejected during pause period"

    def test_intraday_drawdown_breaker(self, mock_risk_manager):
        """Drawdown from intraday high-water mark > 2% triggers breaker."""
        rm = mock_risk_manager

        # Simulate: peaked at +1500, now at -600 => drawdown = 2100
        # 2% of 100k = 2000.  2100 > 2000 => breaker fires
        rm.update_intraday_equity(realized_pnl=1500, unrealized_pnl=0)
        rm.update_intraday_equity(realized_pnl=-600, unrealized_pnl=0)

        sig = _make_signal()
        result = rm.evaluate(sig)
        assert result is None, "Trade should be rejected when intraday drawdown exceeded"


# ---------------------------------------------------------------------------
# Position Sizing Tests
# ---------------------------------------------------------------------------

class TestPositionSizing:

    def test_position_size_risk_based(self, mock_risk_manager):
        """Quantity = capital * risk% / risk_per_share (when value cap is not binding)."""
        rm = mock_risk_manager
        # Disable all advanced multipliers for a clean test
        with (
            patch.object(rm, "_get_vix_multiplier", return_value=1.0),
            patch.object(rm, "_get_kelly_multiplier", return_value=1.0),
            patch.object(rm, "_get_equity_curve_multiplier", return_value=1.0),
            patch.object(rm, "_get_time_multiplier", return_value=1.0),
        ):
            # Use a price where value cap (30% of 100k = 30k) does not interfere.
            # price = 500, SL = 490, risk_per_share = 10
            # max_risk = 100000 * 1% = 1000
            # risk-based qty = 1000 / 10 = 100
            # value-cap qty = 30000 / 500 = 60
            # min(100, 60) = 60 -- value cap still binds
            # Use price = 100, SL = 90, risk = 10
            # risk-based qty = 1000 / 10 = 100
            # value-cap qty = 30000 / 100 = 300
            # min(100, 300) = 100
            sig = _make_signal(price=100, stop_loss=90, target=120)
            qty = rm._calculate_position_size(sig)
            assert qty == 100, f"Expected 100 shares, got {qty}"

    def test_position_size_value_capped(self, mock_risk_manager):
        """Position value should not exceed MAX_POSITION_PCT (30%) of capital."""
        rm = mock_risk_manager

        with (
            patch.object(rm, "_get_vix_multiplier", return_value=1.0),
            patch.object(rm, "_get_kelly_multiplier", return_value=1.0),
            patch.object(rm, "_get_equity_curve_multiplier", return_value=1.0),
            patch.object(rm, "_get_time_multiplier", return_value=1.0),
        ):
            # Very cheap stock with tight stop -> risk-based qty would be huge
            # Price = 10, SL = 9.5, risk_per_share = 0.5
            # risk-based: 1000 / 0.5 = 2000 shares => value = 20 000
            # value cap: 30% of 100k / 10 = 3000 shares
            # min(2000, 3000) = 2000
            sig = _make_signal(price=10, stop_loss=9.5, target=11)
            qty = rm._calculate_position_size(sig)
            max_by_value = int((rm.capital * settings.MAX_POSITION_PCT / 100) / sig.price)
            assert qty <= max_by_value, "Position should be capped by value limit"


# ---------------------------------------------------------------------------
# Risk/Reward and Confluence Tests
# ---------------------------------------------------------------------------

class TestSignalFilters:

    def test_risk_reward_rejection(self, mock_risk_manager):
        """R:R below MIN_RISK_REWARD_RATIO (2.0) is rejected."""
        rm = mock_risk_manager
        # risk = 50, reward = 40 => R:R = 0.8
        sig = _make_signal(price=2500, stop_loss=2450, target=2540)
        assert sig.risk_reward_ratio < settings.MIN_RISK_REWARD_RATIO
        result = rm.evaluate(sig)
        assert result is None, "Poor R:R trade should be rejected"

    def test_confluence_threshold_rejection(self, mock_risk_manager):
        """Confluence < 55 rejected when scoring is enabled."""
        rm = mock_risk_manager
        original_enabled = settings.ENABLE_CONFLUENCE_SCORING
        original_threshold = settings.CONFLUENCE_THRESHOLD
        try:
            settings.ENABLE_CONFLUENCE_SCORING = True
            settings.CONFLUENCE_THRESHOLD = 55
            sig = _make_signal(confluence_score=40)
            result = rm.evaluate(sig)
            assert result is None, "Low-confluence trade should be rejected"
        finally:
            settings.ENABLE_CONFLUENCE_SCORING = original_enabled
            settings.CONFLUENCE_THRESHOLD = original_threshold


# ---------------------------------------------------------------------------
# Sector Limit
# ---------------------------------------------------------------------------

class TestSectorLimit:

    def test_sector_limit(self, mock_order_manager, mock_risk_manager):
        """Cannot open a second position in the same sector."""
        om = mock_order_manager
        rm = mock_risk_manager

        original_max = getattr(settings, "MAX_POSITIONS_PER_SECTOR", 1)
        try:
            settings.MAX_POSITIONS_PER_SECTOR = 1
            # Open position in Banking
            _make_open_order(om, symbol="HDFCBANK", is_open=True)

            # Try another Banking stock
            sig = _make_signal(symbol="ICICIBANK")
            result = rm.evaluate(sig)
            assert result is None, "Same-sector trade should be rejected"
        finally:
            settings.MAX_POSITIONS_PER_SECTOR = original_max


# ---------------------------------------------------------------------------
# Breakeven edge case
# ---------------------------------------------------------------------------

class TestBreakevenEdge:

    def test_breakeven_trade_not_counted_as_open(self, mock_order_manager):
        """A closed order with pnl=0 should have is_open=False."""
        om = mock_order_manager
        order = _make_open_order(om, symbol="TCS", pnl=0.0, is_open=True)

        # Close the position at breakeven
        om.close_position(order, exit_price=order.executed_price, reason="breakeven")
        assert order.is_open is False, "Closed order must not be open"
        assert order.pnl == 0.0

        open_orders = om.get_open_orders()
        assert order not in open_orders, "Breakeven-closed order must not appear in open orders"
