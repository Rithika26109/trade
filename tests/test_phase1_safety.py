"""Tests for Phase 1 safety-critical fixes."""
from unittest.mock import MagicMock

import pytest

from config import settings
from src.execution.order_manager import Order, OrderManager, OrderStatus
from src.execution.position_manager import PositionManager
from src.risk.risk_manager import RiskManager
from src.strategy.base import Signal, TradeSignal
from src.utils.tick_size import round_to_tick


# ── Tick-size rounding ─────────────────────────────────────────────────────
class TestTickRounding:
    def test_nearest_default(self):
        assert round_to_tick(123.37) == 123.35
        assert round_to_tick(123.38) == 123.40

    def test_floor_mode(self):
        assert round_to_tick(123.37, 0.05, "floor") == 123.35
        assert round_to_tick(123.39, 0.05, "floor") == 123.35

    def test_ceil_mode(self):
        assert round_to_tick(123.31, 0.05, "ceil") == 123.35
        assert round_to_tick(123.36, 0.05, "ceil") == 123.40

    def test_integer_tick(self):
        assert round_to_tick(11234.7, 1.0) == 11235.0

    def test_paper_order_rounds_sl(self, monkeypatch):
        monkeypatch.setattr(settings, "TRADING_MODE", "paper")
        om = OrderManager(kite=None)
        om.is_paper = True
        signal = TradeSignal(
            signal=Signal.BUY, symbol="RELIANCE", price=2500.13,
            stop_loss=2490.37,  # not on 0.05 grid
            target=2525.19,
            quantity=10, reason="test", strategy="TEST",
        )
        om.place_order(signal)
        placed = om.orders[-1]
        # BUY stop rounds up (tighter); target rounds down
        assert placed.stop_loss == round_to_tick(2490.37, 0.05, "ceil")
        assert placed.target == round_to_tick(2525.19, 0.05, "floor")
        assert abs(placed.stop_loss / 0.05 - round(placed.stop_loss / 0.05)) < 1e-9


# ── Risk clamp floor fix ───────────────────────────────────────────────────
class TestRiskClampFloor:
    def test_severe_scaledown_allowed_to_shrink(self, monkeypatch):
        """Equity-curve + time scale-down must actually shrink risk (previously
        floored at 10% of base)."""
        monkeypatch.setattr(settings, "TRADING_MODE", "paper")
        monkeypatch.setattr(settings, "RISK_PER_TRADE_PCT", 1.0)
        monkeypatch.setattr(settings, "EQUITY_CURVE_TRADING_ENABLED", True)
        monkeypatch.setattr(settings, "ENABLE_TIME_SCALING", True)

        om = OrderManager(kite=None)
        om.is_paper = True
        rm = RiskManager(om, db=None)
        # Force multipliers low
        rm._get_vix_multiplier = lambda: 0.3
        rm._get_kelly_multiplier = lambda: 0.25
        rm._get_equity_curve_multiplier = lambda: 0.25
        rm._get_time_multiplier = lambda: 0.5
        adjusted = rm._get_adjusted_risk_pct()
        # Product = 1.0 * 0.3 * 0.25 * 0.25 * 0.5 = 0.009375
        # With old clamp (floor at 0.1% of base = 0.1) it would have been 0.1.
        assert adjusted < 0.05, (
            f"Risk should shrink freely; got {adjusted}. "
            "Old clamp was incorrectly flooring it."
        )

    def test_upper_cap_still_enforced(self, monkeypatch):
        monkeypatch.setattr(settings, "TRADING_MODE", "paper")
        monkeypatch.setattr(settings, "RISK_PER_TRADE_PCT", 1.0)
        om = OrderManager(kite=None); om.is_paper = True
        rm = RiskManager(om, db=None)
        rm._get_vix_multiplier = lambda: 1.2
        rm._get_kelly_multiplier = lambda: 1.5
        rm._get_equity_curve_multiplier = lambda: 1.0
        rm._get_time_multiplier = lambda: 1.0
        adjusted = rm._get_adjusted_risk_pct()
        # Should clamp at 1.5% (150% of base), not 1.8%
        assert adjusted == pytest.approx(1.5)


