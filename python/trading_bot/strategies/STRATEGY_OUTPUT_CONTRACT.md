# Strategy Output Contract

## Overview
Each strategy returns a list of recommendation dicts. TradingCycle's `_record_recommendation()` method stores these in the database.

## Required Fields for Database Storage

### From `result` dict (first parameter to `_record_recommendation()`)
```python
result = {
    "symbol": str,              # e.g., "BTCUSDT"
    "recommendation": str,      # "BUY", "SELL", or "HOLD" (will be normalized to LONG/SHORT/HOLD)
    "confidence": float,        # 0.0-1.0
    "timeframe": str,          # e.g., "1h", "4h"
    "cycle_id": str,           # Cycle identifier
    "chart_path": str,         # Path to chart image (can be empty for non-chart strategies)
    "from_existing": bool,     # Optional: if True, uses existing recommendation_id
    "recommendation_id": str,  # Optional: existing recommendation ID if from_existing=True
}
```

### From `analysis` dict (second parameter to `_record_recommendation()`)
```python
analysis = {
    # Price levels
    "entry_price": float | None,
    "stop_loss": float | None,
    "take_profit": float | None,
    "risk_reward_ratio": float | None,  # or "risk_reward"
    
    # Analysis metadata
    "summary": str,                      # Text summary of analysis
    "raw_response": str,                 # Full AI response text
    "analysis_prompt": str,              # The exact prompt used
    "market_data_snapshot": dict,        # Market data fed to AI
    "validation": dict,                  # Validation info
    "timestamp": str,                    # ISO timestamp
    "normalized_timeframe": str,         # Normalized timeframe
    
    # Prompt/Model info
    "prompt_id": str,                    # Prompt identifier
    "prompt_version": str,               # Prompt version
    "assistant_model": str,              # Model name (e.g., "gpt-4-vision")
    
    # Optional
    "llm_original_recommendation": str,  # Original before correction
}
```

## BaseAnalysisModule Output Format (Validation)

All strategies must return this format from `run_analysis_cycle()`:

```python
{
    "symbol": str,
    "recommendation": str,              # "BUY", "SELL", "HOLD"
    "confidence": float,                # 0.0-1.0
    "entry_price": float | None,
    "stop_loss": float | None,
    "take_profit": float | None,
    "risk_reward": float,               # 0.0+
    "setup_quality": float,             # 0.0-1.0
    "market_environment": float,        # 0.0-1.0
    "analysis": dict,                   # Full analysis data
    "chart_path": str,                  # Path or empty string
    "timeframe": str,                   # e.g., "1h"
    "cycle_id": str,                    # Cycle ID
}
```

## Storage Flow

1. Strategy returns list of dicts matching BaseAnalysisModule format
2. TradingCycle calls `_record_recommendation(result, analysis)` for each
3. `_record_recommendation()` extracts fields and inserts into database

## Key Points

- **Strategies don't store** - TradingCycle handles all database operations
- **Analysis dict is separate** - Contains detailed metadata for audit trail
- **Prompt info required** - prompt_id, prompt_version, assistant_model for reproducibility
- **Market data snapshot** - Stored for replay/audit purposes
- **Raw response** - Full AI response stored as JSON for reproducibility

