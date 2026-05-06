"""
Bootstrap
─────────
One-shot startup pipeline. Validates config, runs compliance gate,
authenticates with Zerodha, wires all components, applies the daily
plan, and recovers any orphaned positions from a prior crashed session.

Returns a fully-populated :class:`BotContext` ready for ``Runtime.run()``.
"""

from __future__ import annotations

import sys

from config import settings
from src.auth.login import ZerodhaAuth
from src.data.market_data import MarketData
from src.execution.order_manager import Order, OrderManager, OrderStatus
from src.execution.position_manager import PositionManager
from src.risk.risk_manager import RiskManager
from src.scanner.stock_scanner import StockScanner
from src.strategy.base import Signal
from src.strategy.mean_reversion import MeanReversionStrategy
from src.strategy.orb import ORBStrategy
from src.strategy.orchestrator import StrategyOrchestrator
from src.strategy.pairs import PairsTradingStrategy
from src.strategy.rsi_ema import RSIEMAStrategy
from src.strategy.vwap_supertrend import VWAPSupertrendStrategy
from src.utils import kill_switch
from src.utils.audit import audit
from src.utils.compliance import ComplianceError, startup_compliance_check
from src.utils.logger import logger
from src.utils.plan_loader import git_pull, load_plan

from src.runtime.context import BotContext


