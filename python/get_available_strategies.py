#!/usr/bin/env python3
"""
Get available strategies from StrategyFactory.

Returns JSON list of strategy names and metadata.
"""

import json
import sys

try:
    from trading_bot.strategies.factory import StrategyFactory
    
    # Get all registered strategies
    strategies = StrategyFactory.get_available_strategies()
    
    # Convert to list of strategy names
    strategy_list = [
        {
            "name": name,
            "class": strategy_class.__name__
        }
        for name, strategy_class in strategies.items()
    ]
    
    # Output as JSON
    print(json.dumps(strategy_list))
    sys.exit(0)
    
except Exception as e:
    print(json.dumps({"error": str(e)}), file=sys.stderr)
    sys.exit(1)

