"""
Tests for the Trade Database (SQLite persistence).
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from config import settings
from src.execution.order_manager import Order, OrderStatus
from src.strategy.base import Signal
from src.utils.db import TradeDB


def _make_order(
    order_id="PAPER-000001",
    symbol="RELIANCE",
    signal=Signal.BUY,
    quantity=10,
    executed_price=2500.0,
    exit_price=2550.0,
    stop_loss=2450.0,
    target=2600.0,
    pnl=500.0,
    strategy="ORB",
    is_paper=True,
    is_open=False,
):
    return Order(
        order_id=order_id,
        symbol=symbol,
        exchange="NSE",
        signal=signal,
        quantity=quantity,
        price=executed_price,
        stop_loss=stop_loss,
        target=target,
        order_type="MARKET",
        status=OrderStatus.EXECUTED,
        executed_price=executed_price,
        executed_at=settings.now_ist(),
        exit_price=exit_price,
        pnl=pnl,
        reason="Test trade",
        strategy=strategy,
        is_paper=is_paper,
        is_open=is_open,
        original_quantity=quantity,
    )


class TestTradeLogAndRetrieval:

    def test_log_and_retrieve_trade(self, trade_db):
        """log_trade followed by get_todays_trades returns the record."""
        order = _make_order()
        trade_db.log_trade(order)

        trades = trade_db.get_todays_trades()
        assert len(trades) >= 1

        latest = trades[-1]
        assert latest["order_id"] == "PAPER-000001"
        assert latest["symbol"] == "RELIANCE"
        assert latest["signal"] == "BUY"
        assert latest["quantity"] == 10
        assert latest["pnl"] == pytest.approx(500.0)
        assert latest["strategy"] == "ORB"

    def test_log_multiple_trades(self, trade_db):
        """Multiple trades are all retrievable."""
        for i in range(3):
            order = _make_order(
                order_id=f"PAPER-{i+1:06d}",
                symbol=["TCS", "INFY", "SBIN"][i],
                pnl=[200, -100, 50][i],
            )
            trade_db.log_trade(order)

        trades = trade_db.get_todays_trades()
        assert len(trades) == 3
        symbols = [t["symbol"] for t in trades]
        assert "TCS" in symbols
        assert "INFY" in symbols
        assert "SBIN" in symbols


class TestOpenPositionLifecycle:

    def test_open_position_lifecycle(self, trade_db):
        """save_open_position -> get_open_positions -> remove_open_position."""
        order = _make_order(is_open=True)

        # Save
        trade_db.save_open_position(order)
        positions = trade_db.get_open_positions()
        assert len(positions) == 1
        assert positions[0]["order_id"] == "PAPER-000001"
        assert positions[0]["symbol"] == "RELIANCE"

        # Remove
        trade_db.remove_open_position("PAPER-000001")
        positions = trade_db.get_open_positions()
        assert len(positions) == 0

    def test_clear_open_positions(self, trade_db):
        """clear_open_positions removes all persisted positions."""
        for i in range(3):
            order = _make_order(order_id=f"PAPER-{i+1:06d}", is_open=True)
            trade_db.save_open_position(order)

        assert len(trade_db.get_open_positions()) == 3

        trade_db.clear_open_positions()
        assert len(trade_db.get_open_positions()) == 0


class TestDailySummary:

    def test_daily_summary(self, trade_db):
        """save_daily_summary -> get_daily_summaries returns the record."""
        trade_db.save_daily_summary(
            total_trades=5,
            winning_trades=3,
            losing_trades=2,
            total_pnl=750.0,
            max_drawdown=200.0,
            capital=100000.0,
            is_paper=True,
        )

        summaries = trade_db.get_daily_summaries(days=7)
        assert len(summaries) >= 1

        latest = summaries[0]
        assert latest["total_trades"] == 5
        assert latest["winning_trades"] == 3
        assert latest["losing_trades"] == 2
        assert latest["total_pnl"] == pytest.approx(750.0)
        assert latest["max_drawdown"] == pytest.approx(200.0)
        assert latest["capital"] == pytest.approx(100000.0)


class TestOverallStats:

    def test_overall_stats(self, trade_db):
        """get_overall_stats aggregates all trades."""
        orders = [
            _make_order(order_id="P-001", pnl=200),
            _make_order(order_id="P-002", pnl=-100),
            _make_order(order_id="P-003", pnl=0),
        ]
        for o in orders:
            trade_db.log_trade(o)

        stats = trade_db.get_overall_stats()
        assert stats["total_trades"] == 3
        assert stats["wins"] == 1
        assert stats["losses"] == 1
        assert stats["breakeven"] == 1
        assert stats["total_pnl"] == pytest.approx(100.0)
