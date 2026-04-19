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
from src.strategy.orb import ORBStrategy
from src.strategy.rsi_ema import RSIEMAStrategy
from src.strategy.vwap_supertrend import VWAPSupertrendStrategy
from src.utils.logger import logger


class StrategyOrchestrator(BaseStrategy):
    """Runs all strategies and selects the best signal by confluence."""

    def __init__(self):
        self.strategies: list[BaseStrategy] = [
            ORBStrategy(),
            RSIEMAStrategy(),
            VWAPSupertrendStrategy(),
        ]

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

    def analyze(
        self,
        df: pd.DataFrame,
        symbol: str,
        df_htf: pd.DataFrame = None,
        regime: MarketRegime = None,
    ) -> TradeSignal:
        """
        Run all strategies and return the best signal.
        Multi-strategy agreement boosts confidence.
        """
        signals: list[TradeSignal] = []

        for strategy in self.strategies:
            try:
                sig = strategy.analyze(df, symbol, df_htf=df_htf, regime=regime)
                if sig.signal != Signal.HOLD:
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
            best.reason += f" | MULTI: {len(buy_signals)} strategies agree ({', '.join(agreeing)})"
            best.strategy = self.name
            return best

        elif sell_signals and not buy_signals:
            best = max(sell_signals, key=lambda s: s.confluence_score)
            agreement_bonus = (len(sell_signals) - 1) * 10
            best.confluence_score += agreement_bonus
            agreeing = [s.strategy for s in sell_signals]
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
