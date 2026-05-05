"""
Multi-Strategy Orchestrator
────────────────────────────
Runs all strategies in parallel on each stock and takes the highest-confluence
signal. When multiple strategies agree on direction, the confluence score
gets boosted — this is a strong confirmation.

Enable with: STRATEGY = "MULTI" in settings.py
"""

import pandas as pd

from config import settings
from src.indicators.market_regime import MarketRegime
from src.strategy.base import BaseStrategy, Signal, TradeSignal
from src.strategy.confluence import calculate_confluence
from src.strategy.mean_reversion import MeanReversionStrategy
from src.strategy.orb import ORBStrategy
from src.strategy.pairs import PairsTradingStrategy
from src.strategy.rsi_ema import RSIEMAStrategy
from src.strategy.vwap_supertrend import VWAPSupertrendStrategy
from src.strategy.regime_tracker import RegimePerformanceTracker
from src.utils.logger import logger


class StrategyOrchestrator(BaseStrategy):
    """Runs all strategies and selects the best signal by confluence."""

    def __init__(self, tracker: RegimePerformanceTracker | None = None):
        self.strategies: list[BaseStrategy] = [
            ORBStrategy(),
            RSIEMAStrategy(),
            VWAPSupertrendStrategy(),
            MeanReversionStrategy(),
        ]
        # Lazy: only build a tracker if enabled; can be injected for tests.
        self.tracker: RegimePerformanceTracker | None = tracker
        if self.tracker is None and getattr(settings, "REGIME_TRACKER_ENABLED", True):
            try:
                self.tracker = RegimePerformanceTracker()
            except Exception as e:
                logger.debug(f"[MULTI] tracker init failed: {e}")
                self.tracker = None

    @property
    def name(self) -> str:
        return "MULTI"

    @property
    def orb_strategy(self) -> ORBStrategy:
        """Access the ORB strategy for setting opening range."""
        for s in self.strategies:
            if isinstance(s, ORBStrategy):
                return s
        return None

    def add_pairs_strategy(self, market_data) -> None:
        """Inject pairs strategy after market_data is available."""
        if getattr(settings, "ENABLE_PAIRS_TRADING", False):
            self.strategies.append(PairsTradingStrategy(market_data=market_data))
            logger.info("[MULTI] Pairs trading strategy enabled")

    def analyze(
        self,
        df: pd.DataFrame,
        symbol: str,
        df_htf: pd.DataFrame = None,
        regime: MarketRegime = None,
        vol_regime=None,
    ) -> TradeSignal:
        """
        Run all strategies and return the best signal.
        Multi-strategy agreement boosts confidence. When a regime tracker is
        present, each strategy's confluence is weighted by its historical
        (strategy, regime, vol_regime) edge; blacklisted cells are dropped.
        """
        signals: list[TradeSignal] = []

        dir_key = regime.value if regime is not None else "UNKNOWN"
        vol_key = vol_regime.value if vol_regime is not None else "NORMAL"

        for strategy in self.strategies:
            try:
                sig = strategy.analyze(df, symbol, df_htf=df_htf, regime=regime)
                if sig.signal == Signal.HOLD:
                    logger.debug(
                        f"[MULTI] {strategy.name} {symbol} -> HOLD: {sig.reason}"
                    )
                    continue
                # Regime-adaptive gating/weighting
                if self.tracker is not None:
                    if self.tracker.is_blacklisted(strategy.name, dir_key, vol_key):
                        logger.debug(
                            f"[MULTI] {strategy.name} blacklisted for "
                            f"({dir_key},{vol_key}); skipping"
                        )
                        continue
                    weight = self.tracker.weight_for(strategy.name, dir_key, vol_key)
                    sig.confluence_score = sig.confluence_score * weight
                signals.append(sig)
            except Exception as e:
                logger.debug(f"Strategy {strategy.name} error on {symbol}: {e}")

        if not signals:
            return self._hold(symbol, "No strategy generated a signal")

        # Separate by direction
        buy_signals = [s for s in signals if s.signal == Signal.BUY]
        sell_signals = [s for s in signals if s.signal == Signal.SELL]

        if buy_signals and not sell_signals:
            best = max(buy_signals, key=lambda s: s.confluence_score)
            # Boost for multi-strategy agreement
            agreement_bonus = (len(buy_signals) - 1) * 10
            best.confluence_score += agreement_bonus
            agreeing = [s.strategy for s in buy_signals]
            best.confirming_strategies = agreeing
            best.reason += f" | MULTI: {len(buy_signals)} strategies agree ({', '.join(agreeing)})"
            best.strategy = self.name
            return best

        elif sell_signals and not buy_signals:
            best = max(sell_signals, key=lambda s: s.confluence_score)
            agreement_bonus = (len(sell_signals) - 1) * 10
            best.confluence_score += agreement_bonus
            agreeing = [s.strategy for s in sell_signals]
            best.confirming_strategies = agreeing
            best.reason += f" | MULTI: {len(sell_signals)} strategies agree ({', '.join(agreeing)})"
            best.strategy = self.name
            return best

        else:
            # Conflicting signals — HOLD for safety
            buy_strats = [s.strategy for s in buy_signals]
            sell_strats = [s.strategy for s in sell_signals]
            return self._hold(
                symbol,
                f"Conflicting: BUY from {buy_strats}, SELL from {sell_strats}"
            )
