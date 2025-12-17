#!/usr/bin/env python3
"""
Get strategy settings schema.

Usage:
    python get_strategy_settings_schema.py <strategy_type>

Returns JSON with the settings schema for the given strategy type.
"""

import sys
import json
import logging

# Configure logging
logging.basicConfig(level=logging.ERROR)

def get_strategy_settings_schema(strategy_type: str) -> dict:
    """
    Get the settings schema for a given strategy type.
    
    Args:
        strategy_type: Strategy type ('price_based' or 'spread_based')
    
    Returns:
        Dict with settings schema
    """
    try:
        from trading_bot.strategies.prompt.prompt_strategy import PromptStrategy
        from trading_bot.strategies.cointegration.cointegration_analysis_module import CointegrationAnalysisModule
        
        # Map strategy types to strategy classes
        strategy_map = {
            'price_based': PromptStrategy,
            'spread_based': CointegrationAnalysisModule,
        }
        
        if strategy_type not in strategy_map:
            raise ValueError(
                f"Unknown strategy type: {strategy_type}. "
                f"Available: {list(strategy_map.keys())}"
            )
        
        strategy_class = strategy_map[strategy_type]
        schema = strategy_class.get_required_settings()
        
        return schema
    
    except Exception as e:
        logging.error(f"Error getting strategy settings schema: {e}")
        raise


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(json.dumps({'error': 'Strategy type is required'}))
        sys.exit(1)
    
    strategy_type = sys.argv[1]
    
    try:
        schema = get_strategy_settings_schema(strategy_type)
        print(json.dumps(schema))
    except Exception as e:
        print(json.dumps({'error': str(e)}))
        sys.exit(1)

