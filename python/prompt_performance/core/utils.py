"""
Utility functions for prompt performance analysis.
"""

import hashlib
import re
from typing import Dict


def normalize_prompt_for_hashing(prompt_text: str) -> str:
    """
    Normalize prompt text by removing dynamic market data sections.

    Args:
        prompt_text: The raw prompt text

    Returns:
        Normalized prompt text with dynamic data removed
    """
    if not prompt_text or not prompt_text.strip():
        return ""

    # Remove specific market data sections
    prompt_text = re.sub(r'### MARKET DATA.*?(?=\n\n|\n#|\n-|\Z)', '', prompt_text, flags=re.DOTALL | re.IGNORECASE)
    prompt_text = re.sub(r'## CURRENT MARKET DATA.*?(?=\n\n|\n#|\n-|\Z)', '', prompt_text, flags=re.DOTALL | re.IGNORECASE)


    # Remove specific dynamic data lines (only the line containing the data)
    prompt_text = re.sub(r'^.*Current market price.*:.*$', '', prompt_text, flags=re.MULTILINE | re.IGNORECASE)
    prompt_text = re.sub(r'^.*"last_close_price":.*$', '', prompt_text, flags=re.MULTILINE | re.IGNORECASE)
    prompt_text = re.sub(r'^.*Best Bid:.*$', '', prompt_text, flags=re.MULTILINE | re.IGNORECASE)
    prompt_text = re.sub(r'^.*Best Ask:.*$', '', prompt_text, flags=re.MULTILINE | re.IGNORECASE)
    prompt_text = re.sub(r'^.*Latest Funding Rate:.*$', '', prompt_text, flags=re.MULTILINE | re.IGNORECASE)
    prompt_text = re.sub(r'^.*Long/Short Ratio:.*$', '', prompt_text, flags=re.MULTILINE | re.IGNORECASE)
    prompt_text = re.sub(r'^.*Timeframe:.*$', '', prompt_text, flags=re.MULTILINE | re.IGNORECASE)
    prompt_text = re.sub(r'^.*Symbol:.*$', '', prompt_text, flags=re.MULTILINE | re.IGNORECASE)
    prompt_text = re.sub(r'^.*"timeframe":.*$', '', prompt_text, flags=re.MULTILINE | re.IGNORECASE)
    prompt_text = re.sub(r'^.*"symbol":.*$', '', prompt_text, flags=re.MULTILINE | re.IGNORECASE)
    prompt_text = re.sub(r'^.*Last close price:.*$', '', prompt_text, flags=re.MULTILINE | re.IGNORECASE)

    # Clean up extra whitespace and newlines
    prompt_text = re.sub(r'\n\s*\n', '\n', prompt_text)  # Remove extra blank lines
    prompt_text = prompt_text.strip()

    return prompt_text


def extract_prompt_metadata(prompt_text: str) -> Dict[str, str]:
    """
    Extract metadata from prompt text for analysis purposes.

    Args:
        prompt_text: The raw prompt text

    Returns:
        Dictionary containing extracted metadata (timeframe, symbol, market_price, etc.)
    """
    metadata = {}

    if not prompt_text or not prompt_text.strip():
        return metadata

    # Extract timeframe
    timeframe_match = re.search(r'"timeframe":\s*"([^"]+)"', prompt_text, re.IGNORECASE)
    if timeframe_match:
        metadata['timeframe'] = timeframe_match.group(1)
    else:
        # Try alternative format
        timeframe_match = re.search(r'Timeframe:\s*"([^"]+)"', prompt_text, re.IGNORECASE)
        if timeframe_match:
            metadata['timeframe'] = timeframe_match.group(1)

    # Extract symbol
    symbol_match = re.search(r'"symbol":\s*"([^"]+)"', prompt_text, re.IGNORECASE)
    if symbol_match:
        metadata['symbol'] = symbol_match.group(1)
    else:
        # Try alternative format
        symbol_match = re.search(r'Symbol:\s*"([^"]+)"', prompt_text, re.IGNORECASE)
        if symbol_match:
            metadata['symbol'] = symbol_match.group(1)

    return metadata


def generate_prompt_hash(prompt_text: str) -> str:
    """
    Generate a 5-character MD5 hash for prompt grouping.
    Normalizes the prompt first to remove dynamic market data.

    Args:
        prompt_text: The prompt text to hash

    Returns:
        5-character hash string, or 'empty' for empty/null prompts
    """
    if not prompt_text or not prompt_text.strip():
        return "empty"

    # Normalize the prompt to remove dynamic data
    normalized_prompt = normalize_prompt_for_hashing(prompt_text)

    if not normalized_prompt:
        return "empty"

    # Generate MD5 hash and take first 5 characters
    hash_obj = hashlib.md5(normalized_prompt.encode())
    return hash_obj.hexdigest()[:5]