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
from trading_bot.strategies.new_listing.new_listing_strategy import NewListingStrategy

__all__ = [
    "BaseAnalysisModule",
    "CandleAdapter",
    "StrategyFactory",
    "AlexAnalysisModule",
    "CointegrationAnalysisModule",
    "PromptStrategy",
    "NewListingStrategy",
]

# Register strategies with factory
# Strategy classes define their own names - factory uses those names
StrategyFactory.register_strategy(PromptStrategy.STRATEGY_NAME, PromptStrategy)
StrategyFactory.register_strategy(AlexAnalysisModule.STRATEGY_NAME, AlexAnalysisModule)
StrategyFactory.register_strategy(CointegrationAnalysisModule.STRATEGY_NAME, CointegrationAnalysisModule)
StrategyFactory.register_strategy(NewListingStrategy.STRATEGY_NAME, NewListingStrategy)

