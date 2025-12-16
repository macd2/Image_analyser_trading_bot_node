"""
Prompt Strategy - Independent chart-based trading strategy.

Self-contained strategy with its own copies of:
- sourcer.py (chart capture from TradingView)
- cleaner.py (outdated chart cleanup)
- analyzer.py (chart analysis with OpenAI)
- prompt_strategy.py (orchestration)

This strategy is completely independent and can be swapped with other strategies.
"""

from .prompt_strategy import PromptStrategy

__all__ = ["PromptStrategy"]
