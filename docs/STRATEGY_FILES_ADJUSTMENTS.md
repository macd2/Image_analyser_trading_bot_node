# Strategy Files - Exact Adjustments Needed

## 1. `python/trading_bot/strategies/base.py`

**ADD** a heartbeat callback parameter to `__init__`:

```python
def __init__(
    self,
    config: 'Config',
    instance_id: Optional[str] = None,
    run_id: Optional[str] = None,
    strategy_config: Optional[Dict[str, Any]] = None,
    heartbeat_callback: Optional[Callable] = None,  # ADD THIS
):
    """..."""
    self.config = config
    self.instance_id = instance_id
    self.run_id = run_id
    self.heartbeat_callback = heartbeat_callback  # ADD THIS
    self.logger = logging.getLogger(self.__class__.__name__)
    # ... rest of init
```

**ADD** a helper method to call heartbeat:

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

## 2. `python/trading_bot/strategies/factory.py`

**MODIFY** the `create()` method to pass heartbeat_callback:

```python
@classmethod
def create(
    cls,
    instance_id: str,
    config: 'Config',
    run_id: Optional[str] = None,
    heartbeat_callback: Optional[Callable] = None,  # ADD THIS
    **kwargs
) -> 'BaseAnalysisModule':
    """..."""
    # ... existing code ...
    
    # Pass heartbeat_callback to strategy constructor
    return strategy_class(
        config=config,
        instance_id=instance_id,
        run_id=run_id,
        strategy_config=strategy_config,
        heartbeat_callback=heartbeat_callback,  # ADD THIS
        **kwargs
    )
```

---

## 3. `python/trading_bot/strategies/alex_analysis_module.py`

**MODIFY** `__init__` to accept heartbeat_callback:

```python
def __init__(
    self,
    config: 'Config',
    instance_id: Optional[str] = None,
    run_id: Optional[str] = None,
    strategy_config: Optional[Dict[str, Any]] = None,
    heartbeat_callback: Optional[Callable] = None,  # ADD THIS
):
    """Initialize Alex strategy with instance-specific config."""
    super().__init__(config, instance_id, run_id, strategy_config, heartbeat_callback)  # PASS IT
    global logger
    logger = self.logger
```

**ADD** heartbeat calls in `run_analysis_cycle()`:

```python
async def run_analysis_cycle(self, symbols, timeframe, cycle_id):
    results = []
    
    self._heartbeat(f"Starting analysis for {len(symbols)} symbols")  # ADD
    
    configured_timeframes = self.get_config_value('timeframes', ['1h', '4h', '1d'])
    
    for symbol in symbols:
        try:
            self._heartbeat(f"Analyzing {symbol}")  # ADD
            
            # ... existing analysis code ...
            
            self._heartbeat(f"Completed {symbol}")  # ADD
            
        except Exception as e:
            self.logger.error(...)
            self._heartbeat(f"Error analyzing {symbol}: {e}")  # ADD
    
    self._heartbeat("Analysis cycle complete")  # ADD
    return results
```

---

## 4. `python/trading_bot/strategies/__init__.py`

**NO CHANGES NEEDED** - Factory already handles registration

---

## 5. `python/trading_bot/engine/trading_cycle.py`

**MODIFY** where strategy is created (in `__init__`):

```python
# OLD:
self.analyzer = ChartAnalyzer(...)

# NEW:
self.strategy = StrategyFactory.create(
    instance_id=self.instance_id,
    config=self.config,
    run_id=self.run_id,
    heartbeat_callback=self.heartbeat_callback  # PASS IT
)
```

**MODIFY** where analysis is called (in `_analyze_all_charts_parallel`):

```python
# OLD:
analysis = await loop.run_in_executor(
    None,
    lambda: self.analyzer.analyze_chart(...)
)

# NEW:
results = await self.strategy.run_analysis_cycle(
    symbols=list(chart_paths.keys()),
    timeframe=self.timeframe,
    cycle_id=cycle_id
)
```

---

## 6. Create `python/trading_bot/strategies/cointegration_analysis_module.py`

**NEW FILE** - Cointegration strategy:

