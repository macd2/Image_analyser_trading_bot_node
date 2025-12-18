"""
Configuration settings for trading bot V2.
Reads dashboard-configurable settings from database, static settings from YAML.

NO DEFAULTS - All required settings must be set in the database.
Bot will fail to start if any required setting is missing.
"""

import os
import json
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Load .env.local from project root (unified env file)
_env_path = Path(__file__).parent.parent.parent.parent / '.env.local'
if _env_path.exists():
    load_dotenv(_env_path)
else:
    load_dotenv()  # Fallback to default .env lookup

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Raised when required configuration is missing."""
    pass

# Path to config.yaml (relative to this file or working directory)
# Using centralized path manager to eliminate hardcoded paths
from trading_bot.core.path_manager import get_config_yaml_path
CONFIG_YAML_PATH = get_config_yaml_path()


@dataclass
class PathsConfig:
    """File paths configuration (from YAML only)."""
    database: str
    charts: str
    logs: str
    session_file: str


@dataclass
class ChartCleaningConfig:
    """Chart cleaning configuration (from YAML only)."""
    enable_age_based_cleaning: bool
    max_file_age_hours: int
    enable_cycle_based_cleaning: bool


@dataclass
class FileManagementConfig:
    """File management configuration (from YAML only)."""
    enable_backup: bool
    chart_cleaning: Optional[ChartCleaningConfig] = None


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration (from YAML only)."""
    error_threshold: int = 5
    recovery_timeout: int = 300
    max_recv_window: int = 300000
    backoff_multiplier: float = 2.0
    jitter_range: float = 0.1


@dataclass
class BybitConfig:
    """Bybit configuration (mixed: some from DB, some from YAML)."""
    use_testnet: bool  # From DB
    recv_window: int   # From DB
    max_retries: int   # From DB
    circuit_breaker: Optional[CircuitBreakerConfig] = None  # From YAML


@dataclass
class OpenAIConfig:
    """OpenAI configuration (mixed)."""
    api_key: str       # From environment
    model: str         # From DB
    assistant_id: str  # From DB
    max_tokens: int = 4096      # Default
    temperature: float = 0.1    # Default


@dataclass
class RRTighteningStep:
    """Single RR tightening step."""
    threshold: float
    sl_position: float


@dataclass
class TradingConfig:
    """Trading configuration (mostly from DB)."""
    # Core settings (from DB)
    paper_trading: bool
    auto_approve_trades: bool
    min_confidence_threshold: float
    min_rr: float
    risk_percentage: float
    max_loss_usd: float
    leverage: int
    max_concurrent_trades: int
    timeframe: str  # From instance or DB

    # Tightening (from DB)
    enable_position_tightening: bool
    enable_sl_tightening: bool
    rr_tightening_steps: Dict[str, RRTighteningStep] = field(default_factory=dict)

    # Position sizing (from DB)
    use_enhanced_position_sizing: bool = True
    min_position_value_usd: float = 50.0

    # Kelly Criterion (from DB)
    use_kelly_criterion: bool = False
    kelly_fraction: float = 0.3  # Fractional Kelly (0.3 = 30% of full Kelly)
    kelly_window: int = 30  # Number of recent trades to analyze

    # Order replacement (from DB)
    enable_intelligent_replacement: bool = True
    min_score_improvement_threshold: float = 0.15

    # Enhanced Position Monitor Settings (optional - from DB)
    # TP Proximity Feature
    enable_tp_proximity_trailing: bool = False
    tp_proximity_threshold_pct: float = 1.0
    tp_proximity_trailing_pct: float = 1.0

    # Age-based tightening
    age_tightening_enabled: bool = False
    age_tightening_max_pct: float = 30.0
    age_tightening_min_profit_threshold: float = 1.0
    age_tightening_bars: Dict[str, float] = field(default_factory=dict)

    # Age-based cancellation
    age_cancellation_enabled: bool = False
    age_cancellation_max_bars: Dict[str, float] = field(default_factory=dict)

    # Strategy-specific settings (loaded dynamically based on strategy type)
    strategy_specific_settings: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TradingViewBrowserConfig:
    """TradingView browser settings (from YAML only)."""
    headless: bool = True
    timeout: int = 300000
    viewport_width: int = 1600
    viewport_height: int = 900
    use_vnc: bool = False
    vnc_display: str = ":99"
    vnc_window_size: str = "1920,1080"
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


@dataclass
class TradingViewScreenshotConfig:
    """TradingView screenshot settings (from YAML only)."""
    chart_selector: str = ".chart-container"
    wait_for_load: int = 5000
    quality: int = 90
    hide_elements: list = None  # Elements to hide before screenshot

    def __post_init__(self):
        if self.hide_elements is None:
            self.hide_elements = []


