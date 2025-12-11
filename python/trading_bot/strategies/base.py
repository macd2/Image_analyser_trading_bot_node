"""
BaseAnalysisModule - Abstract base for all analysis strategies.

Enforces:
1. Output format contract (recommendation, confidence, prices, etc.)
2. Instance-aware logging and audit trail
3. Instance-specific configuration loading from database
4. Error handling and validation
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import logging
import json

logger = logging.getLogger(__name__)


class BaseAnalysisModule(ABC):
    """
    Abstract base for all analysis strategies.
    
    Strategies must:
    1. Return standardized output format
    2. Load instance-specific config from database
    3. Use CandleAdapter for candle data
    4. Validate output before returning
    """
    
    # Default strategy config (override in subclasses)
    DEFAULT_CONFIG = {}
    
    def __init__(
        self,
        config: 'Config',
        instance_id: Optional[str] = None,
        run_id: Optional[str] = None,
        strategy_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize analysis module.
        
        Args:
            config: Trading bot config
            instance_id: Instance ID (for database lookups)
            run_id: Run ID (for audit trail)
            strategy_config: Instance-specific strategy config
        """
        self.config = config
        self.instance_id = instance_id
        self.run_id = run_id
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Load strategy config from database or use provided config
        self.strategy_config = self._load_strategy_config(strategy_config)
        
        # Initialize candle adapter
        self._init_candle_adapter()
    
    def _load_strategy_config(
        self,
        provided_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Load strategy config from database or use provided config.
        
        Priority:
        1. Provided config (from parameter)
        2. Database config (from instances.settings)
        3. Default config (class-level defaults)
        """
        if provided_config:
            return {**self.DEFAULT_CONFIG, **provided_config}
        
        # Load from database if instance_id provided
        if self.instance_id:
            try:
                from trading_bot.db.client import get_connection, release_connection, query_one
                
                conn = get_connection()
                try:
                    instance = query_one(
                        conn,
                        "SELECT settings FROM instances WHERE id = ?",
                        (self.instance_id,)
                    )
                    
                    if instance and instance.get('settings'):
                        settings = json.loads(instance['settings'])
                        strategy_config = settings.get('strategy_config', {})
                        
                        self.logger.info(
                            f"Loaded strategy config from database for instance {self.instance_id}",
                            extra={"instance_id": self.instance_id}
                        )
                        
                        return {**self.DEFAULT_CONFIG, **strategy_config}
                finally:
                    release_connection(conn)
            except Exception as e:
                self.logger.warning(
                    f"Failed to load strategy config from database: {e}. Using defaults.",
                    extra={"instance_id": self.instance_id}
                )
        
        return self.DEFAULT_CONFIG.copy()
    
    def _init_candle_adapter(self) -> None:
        """Initialize candle adapter (override in subclasses if needed)."""
        try:
            from trading_bot.strategies.candle_adapter import CandleAdapter
            self.candle_adapter = CandleAdapter(instance_id=self.instance_id)
        except Exception as e:
            self.logger.warning(f"Failed to initialize candle adapter: {e}")
            self.candle_adapter = None
    
    def get_config_value(self, key: str, default: Any = None) -> Any:
        """Get a config value from strategy_config."""
        return self.strategy_config.get(key, default)
    
    @abstractmethod
    async def run_analysis_cycle(
        self,
        symbols: List[str],
        timeframe: str,
        cycle_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Analyze symbols and return recommendations.
        
        Must return list of dicts matching OUTPUT_FORMAT.
        """
        raise NotImplementedError
    
    def _validate_output(self, result: Dict[str, Any]) -> None:
        """Validate that result matches output format contract."""
        required_fields = {
            "symbol": str,
            "recommendation": str,
            "confidence": (int, float),
            "entry_price": (int, float, type(None)),
            "stop_loss": (int, float, type(None)),
            "take_profit": (int, float, type(None)),
            "risk_reward": (int, float),
            "setup_quality": (int, float),
            "market_environment": (int, float),
            "analysis": dict,
            "chart_path": str,
            "timeframe": str,
            "cycle_id": str,
        }
        
        for field, expected_type in required_fields.items():
            if field not in result:
                raise ValueError(f"Missing required field: {field}")
            
            if not isinstance(result[field], expected_type):
                raise ValueError(
                    f"Field '{field}' has wrong type. "
                    f"Expected {expected_type}, got {type(result[field])}"
                )
        
        # Validate recommendation
        if result["recommendation"].upper() not in ("BUY", "SELL", "HOLD"):
            raise ValueError(
                f"Invalid recommendation: {result['recommendation']}. "
                f"Must be BUY, SELL, or HOLD"
            )
        
        # Validate confidence
        if not (0 <= result["confidence"] <= 1):
            raise ValueError(
                f"Confidence must be 0-1, got {result['confidence']}"
            )

