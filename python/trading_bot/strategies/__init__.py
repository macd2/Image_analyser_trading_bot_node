"""
Strategies module - Pluggable analysis strategies.

Provides:
- BaseAnalysisModule: Abstract base for all strategies
- CandleAdapter: Unified interface for candle data
- StrategyFactory: Factory for creating strategies
- Built-in strategies: AlexAnalysisModule, CointegrationAnalysisModule, etc.
"""

from trading_bot.strategies.base import BaseAnalysisModule
from trading_bot.strategies.candle_adapter import CandleAdapter
from trading_bot.strategies.factory import StrategyFactory
from trading_bot.strategies.alex.alex_analysis_module import AlexAnalysisModule
from trading_bot.strategies.cointegration.cointegration_analysis_module import CointegrationAnalysisModule
from trading_bot.strategies.prompt.prompt_strategy import PromptStrategy

__all__ = [
    "BaseAnalysisModule",
    "CandleAdapter",
    "StrategyFactory",
    "AlexAnalysisModule",
    "CointegrationAnalysisModule",
    "PromptStrategy",
]

# Register strategies with factory
StrategyFactory.register_strategy("prompt", PromptStrategy)
StrategyFactory.register_strategy("alex", AlexAnalysisModule)
StrategyFactory.register_strategy("cointegration", CointegrationAnalysisModule)

