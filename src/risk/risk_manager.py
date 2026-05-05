"""
Risk Manager — Enhanced
───────────────────────
The most important module in the entire bot.
Controls position sizing, enforces daily limits, and triggers circuit breakers.

Enhanced with:
- Intraday drawdown tracking (high-water mark)
- Volatility-adjusted sizing (India VIX)
- Performance-adaptive sizing (half-Kelly criterion)
- Equity curve trading (reduce size during drawdowns)
- Sector-aware position limits
- Time-of-day position scaling
- Confluence score threshold
"""

from datetime import datetime, timedelta

from config import settings
from src.execution.order_manager import OrderManager
from src.risk.sector_map import get_sector
from src.strategy.base import TradeSignal, Signal
from src.utils.logger import logger


def _isnan(x) -> bool:
    try:
        return x != x  # NaN is never equal to itself
    except Exception:
        return False


class RiskManager:
    """Enforces all risk management rules before allowing a trade."""

    def __init__(self, order_manager: OrderManager, db=None):
        self.order_manager = order_manager
        self.db = db
        self.capital = settings.INITIAL_CAPITAL
        self._consecutive_losses = 0
        self._paused_until: datetime | None = None
        self._daily_loss = 0.0
        self._unrealized_pnl = 0.0

        # Per-symbol same-day stop-loss cooldown (added 2026-05-05).
        # Populated by record_trade_result() when a trade closes via SL hit.
        # Resets naturally on bot restart (launchd starts fresh each morning).
        self._stopped_symbols_today: set[str] = set()

        # Intraday drawdown tracking
        self._intraday_high_water_mark = 0.0
        self._intraday_drawdown = 0.0

        # Volatility regime (set at market open)
        self._vix_level: float | None = None

        # Optional reference to MarketData for circuit-limit checks.
        # Wired by main.py after both components are constructed.
        self.market_data = None

        # ── Runtime risk overrides (from config/daily_plan.json) ──
        # Set by RiskManager.apply_runtime_overrides() at startup. Each
        # override is already clamped to the settings cap by plan_loader,
        # but we re-clamp here as defence in depth. None means "use settings".
        self._override_max_trades: int | None = None
        self._override_risk_pct: float | None = None
        self._override_max_positions: int | None = None

        # Phase 3E: restore persisted intraday risk state (survives crash-restart)
        if self.db and getattr(settings, "PERSIST_INTRADAY_HWM", False):
            try:
                state = self.db.load_risk_state()
                if state:
                    self._intraday_high_water_mark = state.get("hwm", 0.0)
                    self._intraday_drawdown = state.get("drawdown", 0.0)
                    logger.info(
                        f"[RISK] Restored persisted risk state: "
                        f"HWM={self._intraday_high_water_mark:.2f}, "
                        f"DD={self._intraday_drawdown:.2f}"
                    )
            except Exception as e:
                logger.error(
                    f"[RISK] Failed to restore persisted risk state: {e} — "
                    f"drawdown circuit breaker starts from zero"
                )

    # ── Runtime-override accessors (daily-plan driven) ──────────────────

    def _effective_max_trades(self) -> int:
        cap = settings.MAX_TRADES_PER_DAY
        if self._override_max_trades is None:
            return cap
        return min(cap, int(self._override_max_trades))

    def _effective_max_positions(self) -> int:
        cap = settings.MAX_OPEN_POSITIONS
        if self._override_max_positions is None:
            return cap
        return min(cap, int(self._override_max_positions))

    def _effective_risk_pct(self) -> float:
        cap = settings.RISK_PER_TRADE_PCT
        if self._override_risk_pct is None:
            return cap
        return min(cap, float(self._override_risk_pct))

    def apply_runtime_overrides(
        self,
        *,
        max_trades: int | None = None,
        risk_per_trade_pct: float | None = None,
        max_open_positions: int | None = None,
    ) -> dict[str, float]:
        """Apply per-day risk overrides from `config/daily_plan.json`.

        All overrides are clamped to the settings caps (tighter-only). Passing
        None for an argument leaves that override unchanged. Returns the
        effective cap dict after applying.
        """
        if max_trades is not None:
            v = max(1, min(int(max_trades), settings.MAX_TRADES_PER_DAY))
            self._override_max_trades = v
            logger.info(f"[RISK] Override: max_trades = {v} (cap={settings.MAX_TRADES_PER_DAY})")
        if risk_per_trade_pct is not None:
            v = max(0.1, min(float(risk_per_trade_pct), settings.RISK_PER_TRADE_PCT))
            self._override_risk_pct = v
            logger.info(f"[RISK] Override: risk_per_trade_pct = {v} (cap={settings.RISK_PER_TRADE_PCT})")
        if max_open_positions is not None:
            v = max(1, min(int(max_open_positions), settings.MAX_OPEN_POSITIONS))
            self._override_max_positions = v
            logger.info(f"[RISK] Override: max_open_positions = {v} (cap={settings.MAX_OPEN_POSITIONS})")
        return {
            "max_trades": self._effective_max_trades(),
            "risk_per_trade_pct": self._effective_risk_pct(),
            "max_open_positions": self._effective_max_positions(),
        }

    def evaluate(self, signal: TradeSignal) -> TradeSignal | None:
        """
        Evaluate a trade signal against all risk rules.

        Returns:
            The signal with quantity set if approved, or None if rejected.
        """
        if signal.signal == Signal.HOLD:
            return None

        # ── Check circuit breakers ──
        rejection = self._check_circuit_breakers(signal)
        if rejection:
            logger.warning(f"[RISK] Trade REJECTED for {signal.symbol}: {rejection}")
            return None

        # ── Hard-reject: no shorts when RSI is oversold ──
        if signal.rsi is not None and signal.signal == Signal.SELL and signal.rsi < 30:
            logger.warning(
                f"[RISK] Trade REJECTED for {signal.symbol}: "
                f"SELL at RSI {signal.rsi:.1f} < 30 (oversold bounce risk)"
            )
            return None

        # ── Min confirmations gate (added 2026-05-05) ──
        # Require N strategies to agree before entering. Single-strategy
        # entries produced 100% of the May 4–5 paper losses.
        # Escape hatch: a *single* strategy can still trigger an entry if its
        # confluence_score is at or above HIGH_CONVICTION_SCORE.
        min_conf = getattr(settings, "MIN_CONFIRMATIONS", 1)
        if min_conf > 1:
            n_conf = len(signal.confirming_strategies) if signal.confirming_strategies else 1
            high_conv = getattr(settings, "HIGH_CONVICTION_SCORE", None)
            if n_conf < min_conf and not (
                high_conv is not None and signal.confluence_score >= high_conv
            ):
                logger.warning(
                    f"[RISK] Trade REJECTED for {signal.symbol}: "
                    f"only {n_conf} strategy confirms (min {min_conf}, "
                    f"score {signal.confluence_score:.1f} < high-conv {high_conv}) "
                    f"[{', '.join(signal.confirming_strategies) or signal.strategy}]"
                )
                return None
            if n_conf < min_conf:
                logger.info(
                    f"[RISK] {signal.symbol} single-strategy entry allowed "
                    f"(score {signal.confluence_score:.1f} >= {high_conv} high-conv) "
                    f"[{signal.strategy}]"
                )

        # ── Check confluence score threshold ──
        if getattr(settings, 'ENABLE_CONFLUENCE_SCORING', False):
            threshold = getattr(settings, 'CONFLUENCE_THRESHOLD', 55)
            if signal.confluence_score > 0 and signal.confluence_score < threshold:
                logger.warning(
                    f"[RISK] Trade REJECTED for {signal.symbol}: "
                    f"Confluence {signal.confluence_score:.0f} < {threshold}"
                )
                return None

        # ── Check risk/reward ratio (net of round-trip costs) ──
        rr_net = self._net_rr(signal)
        if rr_net < settings.MIN_RISK_REWARD_RATIO:
            logger.warning(
                f"[RISK] Trade REJECTED for {signal.symbol}: "
                f"R:R(net) = {rr_net:.2f} < {settings.MIN_RISK_REWARD_RATIO} "
                f"(gross={signal.risk_reward_ratio:.2f})"
            )
            return None

        # ── Check circuit band ──
        if getattr(settings, "ENABLE_CIRCUIT_LIMIT_CHECK", False) and self.market_data:
            band = None
            try:
                band = self.market_data.get_circuit_limits(signal.symbol)
            except Exception as e:
                logger.warning(f"[RISK] Circuit limit check failed for {signal.symbol}: {e}")
                band = None
            if band:
                lo, hi = band["lower"], band["upper"]
                # Stop must lie inside the band, and price itself can't be
                # frozen at a circuit (price == limit → un-tradeable).
                if not (lo < signal.stop_loss < hi):
                    logger.warning(
                        f"[RISK] Trade REJECTED for {signal.symbol}: "
                        f"SL {signal.stop_loss:.2f} outside circuit band "
                        f"[{lo:.2f}, {hi:.2f}]"
                    )
                    return None
                if signal.price <= lo or signal.price >= hi:
                    logger.warning(
                        f"[RISK] Trade REJECTED for {signal.symbol}: "
                        f"price {signal.price:.2f} at circuit limit"
                    )
                    return None

        # ── Calculate position size ──
        quantity = self._calculate_position_size(signal)
        if quantity <= 0:
            logger.warning(f"[RISK] Trade REJECTED for {signal.symbol}: Calculated quantity = 0")
            return None

        signal.quantity = quantity

        # ── Fat-finger guard ──
        ff_reject = self._fat_finger_check(signal)
        if ff_reject:
            logger.warning(f"[RISK] Trade REJECTED for {signal.symbol}: {ff_reject}")
            return None

        # ── Correlation limit (Phase 3E) ──
        corr_reject = self._correlation_check(signal)
        if corr_reject:
            logger.warning(f"[RISK] Trade REJECTED for {signal.symbol}: {corr_reject}")
            return None

        logger.info(
            f"[RISK] Trade APPROVED for {signal.symbol}: "
            f"Qty={quantity}, Risk=Rs {signal.risk_per_share * quantity:.2f}, "
            f"R:R={signal.risk_reward_ratio:.1f}"
            + (f", Confluence={signal.confluence_score:.0f}" if signal.confluence_score > 0 else "")
        )
        return signal

    def _check_circuit_breakers(self, signal: TradeSignal = None) -> str | None:
        """Check all circuit breaker conditions. Returns rejection reason or None."""

        # Per-symbol same-day stop-loss cooldown (added 2026-05-05)
        if (
            signal is not None
            and getattr(settings, "STOPPED_SYMBOL_COOLDOWN", False)
            and signal.symbol in self._stopped_symbols_today
        ):
            return (
                f"{signal.symbol} stopped out earlier today "
                f"— no re-entry (cooldown)"
            )

        # Daily loss limit (includes unrealized P&L from open positions)
        daily_pnl = self.order_manager.get_todays_pnl() + self._unrealized_pnl
        max_daily_loss = self.capital * (settings.MAX_DAILY_LOSS_PCT / 100)
        if daily_pnl < 0 and abs(daily_pnl) >= max_daily_loss:
            return f"Daily loss limit hit: Rs {daily_pnl:.2f} (max: Rs {max_daily_loss:.2f})"

        # Intraday drawdown limit
        max_drawdown_pct = getattr(settings, 'MAX_INTRADAY_DRAWDOWN_PCT', 0)
        if max_drawdown_pct > 0 and self._intraday_drawdown > 0:
            max_drawdown = self.capital * (max_drawdown_pct / 100)
            if self._intraday_drawdown >= max_drawdown:
                return (
                    f"Intraday drawdown limit hit: Rs {self._intraday_drawdown:.2f} "
                    f"(max: Rs {max_drawdown:.2f})"
                )

        # Max trades per day
        trade_count = self.order_manager.get_todays_trade_count()
        if trade_count >= self._effective_max_trades():
            return f"Max trades reached: {trade_count}/{self._effective_max_trades()}"

        # Max concurrent positions
        open_positions = len(self.order_manager.get_open_orders())
        if open_positions >= self._effective_max_positions():
            return f"Max open positions: {open_positions}/{self._effective_max_positions()}"

        # Sector concentration limit
        if signal is not None and getattr(settings, 'MAX_POSITIONS_PER_SECTOR', 0) > 0:
            sector_rejection = self._check_sector_limit(signal.symbol)
            if sector_rejection:
                return sector_rejection

        # Consecutive losses pause
        if self._paused_until and settings.now_ist() < self._paused_until:
            remaining = (self._paused_until - settings.now_ist()).seconds // 60
            return f"Paused for {remaining} more minutes after {settings.MAX_CONSECUTIVE_LOSSES} consecutive losses"

        return None

    def _check_sector_limit(self, symbol: str) -> str | None:
        """Check if adding this symbol would exceed sector concentration limit."""
        max_per_sector = getattr(settings, 'MAX_POSITIONS_PER_SECTOR', 0)
        if max_per_sector <= 0:
            return None

        new_sector = get_sector(symbol)
        if new_sector == "Unknown":
            return None

        open_orders = self.order_manager.get_open_orders()
        sector_count = sum(1 for o in open_orders if get_sector(o.symbol) == new_sector)

        if sector_count >= max_per_sector:
            existing = [o.symbol for o in open_orders if get_sector(o.symbol) == new_sector]
            return (
                f"Sector limit: already holding {existing} in {new_sector} "
                f"({sector_count}/{max_per_sector})"
            )
        return None

    def _calculate_position_size(self, signal: TradeSignal) -> int:
        """
        Calculate how many shares to buy based on risk rules.

        Position Size = (Capital x Risk% x Adjustments) / Risk per share
        Capped by maximum position percentage.
        """
        risk_per_share = signal.risk_per_share
        if risk_per_share <= 0:
            return 0

        # Base risk percentage, then apply multipliers
        risk_pct = self._get_adjusted_risk_pct()

        # Risk-based sizing
        max_risk_amount = self.capital * (risk_pct / 100)
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

    def _get_adjusted_risk_pct(self) -> float:
        """
        Calculate adjusted risk percentage after all multipliers.
        Multiplicative chain: base_risk * vix_mult * kelly_mult * equity_mult * time_mult
        """
        base_risk = self._effective_risk_pct()

        # 1. Volatility (VIX) adjustment
        vix_mult = self._get_vix_multiplier()

        # 2. Kelly criterion adjustment
        kelly_mult = self._get_kelly_multiplier()

        # 3. Equity curve adjustment
        equity_mult = self._get_equity_curve_multiplier()

        # 4. Time-of-day adjustment
        time_mult = self._get_time_multiplier()

        adjusted = base_risk * vix_mult * kelly_mult * equity_mult * time_mult

        # Clamp: never exceed 150% of effective base (upper cap guards against
        # runaway Kelly × VIX stacking), and never exceed the *settings* base
        # cap either — a runtime override can only tighten, never loosen.
        hard_cap = min(base_risk * 1.5, settings.RISK_PER_TRADE_PCT * 1.5)
        adjusted = max(0.0, min(adjusted, hard_cap))

        return adjusted

    def _get_vix_multiplier(self) -> float:
        """Scale position size based on India VIX level."""
        if not getattr(settings, 'VOLATILITY_SCALING_ENABLED', False) or self._vix_level is None:
            return 1.0

        vix = self._vix_level
        vix_low = getattr(settings, 'VIX_LOW', 12.0)
        vix_high = getattr(settings, 'VIX_HIGH', 20.0)
        vix_extreme = getattr(settings, 'VIX_EXTREME', 25.0)

        if vix < vix_low:
            return 1.2  # Low vol — slightly larger positions
        elif vix < vix_high:
            return 1.0  # Normal
        elif vix < vix_extreme:
            return 0.6  # High vol — reduce
        else:
            return 0.3  # Extreme vol — minimal size

    def _get_kelly_multiplier(self) -> float:
        """Half-Kelly criterion based on recent trade performance."""
        if not getattr(settings, 'KELLY_ENABLED', False):
            return 1.0

        min_trades = getattr(settings, 'KELLY_MIN_TRADES', 20)

        # Session-level closed orders
        all_orders = self.order_manager.orders
        closed_orders = [o for o in all_orders if not o.is_open and o.pnl != 0]
        session_pnls = [o.pnl for o in closed_orders]

        # Augment with DB history when configured
        pnls = list(session_pnls)
        if self.db and getattr(settings, "KELLY_USE_DB_HISTORY", False):
            try:
                db_trades = self.db.get_closed_trades(limit=500)
                pnls.extend(t["pnl"] for t in db_trades if t.get("pnl", 0) != 0)
            except Exception as e:
                logger.warning(f"[RISK] Kelly DB history load failed: {e} — using session-only data")

        if len(pnls) < min_trades:
            return 1.0

        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        if not wins or not losses:
            return 1.0

        win_rate = len(wins) / len(pnls)
        avg_win = sum(wins) / len(wins)
        avg_loss = abs(sum(losses) / len(losses))

        if avg_loss <= 0:
            return 1.0

        win_loss_ratio = avg_win / avg_loss
        # Kelly fraction: K = W - (1-W)/R
        kelly = win_rate - ((1 - win_rate) / win_loss_ratio)
        # Half-Kelly for safety, clamped
        return max(0.25, min(kelly / 2 + 0.5, 1.5))

    def _get_equity_curve_multiplier(self) -> float:
        """Reduce size during drawdown periods."""
        if not getattr(settings, 'EQUITY_CURVE_TRADING_ENABLED', False) or not self.db:
            return 1.0

        try:
            lookback = getattr(settings, 'EQUITY_CURVE_LOOKBACK_DAYS', 10)
            summaries = self.db.get_daily_summaries(lookback)

            if not summaries:
                return 1.0

            # Check for consecutive losing days
            consecutive_losing = 0
            for s in summaries:
                if s.get("total_pnl", 0) < 0:
                    consecutive_losing += 1
                else:
                    break

            severe_threshold = getattr(settings, 'EQUITY_CURVE_SEVERE_THRESHOLD', 3)
            if consecutive_losing >= severe_threshold:
                return getattr(settings, 'EQUITY_CURVE_SEVERE_SCALE', 0.25)

            # Check cumulative P&L trend
            cumulative_pnl = sum(s.get("total_pnl", 0) for s in summaries)
            if cumulative_pnl < 0:
                return getattr(settings, 'EQUITY_CURVE_DRAWDOWN_SCALE', 0.5)

            return 1.0
        except Exception as e:
            logger.warning(f"[RISK] Equity curve calculation failed: {e} — using 1.0x sizing")
            return 1.0

    def _get_time_multiplier(self) -> float:
        """Adjust position size based on time of day."""
        if not getattr(settings, 'ENABLE_TIME_SCALING', False):
            return 1.0

        now = settings.now_ist()
        minutes = now.hour * 60 + now.minute

        if minutes < 570:    # Before 9:30
            return 0.0       # No trading
        elif minutes < 630:  # 9:30 - 10:30 — Morning breakout session
            return 1.0
        elif minutes < 780:  # 10:30 - 13:00 — Midday lull
            return 0.6
        elif minutes < 870:  # 13:00 - 14:30 — Afternoon session
            return 0.8
        elif minutes < 900:  # 14:30 - 15:00 — Pre-close
            return 0.5
        else:
            return 0.0       # No trading

    def set_vix_level(self, vix: float):
        """Set the current India VIX level (called at market open)."""
        self._vix_level = vix
        logger.info(f"[RISK] VIX level set: {vix:.2f}")

    def update_intraday_equity(self, realized_pnl: float, unrealized_pnl: float):
        """Update intraday equity tracking for drawdown circuit breaker."""
        total_pnl = realized_pnl + unrealized_pnl

        if total_pnl > self._intraday_high_water_mark:
            self._intraday_high_water_mark = total_pnl

        self._intraday_drawdown = self._intraday_high_water_mark - total_pnl

        # Phase 3E: persist so the circuit breaker survives a restart
        if self.db and getattr(settings, "PERSIST_INTRADAY_HWM", False):
            try:
                self.db.save_risk_state(
                    hwm=self._intraday_high_water_mark,
                    drawdown=self._intraday_drawdown,
                    daily_loss=min(0.0, total_pnl),
                )
            except Exception as e:
                logger.error(
                    f"[RISK] Failed to persist risk state (HWM/drawdown): {e} — "
                    f"circuit breaker will reset on next restart"
                )

    # ── Phase 3E helpers ──
    def _net_rr(self, signal: TradeSignal) -> float:
        """Risk:reward net of round-trip costs (brokerage+STT+slippage proxy)."""
        try:
            gross = signal.risk_reward_ratio
        except Exception as e:
            logger.debug(f"[RISK] net R:R calc failed for {signal.symbol}: {e}")
            return 0.0
        costs_bps = getattr(settings, "COSTS_ROUND_TRIP_BPS", 0)
        if costs_bps <= 0 or signal.price <= 0:
            return gross
        cost_per_share = signal.price * (costs_bps / 10000.0)
        risk = signal.risk_per_share
        reward = abs(signal.target - signal.price) if signal.target else 0.0
        if risk <= 0 or reward <= 0:
            return gross
        net_reward = max(0.0, reward - cost_per_share)
        net_risk = risk + cost_per_share
        return net_reward / net_risk if net_risk > 0 else 0.0

    def _fat_finger_check(self, signal: TradeSignal) -> str | None:
        """Hard cap on notional size + risk. Returns rejection reason or None."""
        max_notional_pct = getattr(settings, "FAT_FINGER_MAX_NOTIONAL_PCT", 0)
        if max_notional_pct <= 0:
            return None
        notional = signal.quantity * signal.price
        notional_cap = self.capital * (max_notional_pct / 100)
        if notional > notional_cap:
            return (
                f"fat-finger: notional Rs {notional:.0f} > cap Rs {notional_cap:.0f}"
                f" ({max_notional_pct}% of capital)"
            )
        # Risk cap = 2% of capital (hard, independent of risk_pct scaling)
        risk_amount = signal.quantity * signal.risk_per_share
        risk_cap = self.capital * 0.02
        if risk_amount > risk_cap:
            return (
                f"fat-finger: trade risk Rs {risk_amount:.0f} > 2% cap Rs {risk_cap:.0f}"
            )
        return None

    def _correlation_check(self, signal: TradeSignal) -> str | None:
        """Reject if avg daily-return correlation with open positions exceeds threshold."""
        if not getattr(settings, "CORRELATION_LIMIT_ENABLED", False):
            return None
        if self.market_data is None:
            return None
        threshold = getattr(settings, "CORRELATION_LIMIT_THRESHOLD", 0.7)
        lookback = getattr(settings, "CORRELATION_LOOKBACK_DAYS", 20)

        open_orders = self.order_manager.get_open_orders()
        open_syms = [o.symbol for o in open_orders if o.symbol != signal.symbol]
        if not open_syms:
            return None

        try:
            new_ret = self._daily_returns(signal.symbol, lookback)
            if new_ret is None or len(new_ret) < 5:
                return None
            corrs = []
            for sym in open_syms:
                r = self._daily_returns(sym, lookback)
                if r is None or len(r) < 5:
                    continue
                n = min(len(new_ret), len(r))
                c = new_ret.tail(n).corr(r.tail(n))
                if c is not None and not _isnan(c):
                    corrs.append(abs(c))
            if not corrs:
                return None
            avg_corr = sum(corrs) / len(corrs)
            if avg_corr > threshold:
                return (
                    f"correlation {avg_corr:.2f} > {threshold:.2f} "
                    f"with open book {open_syms}"
                )
        except Exception as e:
            logger.debug(f"[RISK] correlation check error: {e}")
        return None

    def _daily_returns(self, symbol: str, days: int):
        """Fetch daily % returns series for correlation calc. Returns None on failure."""
        try:
            df = self.market_data.get_historical_data(symbol, interval="day", days=days + 2)
            if df is None or df.empty or "close" not in df.columns:
                return None
            return df["close"].pct_change().dropna()
        except Exception:
            return None

    def record_trade_result(self, pnl: float, symbol: str | None = None, exit_reason: str | None = None):
        """Record a completed trade's P&L for circuit breaker tracking.

        Args:
            pnl: Realised P&L for the closed trade.
            symbol: (optional) Symbol that was closed; used for per-symbol
                same-day cooldown tracking when ``exit_reason`` indicates SL.
            exit_reason: (optional) Free-text exit reason from the order
                manager (e.g. ``"Stop-loss hit at 109.74"``). Anything starting
                with ``"Stop-loss"`` triggers cooldown.
        """
        # Per-symbol cooldown: track this symbol if it stopped out today
        if (
            symbol
            and exit_reason
            and getattr(settings, "STOPPED_SYMBOL_COOLDOWN", False)
            and exit_reason.lower().startswith("stop-loss")
        ):
            self._stopped_symbols_today.add(symbol)
            logger.warning(
                f"[RISK] {symbol} added to same-day cooldown set "
                f"(SL hit) — no re-entry today"
            )

        if pnl < 0:
            self._consecutive_losses += 1
            if self._consecutive_losses >= settings.MAX_CONSECUTIVE_LOSSES:
                now = settings.now_ist()
                stop_time = now.replace(
                    hour=int(settings.STOP_NEW_TRADES.split(":")[0]),
                    minute=int(settings.STOP_NEW_TRADES.split(":")[1]),
                    second=0, microsecond=0,
                )
                mins_remaining = (stop_time - now).total_seconds() / 60

                if mins_remaining < 45:
                    logger.warning(
                        f"[RISK] {self._consecutive_losses} consecutive losses! "
                        f"Skipping pause — only {mins_remaining:.0f} mins left in session"
                    )
                else:
                    self._paused_until = now + timedelta(
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
            "max_trades": self._effective_max_trades(),
            "open_positions": len(self.order_manager.get_open_orders()),
            "max_positions": self._effective_max_positions(),
            "consecutive_losses": self._consecutive_losses,
            "is_paused": self._paused_until is not None and settings.now_ist() < self._paused_until,
            "intraday_drawdown": self._intraday_drawdown,
            "intraday_hwm": self._intraday_high_water_mark,
            "vix_level": self._vix_level,
            "adjusted_risk_pct": self._get_adjusted_risk_pct(),
        }