@dataclass
class TradingViewRateLimitConfig:
    """TradingView rate limiting settings."""
    respect_rate_limits: bool = True
    delay_between_requests: float = 2.0
    max_requests_per_minute: int = 20


@dataclass
class TradingViewAuthConfig:
    """TradingView authentication settings."""
    username: str = ""
    password: str = ""
    session_file: str = ".tradingview_session"
    max_login_attempts: int = 3
    login_retry_delay: float = 5.0


@dataclass
class TradingViewRetryConfig:
    """TradingView retry configuration."""
    max_attempts: int = 3
    backoff_factor: float = 2.0
    base_delay: float = 1.0


@dataclass
class TradingViewConfig:
    """TradingView configuration (from YAML only)."""
    enabled: bool = True
    target_chart: str = ""
    chart_url_template: str = "https://www.tradingview.com/chart/?symbol=BYBIT:{symbol}.P&interval={interval}"
    browser: Optional[TradingViewBrowserConfig] = None
    screenshot: Optional[TradingViewScreenshotConfig] = None
    rate_limit: Optional[TradingViewRateLimitConfig] = None
    auth: Optional[TradingViewAuthConfig] = None
    retry: Optional[TradingViewRetryConfig] = None

    def __post_init__(self):
        """Initialize default sub-configs if not provided."""
        if self.retry is None:
            self.retry = TradingViewRetryConfig()