```python
from typing import Dict, Any, List, Optional, Callable
import pandas as pd
from trading_bot.strategies.base import BaseAnalysisModule
from trading_bot.strategies.spread_trading_cointegrated_plot import CointegrationStrategy

class CointegrationAnalysisModule(BaseAnalysisModule):
    """Cointegration-based spread trading strategy."""

    # Strategy-specific configuration (ready to move to instances.settings.strategy_config)
    # Later: This will be read from instances.settings.strategy_config in database
    STRATEGY_CONFIG = {
        # Analysis timeframe (NOT the cycle timeframe)
        "analysis_timeframe": "1h",

        # Pair mappings: symbol -> pair_symbol
        "pairs": {
            "RNDR": "AKT",
            "BTC": "ETH",
            "SOL": "AVAX",
        },

        # Cointegration parameters (strategy-specific)
        "lookback": 120,           # Lookback period for cointegration analysis
        "z_entry": 2.0,            # Z-score entry threshold for cointegration
        "z_exit": 0.5,             # Z-score exit threshold for cointegration
        "use_soft_vol": False,      # Use soft volatility adjustment for cointegration
    }

    DEFAULT_CONFIG = STRATEGY_CONFIG  # Use STRATEGY_CONFIG as default

    # Note: Price levels (entry, SL, TP) are calculated from the cointegration signal
    # Confidence is calculated from z-score
    # These are returned in the output, not configured here
    
    def __init__(
        self,
        config: 'Config',
        instance_id: Optional[str] = None,
        run_id: Optional[str] = None,
        strategy_config: Optional[Dict[str, Any]] = None,
        heartbeat_callback: Optional[Callable] = None,
    ):
        """Initialize cointegration strategy."""
        super().__init__(config, instance_id, run_id, strategy_config, heartbeat_callback)
    
    async def run_analysis_cycle(
        self,
        symbols: List[str],
        timeframe: str,
        cycle_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Analyze symbols using cointegration strategy.

        Each strategy is INDEPENDENT:
        - Gets symbols from config (NOT from watchlist)
        - Fetches candles (NOT chart images)
        - Runs cointegration analysis
        - Returns same output format

        Note: timeframe parameter is ignored - uses analysis_timeframe from config
        """
        results = []

        # Get configuration (will be read from instance settings later)
        pairs = self.get_config_value('pairs', {})
        analysis_timeframe = self.get_config_value('analysis_timeframe', '1h')

        self._heartbeat(f"Starting cointegration analysis for {len(symbols)} symbols (timeframe: {analysis_timeframe})")

        for symbol in symbols:
            try:
                self._heartbeat(f"Analyzing {symbol}")

                # Get pair symbol from config
                pair_symbol = pairs.get(symbol)
                if not pair_symbol:
                    self._heartbeat(f"No pair configured for {symbol}")
                    results.append({
                        "symbol": symbol,
                        "recommendation": "HOLD",
                        "confidence": 0.0,
                        "entry_price": None,
                        "stop_loss": None,
                        "take_profit": None,
                        "risk_reward": 0,
                        "setup_quality": 0.0,
                        "market_environment": 0.5,
                        "analysis": {"error": f"No pair configured for {symbol}"},
                        "chart_path": "",
                        "timeframe": analysis_timeframe,
                        "cycle_id": cycle_id,
                        "skipped": True,
                        "skip_reason": "No pair configured",
                    })
                    continue

                # Fetch candles for both symbols using analysis_timeframe from config
                self._heartbeat(f"Fetching candles for {symbol} and {pair_symbol}")
                candles1 = await self.candle_adapter.get_candles(symbol, analysis_timeframe)
                candles2 = await self.candle_adapter.get_candles(pair_symbol, analysis_timeframe)
                
                if not candles1 or not candles2:
                    self._heartbeat(f"Failed to fetch candles for {symbol}/{pair_symbol}")
                    results.append({
                        "symbol": symbol,
                        "recommendation": "HOLD",
                        "confidence": 0.0,
                        "entry_price": None,
                        "stop_loss": None,
                        "take_profit": None,
                        "risk_reward": 0,
                        "setup_quality": 0.0,
                        "market_environment": 0.5,
                        "analysis": {"error": "Failed to fetch candles"},
                        "chart_path": "",
                        "timeframe": timeframe,
                        "cycle_id": cycle_id,
                        "skipped": True,
                        "skip_reason": "Insufficient candle data",
                    })
                    continue
                
                # Merge candles into DataFrame
                df = pd.DataFrame({
                    'timestamp': candles1['timestamp'],
                    'close_1': candles1['close'],
                    'close_2': candles2['close']
                })
                
                # Run cointegration strategy with config values
                self._heartbeat(f"Running cointegration analysis for {symbol}")
                strategy = CointegrationStrategy(
                    lookback=self.get_config_value('lookback', 120),
                    z_entry=self.get_config_value('z_entry', 2.0),
                    z_exit=self.get_config_value('z_exit', 0.5),
                    use_soft_vol=self.get_config_value('use_soft_vol', False)
                )

                signals = strategy.generate_signals(df)
                latest_signal = signals.iloc[-1]

                # Convert to analyzer format with config values
                recommendation = self._convert_signal_to_recommendation(
                    symbol=symbol,
                    signal=latest_signal,
                    candles=candles1,
                    cycle_id=cycle_id,
                    analysis_timeframe=analysis_timeframe
                )
                
                self._validate_output(recommendation)
                results.append(recommendation)
                self._heartbeat(f"Completed {symbol}: {recommendation['recommendation']}")
                
            except Exception as e:
                self.logger.error(f"Error analyzing {symbol}: {e}")
                self._heartbeat(f"Error analyzing {symbol}: {e}")
                results.append({
                    "symbol": symbol,
                    "error": str(e),
                    "timeframe": timeframe,
                    "cycle_id": cycle_id,
                })
        
        self._heartbeat("Cointegration analysis cycle complete")
        return results
    
    def _convert_signal_to_recommendation(
        self,
        symbol: str,
        signal: pd.Series,
        candles: Dict[str, Any],
        cycle_id: str,
        analysis_timeframe: str,
    ) -> Dict[str, Any]:
        """Convert cointegration signal to analyzer format."""
        z_score = signal['z_score']
        signal_val = signal['signal']
        current_price = candles['close'].iloc[-1]

        # Map z-score to confidence (0-1 range)
        # Higher z-score = stronger signal = higher confidence
        confidence = min(0.95, 0.5 + abs(z_score) * 0.15)

        # Map signal to recommendation
        if signal_val == 1:
            recommendation = "BUY"
        elif signal_val == -1:
            recommendation = "SELL"
        else:
            recommendation = "HOLD"

        # Calculate price levels from current price
        # These are just initial estimates - position sizer will adjust based on risk_percentage
        entry_price = current_price
        if recommendation == "BUY":
            stop_loss = current_price * 0.98  # 2% below entry
            take_profit = current_price * 1.04  # 4% above entry
        elif recommendation == "SELL":
            stop_loss = current_price * 1.02  # 2% above entry
            take_profit = current_price * 0.96  # 4% below entry
        else:
            stop_loss = None
            take_profit = None

        # Calculate risk-reward
        if stop_loss and take_profit:
            risk = abs(entry_price - stop_loss)
            reward = abs(take_profit - entry_price)
            risk_reward = reward / risk if risk > 0 else 0
        else:
            risk_reward = 0

        return {
            "symbol": symbol,
            "recommendation": recommendation,
            "confidence": confidence,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "risk_reward": risk_reward,
            "setup_quality": signal.get('size_multiplier', 0.5),
            "market_environment": 0.5,
            "analysis": {
                "strategy": "cointegration",
                "z_score": float(z_score),
                "is_mean_reverting": bool(signal.get('is_mean_reverting', False)),
                "size_multiplier": float(signal.get('size_multiplier', 1.0)),
            },
            "chart_path": "",
            "timeframe": analysis_timeframe,
            "cycle_id": cycle_id,
        }
```

---

## Summary of Changes

| File | Change | Type |
|------|--------|------|
| `base.py` | Add heartbeat_callback param + _heartbeat() method | MODIFY |
| `factory.py` | Pass heartbeat_callback to strategy | MODIFY |
| `alex_analysis_module.py` | Accept heartbeat_callback + add _heartbeat() calls | MODIFY |
| `cointegration_analysis_module.py` | NEW FILE | CREATE |
| `trading_cycle.py` | Pass heartbeat_callback when creating strategy | MODIFY |

**Key Points:**
- Each strategy is COMPLETELY INDEPENDENT
- Both strategies return SAME output format
- Heartbeat is handled by each strategy
- Pair config is simple dict (can move to settings later)
- No changes to downstream code (ranking, execution, etc.)