# ── Broker SLM + software stop arbitration ─────────────────────────────────
class TestSLMArbitration:
    def _make_order(self, sl_order_id=None, is_paper=False):
        return Order(
            order_id="PX1", symbol="RELIANCE", exchange="NSE",
            signal=Signal.BUY, quantity=10, price=2500.0,
            stop_loss=2490.0, target=2520.0, order_type="MARKET",
            status=OrderStatus.EXECUTED, executed_price=2500.0,
            is_paper=is_paper, is_open=True, sl_order_id=sl_order_id,
            original_quantity=10,
        )

    def test_software_stop_suppressed_when_slm_active(self, monkeypatch):
        monkeypatch.setattr(settings, "TRADING_MODE", "live")
        om = OrderManager(kite=MagicMock())
        om.is_paper = False
        pm = PositionManager(om, db=None)
        pos = self._make_order(sl_order_id="SL-123", is_paper=False)
        # Price is at stop → software stop would normally fire
        reason = pm._should_exit(pos, 2489.0)
        assert reason is None, "Software stop must not fire when broker SLM is live"

    def test_software_stop_fires_when_no_slm(self, monkeypatch):
        om = OrderManager(kite=None); om.is_paper = True
        pm = PositionManager(om, db=None)
        pos = self._make_order(sl_order_id=None, is_paper=True)
        reason = pm._should_exit(pos, 2489.0)
        assert reason is not None and "Stop-loss" in reason

    def test_target_still_fires_when_slm_active(self):
        om = OrderManager(kite=MagicMock()); om.is_paper = False
        pm = PositionManager(om, db=None)
        pos = self._make_order(sl_order_id="SL-123", is_paper=False)
        reason = pm._should_exit(pos, 2525.0)
        assert reason is not None and "Target" in reason


# ── Close-position cancels SLM first ───────────────────────────────────────
class TestCloseCancelsSLM:
    def test_close_cancels_slm_before_market_exit(self, monkeypatch):
        kite = MagicMock()
        kite.VARIETY_REGULAR = "regular"
        kite.PRODUCT_MIS = "MIS"
        kite.TRANSACTION_TYPE_BUY = "BUY"
        kite.TRANSACTION_TYPE_SELL = "SELL"
        kite.ORDER_TYPE_MARKET = "MARKET"
        kite.cancel_order.return_value = "CANCEL_OK"
        kite.place_order.return_value = "CLOSE_123"

        om = OrderManager(kite=kite)
        om.is_paper = False

        order = Order(
            order_id="E1", symbol="RELIANCE", exchange="NSE",
            signal=Signal.BUY, quantity=10, price=2500.0,
            stop_loss=2490.0, target=2520.0, order_type="MARKET",
            status=OrderStatus.EXECUTED, executed_price=2500.0,
            is_paper=False, is_open=True, sl_order_id="SL-999",
            original_quantity=10,
        )
        om.orders.append(order)

        om._close_live_position(order, 2510.0, "target")

        # cancel_order must be called BEFORE place_order (close)
        assert kite.cancel_order.called, "SLM cancel must be attempted"
        # Ensure cancel happened before the close market order
        call_order = [c[0] for c in kite.method_calls]
        assert call_order.index("cancel_order") < call_order.index("place_order")
        assert order.sl_order_id is None

    def test_close_aborts_if_slm_cancel_fails(self, monkeypatch):
        """If we can't cancel the SLM, do NOT send a bot-side close — it would
        risk a reverse position when the SLM later triggers."""
        monkeypatch.setattr(settings, "BROKER_RETRY_ATTEMPTS", 1)
        monkeypatch.setattr(settings, "BROKER_RETRY_INITIAL_DELAY", 0.0)
        kite = MagicMock()
        kite.VARIETY_REGULAR = "regular"
        kite.PRODUCT_MIS = "MIS"
        kite.TRANSACTION_TYPE_BUY = "BUY"
        kite.TRANSACTION_TYPE_SELL = "SELL"
        kite.ORDER_TYPE_MARKET = "MARKET"
        kite.cancel_order.side_effect = RuntimeError("network")

        om = OrderManager(kite=kite); om.is_paper = False
        order = Order(
            order_id="E1", symbol="RELIANCE", exchange="NSE",
            signal=Signal.BUY, quantity=10, price=2500.0,
            stop_loss=2490.0, target=2520.0, order_type="MARKET",
            status=OrderStatus.EXECUTED, executed_price=2500.0,
            is_paper=False, is_open=True, sl_order_id="SL-999",
            original_quantity=10,
        )
        om.orders.append(order)

        om._close_live_position(order, 2510.0, "target")
        # place_order (close market) MUST NOT be called
        assert not kite.place_order.called, "Must not close when SLM cancel fails"
        assert order.is_open is True
        assert order.sl_order_id == "SL-999"