class Bootstrap:
    """Builds and wires all components for a single trading session."""

    def __init__(self, mode: str | None = None):
        self.mode = mode or settings.TRADING_MODE

    def setup(self) -> BotContext:
        ctx = BotContext(mode=self.mode)

        logger.info("=" * 60)
        logger.info(f"  TRADING BOT STARTING — Mode: {ctx.mode.upper()}")
        logger.info("=" * 60)

        settings.validate_config()

        # Daily plan (best-effort — falls back to scanner / WATCHLIST).
        git_pull()
        ctx.daily_plan = load_plan()
        if ctx.daily_plan:
            audit(
                "plan_loaded",
                date=ctx.daily_plan.date,
                symbols=ctx.daily_plan.watchlist,
                overrides=ctx.daily_plan.risk_overrides,
                lessons=ctx.daily_plan.lessons_applied,
            )

        # SEBI compliance gate
        try:
            compliance = startup_compliance_check(ctx.mode)
        except ComplianceError as ce:
            logger.error(f"[COMPLIANCE] Halting: {ce}")
            audit("compliance_failed", error=str(ce), mode=ctx.mode)
            sys.exit(3)

        if kill_switch.is_engaged():
            reason = kill_switch.reason() or "pre-existing kill-switch"
            logger.error(f"[KILL_SWITCH] engaged ({reason}) — refusing to start.")
            audit("kill_switch_triggered", phase="startup", reason=reason)
            sys.exit(4)

        audit("startup", compliance=compliance)

        if not settings.is_market_day():
            today = settings.now_ist().date()
            logger.info(f"Market closed today ({today} — weekend or holiday). Exiting.")
            sys.exit(0)

        # Authenticate
        if ctx.mode in ("live", "paper"):
            try:
                auth = ZerodhaAuth()
                ctx.kite = auth.login()
                ctx.market_data = MarketData(ctx.kite)
                ctx.market_data.load_instruments("NSE")
                logger.info("Zerodha connected successfully")
            except Exception as e:
                logger.error(f"Authentication failed: {e}")
                if ctx.mode == "live":
                    logger.error("Cannot run live mode without Zerodha connection. Exiting.")
                    sys.exit(1)
                logger.error(
                    "Auth failed — cannot run paper trading without market data. "
                    "Paper mode needs real-time prices; offline simulation is not supported."
                )
                ctx.notifier.send("Auth failed — bot cannot start without market data.")
                sys.exit(1)

        # Order / position / risk
        ctx.order_manager = OrderManager(ctx.kite, market_data=ctx.market_data)
        ctx.order_manager.is_paper = ctx.mode == "paper"
        ctx.position_manager = PositionManager(ctx.order_manager, db=ctx.db)
        ctx.risk_manager = RiskManager(ctx.order_manager, db=ctx.db)
        ctx.risk_manager.market_data = ctx.market_data
        # Paper-mode capital callback for rejection sim.
        ctx.order_manager._get_available_capital = lambda: ctx.risk_manager.capital

        # Apply daily-plan risk overrides
        if ctx.daily_plan and ctx.daily_plan.risk_overrides:
            ctx.risk_manager.apply_runtime_overrides(
                max_trades=ctx.daily_plan.risk_overrides.get("max_trades"),
                risk_per_trade_pct=ctx.daily_plan.risk_overrides.get("risk_per_trade_pct"),
                max_open_positions=ctx.daily_plan.risk_overrides.get("max_open_positions"),
            )

        # Crash recovery — restore any orphaned positions from DB
        self._recover_orphaned_positions(ctx)

        # Live: reconcile against broker after recovery.
        if ctx.mode == "live" and ctx.kite:
            report = ctx.order_manager.reconcile_with_broker()
            if not report.get("clean", True):
                logger.error(
                    "Broker reconciliation FAILED at startup. "
                    f"Details: {report}. Refusing to start trading until "
                    "positions are reconciled manually."
                )
                ctx.notifier.send(
                    f"🚨 Broker drift at startup — bot halting.\n{report}"
                )
                sys.exit(2)

        # Strategy
        ctx.strategy = self._build_strategy(ctx.market_data)
        if isinstance(ctx.strategy, StrategyOrchestrator) and ctx.market_data:
            ctx.strategy.add_pairs_strategy(ctx.market_data)
        logger.info(f"Strategy: {ctx.strategy.name}")

        # Scanner
        if ctx.market_data:
            ctx.scanner = StockScanner(ctx.market_data)

        # Live capital from broker margins
        if ctx.kite and ctx.mode == "live":
            try:
                margins = ctx.kite.margins()
                available = margins["equity"]["available"]["live_balance"]
                ctx.risk_manager.update_capital(available)
                logger.info(f"Live capital: Rs {available:,.2f}")
            except Exception:
                logger.warning("Could not fetch margins, using configured capital")

        ctx.notifier.send(
            f"🤖 Trading Bot started in <b>{ctx.mode.upper()}</b> mode\n"
            f"Strategy: {ctx.strategy.name}\n"
            f"Capital: Rs {ctx.risk_manager.capital:,.2f}"
        )
        return ctx

    @staticmethod
    def _build_strategy(market_data):
        name = settings.STRATEGY
        if name == "ORB":
            return ORBStrategy()
        if name == "RSI_EMA":
            return RSIEMAStrategy()
        if name == "VWAP_SUPERTREND":
            return VWAPSupertrendStrategy()
        if name == "MEAN_REVERSION":
            return MeanReversionStrategy()
        if name == "PAIRS":
            return PairsTradingStrategy(market_data=market_data)
        if name == "MULTI":
            return StrategyOrchestrator()
        logger.warning(f"Unknown strategy '{name}', defaulting to ORB")
        return ORBStrategy()

    @staticmethod
    def _recover_orphaned_positions(ctx: BotContext) -> None:
        """Recover open positions from a previous crashed session.

        LIVE: reconstruct Order objects from the DB and inject them so
        reconcile_with_broker() can diff against actual broker state.

        PAPER: no broker to check; just clear the stale DB rows.
        """
        try:
            orphaned = ctx.db.get_open_positions()
            if not orphaned:
                if ctx.mode == "paper" or not ctx.kite:
                    ctx.db.clear_open_positions()
                return

            logger.warning(
                f"Found {len(orphaned)} orphaned positions from previous session"
            )
            for row in orphaned:
                logger.warning(
                    f"  Orphaned: {row['signal']} {row['symbol']} "
                    f"qty={row['quantity']} entry={row['entry_price']:.2f}"
                )

            if ctx.mode == "paper" or not ctx.kite:
                ctx.db.clear_open_positions()
                return

            for row in orphaned:
                order = Order(
                    order_id=row["order_id"],
                    symbol=row["symbol"],
                    exchange=row.get("exchange", "NSE"),
                    signal=Signal(row["signal"]),
                    quantity=row["quantity"],
                    price=row["entry_price"],
                    stop_loss=row["stop_loss"],
                    target=row["target"],
                    order_type="MARKET",
                    status=OrderStatus.EXECUTED,
                    executed_price=row["entry_price"],
                    is_paper=bool(row.get("is_paper", 0)),
                    is_open=True,
                    reason=row.get("reason", ""),
                    strategy=row.get("strategy", ""),
                )
                # Restore fields needed for partial exits, ATR trailing,
                # tick-rounded SLM modifies, and SLM cancellation.
                order.original_quantity = (
                    row.get("original_quantity") or row["quantity"]
                )
                order.entry_atr = float(row.get("entry_atr") or 0.0)
                order.tick_size = float(row.get("tick_size") or 0.05)
                order.sl_order_id = row.get("sl_order_id") or None
                order._original_stop_loss = float(
                    row.get("original_stop_loss") or row["stop_loss"]
                )
                ctx.order_manager.orders.append(order)
                ctx.position_manager.open_positions.append(order)
                logger.info(
                    f"Recovered position: {order.signal.value} {order.symbol} "
                    f"qty={order.quantity} (orig={order.original_quantity}, "
                    f"atr={order.entry_atr:.4f}, sl_id={order.sl_order_id})"
                )

            logger.info("Live mode: broker reconciliation will verify state next.")
        except Exception as e:
            logger.error(f"Crash recovery failed: {e}")