@dataclass
class ConfigV2:
    """Main configuration class for V2 trading bot."""
    paths: PathsConfig
    openai: OpenAIConfig
    bybit: BybitConfig
    trading: TradingConfig
    file_management: FileManagementConfig
    tradingview: Optional[TradingViewConfig] = None

    def get_agent_config(self, agent_name: str) -> 'AgentConfig':
        """
        Get agent-specific configuration.

        Args:
            agent_name: Name of the agent (e.g., 'analyzer')

        Returns:
            AgentConfig with model, max_tokens, temperature, etc.
        """
        # For now, return the OpenAI config as agent config
        # This can be extended later for agent-specific configurations
        return AgentConfig(
            model=self.openai.model,
            max_tokens=self.openai.max_tokens,
            temperature=self.openai.temperature,
            reasoning_effort=None  # Can be added later for specific agents
        )

    @classmethod
    def load(cls, config_yaml_path: Optional[str] = None, instance_id: str = None) -> 'ConfigV2':
        """
        Load configuration from instance settings and YAML (static settings).

        Args:
            config_yaml_path: Path to YAML file for static settings
            instance_id: REQUIRED - Instance ID to load settings from

        Priority:
        1. Instance settings (from instances.settings JSON)
        2. YAML file (static settings like paths, browser config)
        3. Environment variables (secrets like API keys)
        """
        if not instance_id:
            raise ConfigurationError("instance_id is required. Global config table is deprecated.")

        yaml_path = Path(config_yaml_path) if config_yaml_path else CONFIG_YAML_PATH

        # Load YAML for static settings
        yaml_data = {}
        if yaml_path.exists():
            with open(yaml_path, 'r') as f:
                yaml_data = yaml.safe_load(f) or {}

        # Load database config from instance settings
        db_config = cls._load_instance_config(instance_id)

        return cls(
            paths=cls._load_paths(yaml_data),
            openai=cls._load_openai(db_config),
            bybit=cls._load_bybit(yaml_data, db_config),
            trading=cls._load_trading(db_config),
            file_management=cls._load_file_management(yaml_data),
            tradingview=cls._load_tradingview(yaml_data, db_config),
        )

    @classmethod
    def from_instance(cls, instance_id: str, config_yaml_path: Optional[str] = None) -> 'ConfigV2':
        """Load config from a specific instance."""
        return cls.load(config_yaml_path, instance_id=instance_id)

    @staticmethod
    def _load_instance_config(instance_id: str) -> Dict[str, Any]:
        """Load config from instance's settings JSON."""
        from trading_bot.db import get_connection, query_one, release_connection

        conn = get_connection()
        row = query_one(
            conn,
            "SELECT settings, timeframe, min_confidence, max_leverage FROM instances WHERE id = ?",
            (instance_id,)
        )
        release_connection(conn)

        if not row:
            raise ConfigurationError(f"Instance {instance_id} not found in database.")

        # Parse settings JSON
        # PostgreSQL with RealDictCursor returns JSON/JSONB as dict, SQLite returns string
        settings_data = row['settings']
        config = {}

        try:
            # Handle both dict (PostgreSQL) and string (SQLite)
            if isinstance(settings_data, dict):
                settings = settings_data
            elif isinstance(settings_data, str):
                settings = json.loads(settings_data) if settings_data else {}
            else:
                settings = {}

            for key, value in settings.items():
                # Parse value based on content
                if isinstance(value, str):
                    if value.lower() in ('true', 'false'):
                        config[key] = value.lower() == 'true'
                    elif value.startswith('{') or value.startswith('['):
                        try:
                            config[key] = json.loads(value)
                        except:
                            config[key] = value
                    else:
                        # Try to parse as number
                        try:
                            config[key] = float(value) if '.' in value else int(value)
                        except ValueError:
                            config[key] = value
                else:
                    config[key] = value
        except json.JSONDecodeError:
            raise ConfigurationError(f"Invalid settings JSON for instance {instance_id}")

        # Also include top-level instance fields
        if row['timeframe']:
            config['trading.timeframe'] = row['timeframe']
        if row['min_confidence'] is not None:
            config['trading.min_confidence_threshold'] = row['min_confidence']
        if row['max_leverage'] is not None:
            config['trading.leverage'] = row['max_leverage']

        if not config:
            raise ConfigurationError(f"No configuration found for instance {instance_id}. Please configure settings via dashboard.")

        return config

    @staticmethod
    def _require(db_config: dict, key: str, context: str = "") -> Any:
        """Get a required config value, raise error if missing."""
        if key not in db_config:
            raise ConfigurationError(f"Missing required config: {key}. {context}")
        return db_config[key]

    @staticmethod
    def _load_paths(yaml_data: dict) -> PathsConfig:
        """Load paths from YAML."""
        paths = yaml_data.get('paths', {})
        return PathsConfig(
            database=paths.get('database', 'data/trading.db'),
            charts=paths.get('charts', 'data/charts'),
            logs=paths.get('logs', 'logs'),
            session_file=paths.get('session_file', 'data/'),
        )

    @classmethod
    def _load_openai(cls, db_config: dict) -> OpenAIConfig:
        """Load OpenAI config from DB + environment. All settings required."""
        from trading_bot.core.secrets_manager import get_openai_api_key

        # Try to get from strategy-specific settings first (new location)
        strategy_config = db_config.get('strategy_config', {})
        model = strategy_config.get('model')
        assistant_id = strategy_config.get('assistant_id')

        # Fallback to old location for backward compatibility
        if not model:
            model = db_config.get('openai.model')
        if not assistant_id:
            assistant_id = db_config.get('openai.assistant_id')

        return OpenAIConfig(
            api_key=get_openai_api_key(),
            model=model or cls._require(db_config, 'openai.model', "Set via dashboard."),
            assistant_id=assistant_id or cls._require(db_config, 'openai.assistant_id', "Set via dashboard."),
        )

    @classmethod
    def _load_bybit(cls, yaml_data: dict, db_config: dict) -> BybitConfig:
        """Load Bybit config from DB + YAML. DB settings required."""
        bybit_yaml = yaml_data.get('bybit', {})
        cb_data = bybit_yaml.get('circuit_breaker', {})

        return BybitConfig(
            use_testnet=cls._require(db_config, 'bybit.use_testnet', "Set via dashboard."),
            recv_window=cls._require(db_config, 'bybit.recv_window', "Set via dashboard."),
            max_retries=cls._require(db_config, 'bybit.max_retries', "Set via dashboard."),
            circuit_breaker=CircuitBreakerConfig(
                error_threshold=cb_data.get('error_threshold', 5),
                recovery_timeout=cb_data.get('recovery_timeout', 300),
                max_recv_window=cb_data.get('max_recv_window', 300000),
                backoff_multiplier=cb_data.get('backoff_multiplier', 2.0),
                jitter_range=cb_data.get('jitter_range', 0.1),
            ) if cb_data else None,
        )

    @classmethod
    def _load_trading(cls, db_config: dict) -> TradingConfig:
        """Load trading config from DB. Core settings required, enhanced monitor settings optional."""
        # Parse RR tightening steps (required)
        rr_steps_raw = cls._require(db_config, 'trading.rr_tightening_steps', "Set via dashboard.")
        rr_steps = {}
        for name, step_data in rr_steps_raw.items():
            if isinstance(step_data, dict):
                rr_steps[name] = RRTighteningStep(
                    threshold=step_data['threshold'],
                    sl_position=step_data['sl_position'],
                )

        # Parse age-based tightening bars (optional)
        age_tightening_bars = {}
        age_tightening_bars_raw = db_config.get('trading.age_tightening_bars', {})
        if isinstance(age_tightening_bars_raw, dict):
            age_tightening_bars = {k: float(v) for k, v in age_tightening_bars_raw.items()}

        # Parse age-based cancellation bars (optional)
        age_cancellation_bars = {}
        age_cancellation_bars_raw = db_config.get('trading.age_cancellation_max_bars', {})
        if isinstance(age_cancellation_bars_raw, dict):
            age_cancellation_bars = {k: float(v) for k, v in age_cancellation_bars_raw.items()}

        # Load strategy-specific settings (optional)
        strategy_specific_settings = cls._load_strategy_specific_settings(db_config)

        return TradingConfig(
            paper_trading=cls._require(db_config, 'trading.paper_trading', "Set via dashboard."),
            auto_approve_trades=cls._require(db_config, 'trading.auto_approve_trades', "Set via dashboard."),
            min_confidence_threshold=cls._require(db_config, 'trading.min_confidence_threshold', "Set via dashboard."),
            min_rr=cls._require(db_config, 'trading.min_rr', "Set via dashboard."),
            risk_percentage=cls._require(db_config, 'trading.risk_percentage', "Set via dashboard."),
            max_loss_usd=cls._require(db_config, 'trading.max_loss_usd', "Set via dashboard."),
            leverage=cls._require(db_config, 'trading.leverage', "Set via dashboard."),
            max_concurrent_trades=cls._require(db_config, 'trading.max_concurrent_trades', "Set via dashboard."),
            timeframe=cls._require(db_config, 'trading.timeframe', "Set via dashboard. (e.g., '1h', '4h', '1d')"),
            enable_position_tightening=cls._require(db_config, 'trading.enable_position_tightening', "Set via dashboard."),
            enable_sl_tightening=cls._require(db_config, 'trading.enable_sl_tightening', "Set via dashboard."),
            rr_tightening_steps=rr_steps,
            use_enhanced_position_sizing=cls._require(db_config, 'trading.use_enhanced_position_sizing', "Set via dashboard."),
            min_position_value_usd=cls._require(db_config, 'trading.min_position_value_usd', "Set via dashboard."),
            enable_intelligent_replacement=cls._require(db_config, 'trading.enable_intelligent_replacement', "Set via dashboard."),
            min_score_improvement_threshold=cls._require(db_config, 'trading.min_score_improvement_threshold', "Set via dashboard."),
            # Enhanced position monitor settings (optional)
            enable_tp_proximity_trailing=db_config.get('trading.enable_tp_proximity_trailing', False),
            tp_proximity_threshold_pct=db_config.get('trading.tp_proximity_threshold_pct', 1.0),
            tp_proximity_trailing_pct=db_config.get('trading.tp_proximity_trailing_pct', 1.0),
            age_tightening_enabled=db_config.get('trading.age_tightening_enabled', False),
            age_tightening_max_pct=db_config.get('trading.age_tightening_max_pct', 30.0),
            age_tightening_min_profit_threshold=db_config.get('trading.age_tightening_min_profit_threshold', 1.0),
            age_tightening_bars=age_tightening_bars,
            age_cancellation_enabled=db_config.get('trading.age_cancellation_enabled', False),
            age_cancellation_max_bars=age_cancellation_bars,
            use_kelly_criterion=db_config.get('trading.use_kelly_criterion', False),
            kelly_fraction=db_config.get('trading.kelly_fraction', 0.3),
            kelly_window=db_config.get('trading.kelly_window', 30),
            strategy_specific_settings=strategy_specific_settings,
        )

    @staticmethod
    def _load_strategy_specific_settings(db_config: dict) -> Dict[str, Any]:
        """
        Load strategy-specific settings from database config.

        Returns a dict with strategy-specific settings for each strategy type.
        These are loaded from instances.settings['strategy_specific'][STRATEGY_TYPE]
        """
        strategy_specific = {}

        # Extract strategy_specific settings from db_config
        # Keys are like: strategy_specific.price_based.enable_position_tightening
        for key, value in db_config.items():
            if key.startswith('strategy_specific.'):
                parts = key.split('.')
                if len(parts) >= 3:
                    strategy_type = parts[1]  # e.g., 'price_based' or 'spread_based'
                    setting_name = '.'.join(parts[2:])  # e.g., 'enable_position_tightening'

                    if strategy_type not in strategy_specific:
                        strategy_specific[strategy_type] = {}

                    strategy_specific[strategy_type][setting_name] = value

        return strategy_specific

    @staticmethod
    def _load_file_management(yaml_data: dict) -> FileManagementConfig:
        """Load file management from YAML."""
        fm = yaml_data.get('file_management', {})
        cc = fm.get('chart_cleaning', {})

        return FileManagementConfig(
            enable_backup=fm.get('enable_backup', True),
            chart_cleaning=ChartCleaningConfig(
                enable_age_based_cleaning=cc.get('enable_age_based_cleaning', True),
                max_file_age_hours=cc.get('max_file_age_hours', 2),
                enable_cycle_based_cleaning=cc.get('enable_cycle_based_cleaning', True),
            ) if cc else None,
        )

    @classmethod
    def _load_tradingview(cls, yaml_data: dict, db_config: Optional[dict] = None) -> Optional[TradingViewConfig]:
        """Load TradingView config from YAML and instance settings (db_config)."""
        tv = yaml_data.get('tradingview', {})
        if not tv:
            return None

        # Helper to get value with instance settings priority
        def get_value(key: str, default):
            if db_config is not None:
                # Try strategy-specific location first (new)
                strategy_config = db_config.get('strategy_config', {})
                if key == 'target_chart' and 'target_chart' in strategy_config:
                    return strategy_config['target_chart']
                if key == 'chart_timeframe' and 'chart_timeframe' in strategy_config:
                    return strategy_config['chart_timeframe']

                # Fallback to old location for backward compatibility
                db_key = f'tradingview.{key}'
                if db_key in db_config:
                    return db_config[db_key]
            return tv.get(key, default)

        # TradingView is always enabled for PromptStrategy (no longer configurable)
        enabled = True

        # Chart URL template can fallback to YAML
        chart_url_template = tv.get('chart_url_template', 'https://www.tradingview.com/chart/?symbol=BYBIT:{symbol}.P&interval={interval}')

        # Target chart is REQUIRED from instance settings
        target_chart = get_value('target_chart', '')
        if not target_chart:
            raise ConfigurationError(
                "Missing required config: strategy_specific.prompt_strategy.target_chart. "
                "Set via dashboard."
            )

        browser_data = tv.get('browser', {})
        screenshot_data = tv.get('screenshot', {})
        rate_limit_data = tv.get('rate_limit', {})
        auth_data = tv.get('auth', {})

        return TradingViewConfig(
            enabled=enabled,
            target_chart=target_chart,
            chart_url_template=chart_url_template,
            browser=TradingViewBrowserConfig(
                headless=browser_data.get('headless', True),
                timeout=browser_data.get('timeout', 300000),
                viewport_width=browser_data.get('viewport_width', 1600),
                viewport_height=browser_data.get('viewport_height', 900),
                use_vnc=browser_data.get('use_vnc', False),
                user_agent=browser_data.get('user_agent', "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
            ) if browser_data else TradingViewBrowserConfig(),
            screenshot=TradingViewScreenshotConfig(
                chart_selector=screenshot_data.get('chart_selector', '.chart-container'),
                wait_for_load=screenshot_data.get('wait_for_load', 5000),
                quality=screenshot_data.get('quality', 90),
            ) if screenshot_data else TradingViewScreenshotConfig(),
            rate_limit=TradingViewRateLimitConfig(
                respect_rate_limits=rate_limit_data.get('respect_rate_limits', True),
                delay_between_requests=rate_limit_data.get('delay_between_requests', 2.0),
                max_requests_per_minute=rate_limit_data.get('max_requests_per_minute', 20),
            ),
            auth=TradingViewAuthConfig(
                username=auth_data.get('username', os.environ.get('TRADINGVIEW_USERNAME', '')),
                password=auth_data.get('password', os.environ.get('TRADINGVIEW_PASSWORD', '')),
                session_file=auth_data.get('session_file', '.tradingview_session'),
                max_login_attempts=auth_data.get('max_login_attempts', 3),
                login_retry_delay=auth_data.get('login_retry_delay', 5.0),
            ),
        )


# Convenience function
def load_config(config_yaml_path: Optional[str] = None, instance_id: Optional[str] = None) -> ConfigV2:
    """Load configuration from database and YAML.

    Args:
        config_yaml_path: Path to YAML config file
        instance_id: Instance ID to load config from (required)
    """
    if not instance_id:
        raise ConfigurationError("instance_id is required. Use ConfigV2.from_instance(instance_id) instead.")
    return ConfigV2.load(config_yaml_path, instance_id=instance_id)


# Backward compatibility aliases
Config = ConfigV2  # Alias for code that imports Config

# Add agent configuration support to ConfigV2
@dataclass
class AgentConfig:
    """Agent-specific configuration."""
    model: str
    max_tokens: int
    temperature: float
    reasoning_effort: Optional[str] = None
