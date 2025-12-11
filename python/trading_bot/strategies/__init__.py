"""
Strategies module - Pluggable analysis strategies.

Provides:
- BaseAnalysisModule: Abstract base for all strategies
- CandleAdapter: Unified interface for candle data
- StrategyFactory: Factory for creating strategies
- Built-in strategies: PromptAnalysisModule, AlexAnalysisModule, etc.
"""

from trading_bot.strategies.base import BaseAnalysisModule
from trading_bot.strategies.candle_adapter import CandleAdapter
from trading_bot.strategies.factory import StrategyFactory
from trading_bot.strategies.alex_analysis_module import AlexAnalysisModule

__all__ = [
    "BaseAnalysisModule",
    "CandleAdapter",
    "StrategyFactory",
    "AlexAnalysisModule",
]

