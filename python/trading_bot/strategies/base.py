"""
BaseAnalysisModule - Abstract base for all analysis strategies.

Enforces:
1. Output format contract (recommendation, confidence, prices, etc.)
2. Instance-aware logging and audit trail
3. Instance-specific configuration loading from database
4. Error handling and validation
"""

from abc import ABC, abstractmethod, abstractproperty
from typing import Dict, Any, List, Optional, Callable
import logging
import json
import hashlib
import uuid

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

    # Strategy type - must be overridden in subclasses
    STRATEGY_TYPE: str = None  # 'price_based' or 'spread_based'
    STRATEGY_NAME: str = None  # e.g., 'PromptStrategy', 'CointegrationAnalysisModule'
    STRATEGY_VERSION: str = "1.0"  # Version for reproducibility

    def __init__(
        self,
        config: 'Config',
        instance_id: Optional[str] = None,
        run_id: Optional[str] = None,
        strategy_config: Optional[Dict[str, Any]] = None,
        heartbeat_callback: Optional[Callable] = None,
    ):
        """
        Initialize analysis module.

        Args:
            config: Trading bot config
            instance_id: Instance ID (for database lookups)
            run_id: Run ID (for audit trail)
            strategy_config: Instance-specific strategy config
            heartbeat_callback: Optional callback for UI updates during analysis
        """
        self.config = config
        self.instance_id = instance_id
        self.run_id = run_id
        self.heartbeat_callback = heartbeat_callback
        self.logger = logging.getLogger(self.__class__.__name__)

        # Load strategy config from database or use provided config
        self.strategy_config = self._load_strategy_config(strategy_config)

        # Generate deterministic strategy UUID for reproducibility
        self.strategy_uuid = self._generate_strategy_uuid()

        # Initialize candle adapter
        self._init_candle_adapter()
    
    def _convert_setting_type(self, key: str, value: Any) -> Any:
        """
        Convert setting value to appropriate type based on setting name.

        Handles conversion of string values from database to proper types:
        - Numeric settings (lookback, batch_size, etc.) → int/float
        - Boolean settings (use_soft_vol, etc.) → bool
        - String settings → str

        Args:
            key: Setting name
            value: Setting value (often a string from database)

        Returns:
            Converted value with appropriate type
        """
        if value is None:
            return value

        # If already the right type, return as-is
        if isinstance(value, (int, float, bool, dict, list)):
            return value

        # Convert string values
        if isinstance(value, str):
            # Boolean settings
            if key in ('use_soft_vol', 'enable_spread_monitoring', 'use_adf', 'enable_dynamic_sizing'):
                return value.lower() in ('true', '1', 'yes')

            # Numeric settings - try to convert to int first, then float
            if key in (
                'lookback', 'batch_size', 'screener_cache_hours',
                'min_volume_usd', 'z_entry', 'z_exit', 'max_spread_deviation',
                'lookback_period', 'min_z_distance', 'z_score_entry_threshold',
                'z_score_exit_threshold', 'spread_reversion_threshold', 'candle_limit',
                'min_sl_buffer'
            ):
                try:
                    # Try int first
                    if '.' not in value:
                        return int(value)
                    else:
                        return float(value)
                except (ValueError, TypeError):
                    self.logger.warning(
                        f"Could not convert setting '{key}' with value '{value}' to numeric type",
                        extra={"instance_id": self.instance_id}
                    )
                    return value

        return value

    def _flatten_strategy_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Flatten strategy-specific settings from prefixed keys.

        Converts keys like:
        - "strategy_specific.cointegration.pair_discovery_mode" → "pair_discovery_mode"
        - "strategy_specific.spread_based.lookback_period" → "lookback_period"

        Also keeps non-prefixed keys as-is and converts string values to appropriate types.

        Args:
            config: Raw config dict with potentially prefixed keys

        Returns:
            Flattened config dict with only relevant settings for this strategy
        """
        flattened = {}

        # Get the strategy type prefix (e.g., "cointegration" from "CointegrationSpreadTrader")
        # This is a heuristic - subclasses can override if needed
        strategy_type_prefix = self._get_strategy_type_prefix()

        for key, value in config.items():
            # Check if this is a strategy-specific setting
            if key.startswith('strategy_specific.'):
                # Extract the strategy type and setting name
                # Format: "strategy_specific.{strategy_type}.{setting_name}"
                parts = key.split('.')
                if len(parts) >= 3:
                    setting_strategy_type = parts[1]
                    setting_name = '.'.join(parts[2:])  # Handle nested keys like "z_score.entry"

                    # Only include settings for this strategy type
                    if setting_strategy_type == strategy_type_prefix:
                        # Convert to appropriate type
                        converted_value = self._convert_setting_type(setting_name, value)
                        flattened[setting_name] = converted_value
            else:
                # Keep non-prefixed keys but apply type conversion
                # This ensures values from database (which are strings) are converted to proper types
                converted_value = self._convert_setting_type(key, value)
                flattened[key] = converted_value

        return flattened

    def _get_strategy_type_prefix(self) -> str:
        """
        Get the strategy type prefix for filtering strategy-specific settings.

        Override in subclasses if the default heuristic doesn't work.
        Default: Extract from STRATEGY_NAME (e.g., "CointegrationAnalysisModule" → "cointegration")

        Returns:
            Strategy type prefix (e.g., "cointegration", "spread_based")
        """
        if self.STRATEGY_NAME:
            # Convert class name to lowercase prefix
            # "CointegrationAnalysisModule" → "cointegration"
            name = self.STRATEGY_NAME.lower()
            if 'cointegration' in name:
                return 'cointegration'
            elif 'spread' in name:
                return 'spread_based'
        return 'cointegration'  # Default fallback

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
            # Flatten strategy-specific settings from prefixed keys
            flattened_config = self._flatten_strategy_config(provided_config)
            self.logger.info(
                f"Using provided strategy config (keys: {list(flattened_config.keys())})",
                extra={"instance_id": self.instance_id}
            )
            return {**self.DEFAULT_CONFIG, **flattened_config}

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
                        settings_raw = instance['settings']
                        # Handle both string (SQLite) and dict (PostgreSQL JSONB) formats
                        if isinstance(settings_raw, str):
                            settings = json.loads(settings_raw)
                        else:
                            settings = settings_raw if isinstance(settings_raw, dict) else {}

                        strategy_config = settings.get('strategy_config', {})

                        # Apply type conversion to all config values from database
                        # Database stores all values as strings, so we need to convert them to proper types
                        converted_config = {}
                        for key, value in strategy_config.items():
                            converted_config[key] = self._convert_setting_type(key, value)

                        self.logger.info(
                            f"✅ Loaded strategy config from database for instance {self.instance_id}",
                            extra={"instance_id": self.instance_id, "config_keys": list(converted_config.keys())}
                        )

                        return {**self.DEFAULT_CONFIG, **converted_config}
                    else:
                        self.logger.warning(
                            f"⚠️  Instance not found or has no settings: {self.instance_id}. Using defaults.",
                            extra={"instance_id": self.instance_id}
                        )
                finally:
                    release_connection(conn)
            except Exception as e:
                self.logger.warning(
                    f"⚠️  Failed to load strategy config from database: {e}. Using defaults.",
                    extra={"instance_id": self.instance_id}
                )

        self.logger.info(
            f"Using default strategy config (keys: {list(self.DEFAULT_CONFIG.keys())})",
            extra={"instance_id": self.instance_id}
        )
        return self.DEFAULT_CONFIG.copy()
    
    def _generate_strategy_uuid(self) -> str:
        """
        Generate deterministic UUID from strategy type, name, version, and config hash.

        Same strategy + same config = same UUID (reproducible)
        Different config = different UUID (traceable)

        Returns:
            Deterministic UUID string
        """
        if not self.STRATEGY_TYPE or not self.STRATEGY_NAME:
            raise ValueError(
                f"Strategy must define STRATEGY_TYPE and STRATEGY_NAME. "
                f"Got STRATEGY_TYPE={self.STRATEGY_TYPE}, STRATEGY_NAME={self.STRATEGY_NAME}"
            )

        # Create config hash for reproducibility
        config_str = json.dumps(self.strategy_config, sort_keys=True, default=str)
        config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:16]

        # Combine strategy info for UUID
        uuid_input = f"{self.STRATEGY_TYPE}:{self.STRATEGY_NAME}:{self.STRATEGY_VERSION}:{config_hash}"

        # Generate deterministic UUID (namespace-based)
        strategy_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, uuid_input))

        self.logger.debug(
            f"Generated strategy UUID: {strategy_uuid} "
            f"(type={self.STRATEGY_TYPE}, name={self.STRATEGY_NAME}, config_hash={config_hash})"
        )

        return strategy_uuid

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
        value = self.strategy_config.get(key, default)
        if value != default:
            self.logger.debug(f"Config value '{key}': {value} (from strategy_config)")
        else:
            self.logger.debug(f"Config value '{key}': {value} (using default)")
        return value

    def _heartbeat(self, message: str = "", **kwargs) -> None:
        """
        Send heartbeat update to UI (if callback is registered).

        Args:
            message: Status message to send
            **kwargs: Additional data to send with heartbeat
        """
        if self.heartbeat_callback:
            try:
                self.heartbeat_callback(message=message, **kwargs)
            except Exception as e:
                self.logger.warning(f"Heartbeat callback failed: {e}")
    
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

    @abstractmethod
    def validate_signal(self, signal: Dict[str, Any]) -> bool:
        """
        Validate that a signal meets strategy-specific requirements.

        Args:
            signal: Signal dict with entry_price, stop_loss, take_profit, etc.

        Returns:
            True if signal is valid, False otherwise

        Raises:
            ValueError: If validation fails with details
        """
        raise NotImplementedError

    @abstractmethod
    def calculate_risk_metrics(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate strategy-specific risk metrics from a signal.

        Args:
            signal: Signal dict with entry_price, stop_loss, take_profit, etc.

        Returns:
            Dict with risk metrics (e.g., risk_per_unit, RR ratio for price-based,
            z-distance for spread-based)
        """
        raise NotImplementedError

    @abstractmethod
    def get_exit_condition(self) -> Dict[str, Any]:
        """
        Get strategy-specific exit condition metadata.

        Returns:
            Dict with exit condition parameters needed by simulator/position monitor

        Examples:
            Price-based: {"type": "price_level", "tp_price": 100.5, "sl_price": 99.5}
            Spread-based: {"type": "z_score", "z_exit": 0.5, "beta": 1.2, ...}
        """
        raise NotImplementedError

    @abstractmethod
    def get_monitoring_metadata(self) -> Dict[str, Any]:
        """
        Get strategy-specific monitoring metadata.

        Returns:
            Dict with monitoring parameters needed by position monitor

        Examples:
            Price-based: {"entry_price": 100, "sl": 99.5, "tp": 101.5, "rr_ratio": 2.0}
            Spread-based: {"beta": 1.2, "spread_mean": 0.5, "spread_std": 0.1, "z_exit": 0.5}
        """
        raise NotImplementedError

    @abstractmethod
    def should_exit(
        self,
        trade: Dict[str, Any],
        current_candle: Dict[str, Any],
        pair_candle: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Check if a trade should exit based on strategy-specific logic.

        Args:
            trade: Trade record with entry_price, stop_loss, take_profit, strategy_metadata
            current_candle: Current candle data {timestamp, open, high, low, close}
            pair_candle: Optional pair candle (for spread-based strategies)

        Returns:
            Dict with:
            - 'should_exit': bool - whether to exit the trade
            - 'exit_details': dict - detailed exit context for logging
              - 'reason': str - why exit was triggered (e.g., 'tp_touched', 'sl_touched', 'z_score_exit', 'no_exit')
              - Additional fields depend on strategy type (price, z_score, spread, etc.)

        Examples:
            Price-based: {
                'should_exit': True,
                'exit_details': {
                    'reason': 'tp_touched',
                    'price': 101.5,
                    'tp': 101.5,
                    'sl': 99.5,
                    'distance_to_tp': 0.0,
                    'distance_to_sl': 2.0
                }
            }
            Spread-based: {
                'should_exit': True,
                'exit_details': {
                    'reason': 'z_score_exit',
                    'z_score': 0.45,
                    'spread': 0.5,
                    'threshold': 0.5,
                    'threshold_crossed': True,
                    'beta': 1.2,
                    'spread_mean': 0.0,
                    'spread_std': 0.1,
                    'pair_symbol': 'ETHUSDT'
                }
            }
        """
        raise NotImplementedError

    def capture_reproducibility_data(
        self,
        analysis_result: Dict[str, Any],
        chart_path: Optional[str] = None,
        market_data: Optional[Dict[str, Any]] = None,
        model_version: Optional[str] = None,
        model_params: Optional[Dict[str, Any]] = None,
        prompt_version: Optional[str] = None,
        prompt_content: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Capture all reproducibility data for an analysis result.

        This method should be called after analysis to capture:
        - Input snapshots (chart hash, model version, market data, config)
        - Intermediate calculations (confidence components, setup quality, etc.)
        - Reproducibility metadata (model params, prompt version, etc.)

        Args:
            analysis_result: The analysis result dict from run_analysis_cycle()
            chart_path: Path to the chart image (for hashing)
            market_data: Market data snapshot used in analysis
            model_version: Version of the model used (e.g., 'gpt-4-vision')
            model_params: Model parameters (temperature, max_tokens, etc.)
            prompt_version: Version of the prompt used
            prompt_content: Full content of the prompt used

        Returns:
            Dict with reproducibility data to store in database
        """
        reproducibility_data = {}

        # Capture input snapshot
        if chart_path:
            try:
                with open(chart_path, 'rb') as f:
                    chart_hash = hashlib.md5(f.read()).hexdigest()
                reproducibility_data['chart_hash'] = chart_hash
            except Exception as e:
                self.logger.warning(f"Failed to hash chart: {e}")

        reproducibility_data['model_version'] = model_version or 'unknown'
        reproducibility_data['model_params'] = model_params or {}
        reproducibility_data['market_data_snapshot'] = market_data or {}
        reproducibility_data['strategy_config_snapshot'] = self.strategy_config

        # Capture intermediate calculations
        if 'confidence_components' in analysis_result:
            reproducibility_data['confidence_components'] = analysis_result['confidence_components']
        if 'setup_quality_components' in analysis_result:
            reproducibility_data['setup_quality_components'] = analysis_result['setup_quality_components']
        if 'market_environment_components' in analysis_result:
            reproducibility_data['market_environment_components'] = analysis_result['market_environment_components']

        # Capture reproducibility metadata
        reproducibility_data['prompt_version'] = prompt_version or 'unknown'
        reproducibility_data['prompt_content'] = prompt_content or ''
        reproducibility_data['validation_results'] = analysis_result.get('validation_results', {})

        return reproducibility_data
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def get_required_settings(cls) -> Dict[str, Any]:
        """
        Get strategy-specific settings schema.

        Returns:
            Dict with settings schema defining what settings this strategy needs.
            Each setting should have: name, type, default, description

        Examples:
            Price-based: {
                "enable_position_tightening": {"type": "bool", "default": True, "description": "..."},
                "enable_sl_tightening": {"type": "bool", "default": True, "description": "..."},
                "rr_tightening_steps": {"type": "int", "default": 3, "description": "..."},
            }
            Spread-based: {
                "enable_spread_monitoring": {"type": "bool", "default": True, "description": "..."},
                "z_score_monitoring_interval": {"type": "int", "default": 5, "description": "..."},
                "spread_reversion_threshold": {"type": "float", "default": 0.5, "description": "..."},
            }
        """
        raise NotImplementedError

    def get_strategy_specific_settings(self) -> Dict[str, Any]:
        """
        Get strategy-specific settings for this instance.

        Loads settings from instances.settings['strategy_specific'][STRATEGY_TYPE]
        Falls back to defaults from get_required_settings() if not found.
        Merges loaded settings with defaults to ensure all required settings are present.

        Returns:
            Dict with strategy-specific settings for this instance
        """
        # Get defaults first
        required_settings = self.get_required_settings()
        defaults = {}
        for setting_name, setting_schema in required_settings.items():
            if "default" in setting_schema:
                defaults[setting_name] = setting_schema["default"]

        # Try to load from database if instance_id provided
        try:
            if self.instance_id:
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
                        strategy_specific = settings.get('strategy_specific', {})
                        strategy_settings = strategy_specific.get(self.STRATEGY_TYPE, {})

                        if strategy_settings:
                            # Apply type conversion to all settings from database
                            converted_settings = {}
                            for key, value in strategy_settings.items():
                                converted_settings[key] = self._convert_setting_type(key, value)

                            self.logger.debug(
                                f"Loaded strategy-specific settings for {self.STRATEGY_TYPE}",
                                extra={"instance_id": self.instance_id}
                            )
                            # Merge with defaults to ensure all required settings are present
                            return {**defaults, **converted_settings}
                finally:
                    release_connection(conn)
        except Exception as e:
            self.logger.warning(
                f"Failed to load strategy-specific settings: {e}. Using defaults.",
                extra={"instance_id": self.instance_id}
            )

        # Return defaults
        return defaults

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
            "strategy_uuid": str,
            "strategy_type": str,
            "strategy_name": str,
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

