"""
Dynamic prompt registry that introspects analyzer_prompt.py to discover available prompts.
This eliminates hardcoded registries and ensures the API always reflects the actual prompts.
"""

import inspect
import importlib
import json
from typing import Dict, List, Callable, Any, Optional


def get_available_prompts() -> List[Dict[str, Any]]:
    """
    Dynamically discover all prompt functions from analyzer_prompt.py.
    
    A valid prompt function:
    - Takes 'market_data: dict' as first parameter
    - Has name starting with 'get_analyzer_prompt_' or known prompt names
    - Is not a helper function (like get_market_data)
    
    Returns:
        List of dicts with: name, description (from docstring)
    """
    # Import the module fresh (allows hot-reload)
    import trading_bot.core.prompts.analyzer_prompt as prompt_module
    importlib.reload(prompt_module)
    
    prompts = []
    
    # Known prompt function patterns
    valid_prefixes = ('get_analyzer_prompt_', 'code_nova')
    helper_functions = {'get_market_data'}
    
    for name, obj in inspect.getmembers(prompt_module, inspect.isfunction):
        # Skip helper functions
        if name in helper_functions:
            continue
            
        # Check if it matches our prompt function pattern
        if not any(name.startswith(prefix) for prefix in valid_prefixes):
            continue
        
        # Check signature - must accept market_data as first param
        sig = inspect.signature(obj)
        params = list(sig.parameters.keys())
        if not params or params[0] != 'market_data':
            continue
        
        # Extract description from docstring
        docstring = inspect.getdoc(obj) or ''
        # Get first line of docstring as description
        description = docstring.split('\n')[0].strip() if docstring else ''
        
        prompts.append({
            'name': name,
            'description': description
        })
    
    # Sort by name for consistent ordering
    prompts.sort(key=lambda x: x['name'])
    
    return prompts


def get_prompt_function(name: Optional[str]) -> Callable:
    """
    Get a prompt function by name.

    Args:
        name: The function name (e.g., 'get_analyzer_prompt_trade_playbook_v1')
              REQUIRED - no default, raises error if not provided.

    Returns:
        The prompt function callable

    Raises:
        ValueError: If name is None or empty
        ValueError: If function not found
    """
    import trading_bot.core.prompts.analyzer_prompt as prompt_module

    if not name:
        raise ValueError("prompt_name is required - no default prompt. Configure prompt in instance settings.")

    # Try to get the function
    func = getattr(prompt_module, name, None)

    if func is None or not callable(func):
        raise ValueError(f"Prompt function '{name}' not found in analyzer_prompt.py")

    return func


# CLI support for calling from Next.js API
if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'list':
        prompts = get_available_prompts()
        print(json.dumps(prompts))
    else:
        print(json.dumps({'error': 'Usage: python prompt_registry.py list'}))

