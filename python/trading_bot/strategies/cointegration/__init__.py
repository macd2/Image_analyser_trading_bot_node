"""
Cointegration Strategy - Pairs trading strategy based on cointegration.

Provides:
- CointegrationAnalysisModule: Cointegration-based pairs trading strategy
- PairScreener: Utility for discovering cointegrated pairs
- CointegrationStrategy: Spread trading implementation
"""

from trading_bot.strategies.cointegration.cointegration_analysis_module import CointegrationAnalysisModule
from trading_bot.strategies.cointegration.pair_screener import PairScreener
from trading_bot.strategies.cointegration.spread_trading_cointegrated import CointegrationStrategy

__all__ = [
    "CointegrationAnalysisModule",
    "PairScreener",
    "CointegrationStrategy",
]

