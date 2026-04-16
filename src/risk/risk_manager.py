"""
Risk Manager
────────────
The most important module in the entire bot.
Controls position sizing, enforces daily limits, and triggers circuit breakers.

Rules enforced:
- Max 1-2% risk per trade
- Max 3% daily loss → stop trading
- Max 5 trades per day
- Max 2 concurrent positions
- Min 1:2 risk/reward ratio
- Max 30% of capital in one position
- Pause after 3 consecutive losses
"""

from datetime import datetime, timedelta

from config import settings
from src.execution.order_manager import OrderManager
from src.strategy.base import TradeSignal, Signal
from src.utils.logger import logger


class RiskManager:
    """Enforces all risk management rules before allowing a trade."""

    def __init__(self, order_manager: OrderManager):
        self.order_manager = order_manager
        self.capital = settings.INITIAL_CAPITAL
        self._consecutive_losses = 0
        self._paused_until: datetime | None = None
        self._daily_loss = 0.0
        self._unrealized_pnl = 0.0

    def evaluate(self, signal: TradeSignal) -> TradeSignal | None:
        """
        Evaluate a trade signal against all risk rules.

        Returns:
            The signal with quantity set if approved, or None if rejected.
        """
        if signal.signal == Signal.HOLD:
            return None

        # ── Check circuit breakers ──
        rejection = self._check_circuit_breakers()
        if rejection:
            logger.warning(f"[RISK] Trade REJECTED for {signal.symbol}: {rejection}")
            return None

        # ── Check risk/reward ratio ──
        if signal.risk_reward_ratio < settings.MIN_RISK_REWARD_RATIO:
            logger.warning(
                f"[RISK] Trade REJECTED for {signal.symbol}: "
                f"R:R = {signal.risk_reward_ratio:.2f} < {settings.MIN_RISK_REWARD_RATIO}"
            )
            return None

        # ── Calculate position size ──
        quantity = self._calculate_position_size(signal)
        if quantity <= 0:
            logger.warning(f"[RISK] Trade REJECTED for {signal.symbol}: Calculated quantity = 0")
            return None

        signal.quantity = quantity

        logger.info(
            f"[RISK] Trade APPROVED for {signal.symbol}: "
            f"Qty={quantity}, Risk=Rs {signal.risk_per_share * quantity:.2f}, "
            f"R:R={signal.risk_reward_ratio:.1f}"
        )
        return signal

    def _check_circuit_breakers(self) -> str | None:
        """Check all circuit breaker conditions. Returns rejection reason or None."""

        # Daily loss limit (includes unrealized P&L from open positions)
        daily_pnl = self.order_manager.get_todays_pnl() + self._unrealized_pnl
        max_daily_loss = self.capital * (settings.MAX_DAILY_LOSS_PCT / 100)
        if daily_pnl < 0 and abs(daily_pnl) >= max_daily_loss:
            return f"Daily loss limit hit: Rs {daily_pnl:.2f} (max: Rs {max_daily_loss:.2f})"

        # Max trades per day
        trade_count = self.order_manager.get_todays_trade_count()
        if trade_count >= settings.MAX_TRADES_PER_DAY:
            return f"Max trades reached: {trade_count}/{settings.MAX_TRADES_PER_DAY}"

        # Max concurrent positions
        open_positions = len(self.order_manager.get_open_orders())
        if open_positions >= settings.MAX_OPEN_POSITIONS:
            return f"Max open positions: {open_positions}/{settings.MAX_OPEN_POSITIONS}"

        # Consecutive losses pause
        if self._paused_until and settings.now_ist() < self._paused_until:
            remaining = (self._paused_until - settings.now_ist()).seconds // 60
            return f"Paused for {remaining} more minutes after {settings.MAX_CONSECUTIVE_LOSSES} consecutive losses"

        return None

    def _calculate_position_size(self, signal: TradeSignal) -> int:
        """
        Calculate how many shares to buy based on risk rules.

        Position Size = (Capital × Risk%) / Risk per share
        Capped by maximum position percentage.
        """
        risk_per_share = signal.risk_per_share
        if risk_per_share <= 0:
            return 0

        # Risk-based sizing: max 1-2% of capital at risk
        max_risk_amount = self.capital * (settings.RISK_PER_TRADE_PCT / 100)
        quantity_by_risk = int(max_risk_amount / risk_per_share)

        # Position value cap: max 30% of capital in one trade
        max_position_value = self.capital * (settings.MAX_POSITION_PCT / 100)
        quantity_by_value = int(max_position_value / signal.price) if signal.price > 0 else 0

        # Take the smaller of the two
        quantity = min(quantity_by_risk, quantity_by_value)

        # Ensure at least 1 share, unless even 1 exceeds risk limits
        if quantity < 1:
            if risk_per_share > max_risk_amount:
                return 0  # Even 1 share exceeds allowed risk
            return 1
        return quantity

    def record_trade_result(self, pnl: float):
        """Record a completed trade's P&L for circuit breaker tracking."""
        if pnl < 0:
            self._consecutive_losses += 1
            if self._consecutive_losses >= settings.MAX_CONSECUTIVE_LOSSES:
                self._paused_until = settings.now_ist() + timedelta(
                    minutes=settings.PAUSE_AFTER_LOSSES_MINUTES
                )
                logger.warning(
                    f"[RISK] {self._consecutive_losses} consecutive losses! "
                    f"Pausing for {settings.PAUSE_AFTER_LOSSES_MINUTES} minutes"
                )
        else:
            self._consecutive_losses = 0
            self._paused_until = None

    def set_unrealized_pnl(self, amount: float):
        """Update unrealized P&L from open positions (called each cycle)."""
        self._unrealized_pnl = amount

    def update_capital(self, new_capital: float):
        """Update the current capital (e.g., from Zerodha margins)."""
        self.capital = new_capital

    def get_status(self) -> dict:
        """Get current risk status summary."""
        daily_pnl = self.order_manager.get_todays_pnl()
        max_loss = self.capital * (settings.MAX_DAILY_LOSS_PCT / 100)
        return {
            "capital": self.capital,
            "daily_pnl": daily_pnl,
            "daily_loss_limit": max_loss,
            "daily_loss_remaining": max_loss - abs(min(daily_pnl, 0)),
            "trades_today": self.order_manager.get_todays_trade_count(),
            "max_trades": settings.MAX_TRADES_PER_DAY,
            "open_positions": len(self.order_manager.get_open_orders()),
            "max_positions": settings.MAX_OPEN_POSITIONS,
            "consecutive_losses": self._consecutive_losses,
            "is_paused": self._paused_until is not None and settings.now_ist() < self._paused_until,
        }
