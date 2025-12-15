# Exact Code Changes - Copy/Paste Ready

## File 1: `python/trading_bot/strategies/base.py`

**CHANGE 1** - Add import at top:
```python
from typing import Dict, Any, List, Optional, Callable  # ADD Callable
```

**CHANGE 2** - Modify `__init__` signature (line 33-39):
```python
def __init__(
    self,
    config: 'Config',
    instance_id: Optional[str] = None,
    run_id: Optional[str] = None,
    strategy_config: Optional[Dict[str, Any]] = None,
    heartbeat_callback: Optional[Callable] = None,  # ADD THIS LINE
):
```

**CHANGE 3** - Add to `__init__` body (after line 52):
```python
    self.logger = logging.getLogger(self.__class__.__name__)
    self.heartbeat_callback = heartbeat_callback  # ADD THIS LINE
    
    # Load strategy config from database or use provided config
```

**CHANGE 4** - Add new method after `get_config_value()` (after line 119):
```python
    def _heartbeat(self, message: str = "") -> None:
        """Call heartbeat callback if available."""
        if self.heartbeat_callback:
            try:
                self.heartbeat_callback(message)
            except Exception as e:
                self.logger.warning(f"Heartbeat callback failed: {e}")
```

---

## File 2: `python/trading_bot/strategies/factory.py`

**CHANGE 1** - Add import at top:
```python
from typing import Optional, Type, Dict, Any, Callable  # ADD Callable
```

**CHANGE 2** - Modify `create()` signature (line 39-45):
```python
    @classmethod
    def create(
        cls,
        instance_id: str,
        config: 'Config',
        run_id: Optional[str] = None,
        heartbeat_callback: Optional[Callable] = None,  # ADD THIS LINE
        **kwargs
    ) -> 'BaseAnalysisModule':
```

**CHANGE 3** - Modify return statement (line 101-107):
```python
        # Pass strategy_config to strategy constructor
        return strategy_class(
            config=config,
            instance_id=instance_id,
            run_id=run_id,
            strategy_config=strategy_config,
            heartbeat_callback=heartbeat_callback,  # ADD THIS LINE
            **kwargs
        )
```

---

## File 3: `python/trading_bot/strategies/alex_analysis_module.py`

**CHANGE 1** - Add import at top:
```python
from typing import Dict, Any, List, Optional, Callable  # ADD Callable
```

**CHANGE 2** - Modify `__init__` signature (line 33-39):
```python
    def __init__(
        self,
        config: 'Config',
        instance_id: Optional[str] = None,
        run_id: Optional[str] = None,
        strategy_config: Optional[Dict[str, Any]] = None,
        heartbeat_callback: Optional[Callable] = None,  # ADD THIS LINE
    ):
        """Initialize Alex strategy with instance-specific config."""
        super().__init__(config, instance_id, run_id, strategy_config, heartbeat_callback)  # PASS IT
        global logger
        logger = self.logger
```

**CHANGE 3** - Add heartbeat calls in `run_analysis_cycle()`:
- After line 62 (after `results = []`):
```python
        self._heartbeat(f"Starting analysis for {len(symbols)} symbols")
```

- After line 67 (inside for loop, after `for symbol in symbols:`):
```python
            self._heartbeat(f"Analyzing {symbol}")
```

- After line 145 (after `results.append(result)`):
```python
            self._heartbeat(f"Completed {symbol}")
```

- After line 159 (in except block, after `results.append(...)`):
```python
            self._heartbeat(f"Error analyzing {symbol}: {e}")
```

- After line 161 (before `return results`):
```python
        self._heartbeat("Analysis cycle complete")
```

---

## File 4: `python/trading_bot/engine/trading_cycle.py`

**CHANGE 1** - Find where `self.analyzer` is created (around line 108-112):

OLD:
```python
        self.analyzer = ChartAnalyzer(
            openai_client=OpenAI(api_key=self.config.openai.api_key),
            config=self.config,
            api_manager=BybitAPIManager(self.config),
        )
```

NEW:
```python
        # Create strategy using factory (loads from database)
        from trading_bot.strategies.factory import StrategyFactory
        self.strategy = StrategyFactory.create(
            instance_id=self.instance_id,
            config=self.config,
            run_id=self.run_id,
            heartbeat_callback=self.heartbeat_callback
        )
```

**CHANGE 2** - Find `_analyze_all_charts_parallel()` method (around line 730-766):

Replace entire method with:
```python
    async def _analyze_all_charts_parallel(
        self, chart_paths: Dict[str, str], cycle_id: str
    ) -> List[Dict[str, Any]]:
        """
        Analyze symbols using strategy (chart-based or candle-based).
        
        Strategy is loaded from database and handles analysis independently.
        """
        # Get symbols from chart_paths keys
        symbols = list(chart_paths.keys())
        
        # Run strategy analysis cycle
        results = await self.strategy.run_analysis_cycle(
            symbols=symbols,
            timeframe=self.timeframe,
            cycle_id=cycle_id
        )
        
        # Enrich results with chart_path if available
        for result in results:
            if result.get('symbol') in chart_paths:
                result['chart_path'] = chart_paths[result['symbol']]
        
        return results
```

**CHANGE 3** - Remove old `_analyze_chart_async()` method (lines 768-820) - NO LONGER NEEDED

---

## File 5: Create `python/trading_bot/strategies/cointegration_analysis_module.py`

**NEW FILE** - Copy entire content from STRATEGY_FILES_ADJUSTMENTS.md section 6

**Key points:**
- **ONLY strategy-specific config** in `STRATEGY_CONFIG` dict (NOT general trading settings)
- Uses `self.get_config_value()` to read config (automatically reads from database when available)
- Price levels (entry, SL, TP) are calculated from the signal, not configured
- Confidence is calculated from z-score, not configured
- General trading settings come from main TradingConfig, not here
- See COINTEGRATION_CONFIG_STRUCTURE.md for config details

---

## File 6: `python/trading_bot/strategies/__init__.py`

**ADD** import and registration (after line 14):
```python
from trading_bot.strategies.cointegration_analysis_module import CointegrationAnalysisModule

# Register strategies
StrategyFactory.register_strategy("cointegration", CointegrationAnalysisModule)
```

**MODIFY** `__all__` (line 16-21):
```python
__all__ = [
    "BaseAnalysisModule",
    "CandleAdapter",
    "StrategyFactory",
    "AlexAnalysisModule",
    "CointegrationAnalysisModule",  # ADD THIS
]
```

---

## Order of Implementation

1. **base.py** - Add heartbeat support (foundation)
2. **factory.py** - Pass heartbeat to strategies
3. **alex_analysis_module.py** - Add heartbeat calls
4. **cointegration_analysis_module.py** - Create new strategy
5. **__init__.py** - Register cointegration strategy
6. **trading_cycle.py** - Use strategy factory instead of hardcoded analyzer

---

## Testing After Changes

```python
# Test cointegration strategy
from trading_bot.strategies.factory import StrategyFactory

strategy = StrategyFactory.create(
    instance_id="test_instance",
    config=config,
    heartbeat_callback=lambda msg: print(f"[HB] {msg}")
)

results = await strategy.run_analysis_cycle(
    symbols=["RNDR"],
    timeframe="1h",
    cycle_id="test_cycle"
)

print(results)
# Should print: [{symbol, recommendation, confidence, entry_price, ...}]
```

