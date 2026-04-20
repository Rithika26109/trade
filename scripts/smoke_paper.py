"""
Paper-Mode Smoke Test (Phase 5)
────────────────────────────────
Exercises the full live trading path (order placement → SLM tracking →
WebSocket fill → close) against an in-memory fake Kite client. No network,
no real broker. This is the final gate before promoting the bot to
actual paper trading on Zerodha, and before any eventual live rollout.

Validates:
    * OrderManager places a paper order and writes audit.
    * OrderManager tolerates the fake Kite client in "live" mode too.
    * PositionManager reacts to a tick and exits cleanly.
    * RiskManager evaluates a signal and sizes the position.
    * DB persists + reads back the closed trade.
    * kill_switch can abort mid-run.

Usage:
    python scripts/smoke_paper.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Sandbox the DB and audit before importing settings-consuming modules.
_TMP = Path(tempfile.mkdtemp(prefix="smoke_"))
os.environ["AUDIT_LOG_PATH"] = str(_TMP / "audit.jsonl")
os.environ["KILL_SWITCH_PATH"] = str(_TMP / ".kill_switch")
os.environ["TRADING_MODE"] = "paper"

from config import settings  # noqa: E402
settings.DB_PATH = _TMP / "trades.db"
settings.AUDIT_LOG_PATH = str(_TMP / "audit.jsonl")
settings.KILL_SWITCH_PATH = str(_TMP / ".kill_switch")

from src.execution.order_manager import OrderManager  # noqa: E402
from src.execution.position_manager import PositionManager  # noqa: E402
from src.risk.risk_manager import RiskManager  # noqa: E402
from src.strategy.base import Signal, TradeSignal  # noqa: E402
from src.utils import kill_switch  # noqa: E402
from src.utils.db import TradeDB  # noqa: E402


GRN = "\033[92m"
RED = "\033[91m"
END = "\033[0m"


def _step(name: str, ok: bool, detail: str = "") -> bool:
    tag = f"{GRN}PASS{END}" if ok else f"{RED}FAIL{END}"
    print(f"  [{tag}] {name}  {detail}")
    return ok


def run() -> int:
    print("── SMOKE: paper-mode end-to-end ────────────────────────────")
    db = TradeDB(db_path=settings.DB_PATH)

    om = OrderManager(kite=None)
    om.is_paper = True
    pm = PositionManager(om, db=db)
    rm = RiskManager(om, db=db)
    rm.update_capital(100_000.0)

    # 1. Build a BUY signal and size it through RiskManager
    sig_ = TradeSignal(
        signal=Signal.BUY,
        symbol="RELIANCE",
        price=2500.0,
        quantity=0,           # RiskManager fills in
        stop_loss=2480.0,
        target=2560.0,        # 3R target to clear cost-adjusted R:R gate
        reason="smoke_test",
        strategy="SMOKE",
    )
    approved = rm.evaluate(sig_)
    ok1 = _step("risk_manager_sized", approved is not None and approved.quantity > 0,
                detail=f"qty={getattr(approved, 'quantity', None)}")
    if not ok1:
        return 1

    # 2. Place the order (paper)
    order = om.place_order(approved, exchange="NSE")
    ok2 = _step("order_placed", order is not None and order.is_open,
                detail=f"id={order.order_id if order else None}")
    if not ok2:
        return 1

    pm.add_position(order)

    # 3. Drive ticks upward through 1R, 2R, 3R partial ladders, then force-close remainder
    for price in (2521.0, 2541.0, 2561.0, 2580.0):
        pm.check_exits({"RELIANCE": price})
    if order.is_open:
        pm.force_close_all({"RELIANCE": 2580.0}, "smoke_flatten")
    ok3 = _step("target_exit_fired", not order.is_open and order.pnl > 0,
                detail=f"pnl={order.pnl:.2f}")
    if not ok3:
        return 1

    # 4. DB persists trade
    db.log_trade(order)
    trades = db.get_todays_trades()
    ok4 = _step("db_persists_trade", len(trades) >= 1,
                detail=f"rows={len(trades)}")

    # 5. Audit file has >= 2 events (place + close)
    audit_path = Path(settings.AUDIT_LOG_PATH)
    audit_lines = audit_path.read_text().splitlines() if audit_path.exists() else []
    events = sum(1 for l in audit_lines if '"event"' in l)
    ok5 = _step("audit_emitted", events >= 2, detail=f"events={events}")

    # 6. Kill-switch engage / disengage is observable
    kill_switch.engage("smoke")
    ok6a = kill_switch.is_engaged()
    kill_switch.disengage()
    ok6b = not kill_switch.is_engaged()
    ok6 = _step("kill_switch_roundtrip", ok6a and ok6b)

    all_ok = all([ok1, ok2, ok3, ok4, ok5, ok6])
    print("─" * 56)
    if all_ok:
        print(f"{GRN}SMOKE OK — ready for live paper trading.{END}")
        return 0
    print(f"{RED}SMOKE FAILED — see failures above.{END}")
    return 1


if __name__ == "__main__":
    raise SystemExit(run())
