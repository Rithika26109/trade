"""
BotContext
──────────
Shared state container threaded through Bootstrap → Runtime → EODManager.
Holds all components plus per-day mutable state. A single object reference
keeps the three orchestrators decoupled while letting them mutate the same
state (open positions, watchlist, regime cache, control flags).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.utils.db import TradeDB
from src.utils.notifier import Notifier

if TYPE_CHECKING:
    from kiteconnect import KiteConnect

    from src.data.market_data import MarketData
    from src.data.websocket import TickerManager
    from src.execution.order_manager import OrderManager
    from src.execution.position_manager import PositionManager
    from src.risk.risk_manager import RiskManager
    from src.scanner.stock_scanner import StockScanner
    from src.strategy.base import BaseStrategy
    from src.utils.plan_loader import DailyPlan


@dataclass
class BotContext:
    """Mutable per-session state shared across orchestrator components."""

    mode: str

    # Components — populated by Bootstrap.setup()
    db: TradeDB = field(default_factory=TradeDB)
    notifier: Notifier = field(default_factory=Notifier)
    kite: "KiteConnect | None" = None
    market_data: "MarketData | None" = None
    ticker: "TickerManager | None" = None
    order_manager: "OrderManager | None" = None
    position_manager: "PositionManager | None" = None
    risk_manager: "RiskManager | None" = None
    strategy: "BaseStrategy | None" = None
    scanner: "StockScanner | None" = None
    daily_plan: "DailyPlan | None" = None

    # Today's runtime state
    todays_watchlist: list[str] = field(default_factory=list)
    instrument_tokens: dict[str, int] = field(default_factory=dict)
    token_to_symbol: dict[int, str] = field(default_factory=dict)
    last_dir_regime: dict[str, str] = field(default_factory=dict)
    last_vol_regime: dict[str, str] = field(default_factory=dict)
    logged_order_ids: set[str] = field(default_factory=set)

    # Control flags
    running: bool = False
    shutting_down: bool = False
    eod_done: bool = False