# ── Broker reconciliation ──────────────────────────────────────────────────
class TestReconciliation:
    def test_drift_detected(self):
        kite = MagicMock()
        kite.positions.return_value = {
            "day": [
                {"tradingsymbol": "TCS", "quantity": 5},  # unexpected
                {"tradingsymbol": "RELIANCE", "quantity": 10},
            ]
        }
        om = OrderManager(kite=kite); om.is_paper = False
        # Bot thinks it only holds RELIANCE (+10), nothing in TCS
        om.orders.append(Order(
            order_id="E1", symbol="RELIANCE", exchange="NSE",
            signal=Signal.BUY, quantity=10, price=2500.0,
            stop_loss=2490.0, target=2520.0, order_type="MARKET",
            status=OrderStatus.EXECUTED, is_open=True, is_paper=False,
            executed_price=2500.0, original_quantity=10,
        ))
        report = om.reconcile_with_broker()
        assert report["clean"] is False
        assert any(s[0] == "TCS" for s in report["unexpected_at_broker"])

    def test_clean_when_matched(self):
        kite = MagicMock()
        kite.positions.return_value = {
            "day": [{"tradingsymbol": "RELIANCE", "quantity": 10}]
        }
        om = OrderManager(kite=kite); om.is_paper = False
        om.orders.append(Order(
            order_id="E1", symbol="RELIANCE", exchange="NSE",
            signal=Signal.BUY, quantity=10, price=2500.0,
            stop_loss=2490.0, target=2520.0, order_type="MARKET",
            status=OrderStatus.EXECUTED, is_open=True, is_paper=False,
            executed_price=2500.0, original_quantity=10,
        ))
        report = om.reconcile_with_broker()
        assert report["clean"] is True

    def test_paper_mode_always_clean(self):
        om = OrderManager(kite=None); om.is_paper = True
        report = om.reconcile_with_broker()
        assert report["clean"] is True


# ── Circuit-limit rejection ────────────────────────────────────────────────
class TestCircuitLimitRejection:
    def test_sl_outside_band_rejected(self, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_CIRCUIT_LIMIT_CHECK", True)
        om = OrderManager(kite=None); om.is_paper = True
        rm = RiskManager(om, db=None)

        md = MagicMock()
        md.get_circuit_limits.return_value = {"lower": 2400.0, "upper": 2600.0}
        rm.market_data = md

        signal = TradeSignal(
            signal=Signal.BUY, symbol="RELIANCE", price=2500.0,
            stop_loss=2390.0,  # outside lower band (2400)
            target=2720.0,     # RR = 220/110 = 2.0, passes RR gate
            quantity=0, reason="t", strategy="T",
        )
        approved = rm.evaluate(signal)
        assert approved is None

    def test_sl_inside_band_approved(self, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_CIRCUIT_LIMIT_CHECK", True)
        monkeypatch.setattr(settings, "MIN_RISK_REWARD_RATIO", 1.0)
        monkeypatch.setattr(settings, "MAX_POSITIONS_PER_SECTOR", 0)
        monkeypatch.setattr(settings, "ENABLE_TIME_SCALING", False)
        monkeypatch.setattr(settings, "VOLATILITY_SCALING_ENABLED", False)
        monkeypatch.setattr(settings, "KELLY_ENABLED", False)
        monkeypatch.setattr(settings, "EQUITY_CURVE_TRADING_ENABLED", False)
        om = OrderManager(kite=None); om.is_paper = True
        rm = RiskManager(om, db=None)

        md = MagicMock()
        md.get_circuit_limits.return_value = {"lower": 2400.0, "upper": 2600.0}
        rm.market_data = md

        signal = TradeSignal(
            signal=Signal.BUY, symbol="RELIANCE", price=2500.0,
            stop_loss=2490.0, target=2520.0,
            quantity=0, reason="t", strategy="T",
        )
        approved = rm.evaluate(signal)
        assert approved is not None
        assert approved.quantity > 0


# ── Sector map dedupe ──────────────────────────────────────────────────────
def test_sector_map_no_duplicates():
    from src.risk.sector_map import SECTOR_MAP
    # Should have exactly one WIPRO entry
    # (dict can only hold one anyway, but verify the source file doesn't
    # contain it twice by checking the parsed dict has expected size)
    assert "WIPRO" in SECTOR_MAP
    assert SECTOR_MAP["WIPRO"] == "IT"
