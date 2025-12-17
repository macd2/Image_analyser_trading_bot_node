/**
 * Default configuration values for trading bot instances.
 * 
 * IMPORTANT: Keep this in sync with python/trading_bot/db/config_defaults.py
 * When adding new settings, update both files to maintain consistency.
 * 
 * Format: [key, value, type, category, description]
 */

// Default RR tightening steps
const DEFAULT_RR_TIGHTENING_STEPS = {
  "2R": { threshold: 2.0, sl_position: 1.2 },
  "2.5R": { threshold: 2.5, sl_position: 2.0 },
  "3R": { threshold: 3.0, sl_position: 2.5 }
};

export type ConfigType = 'string' | 'number' | 'boolean' | 'json';
export type ConfigCategory = 'trading' | 'tightening' | 'sizing' | 'replacement' | 'exchange' | 'ai' | 'tradingview';

export interface ConfigDefault {
  key: string;
  value: string | number | boolean | object;
  type: ConfigType;
  category: ConfigCategory;
  description: string;
}

/**
 * All dashboard-configurable settings with their default values.
 * This mirrors python/trading_bot/db/config_defaults.py::DEFAULT_CONFIG
 */
export const DEFAULT_CONFIG: ConfigDefault[] = [
  // Trading Core (8 settings)
  {
    key: "trading.paper_trading",
    value: false,
    type: "boolean",
    category: "trading",
    description: "Enable paper trading mode (no real trades)"
  },
  {
    key: "trading.auto_approve_trades",
    value: true,
    type: "boolean",
    category: "trading",
    description: "Skip Telegram confirmation for trades"
  },
  {
    key: "trading.min_confidence_threshold",
    value: 0.75,
    type: "number",
    category: "trading",
    description: "Minimum confidence score required for trades (0.0-1.0)"
  },
  {
    key: "trading.min_rr",
    value: 1.7,
    type: "number",
    category: "trading",
    description: "Minimum risk-reward ratio required for trades"
  },
  {
    key: "trading.risk_percentage",
    value: 0.01,
    type: "number",
    category: "trading",
    description: "Risk per trade as decimal (0.01 = 1% of account)"
  },
  {
    key: "trading.max_loss_usd",
    value: 10.0,
    type: "number",
    category: "trading",
    description: "Maximum USD risk per trade"
  },
  {
    key: "trading.leverage",
    value: 2,
    type: "number",
    category: "trading",
    description: "Trading leverage multiplier"
  },
  {
    key: "trading.max_concurrent_trades",
    value: 3,
    type: "number",
    category: "trading",
    description: "Maximum number of concurrent positions/orders"
  },
  {
    key: "trading.sl_adjustment_enabled",
    value: false,
    type: "boolean",
    category: "trading",
    description: "Enable pre-execution stop-loss adjustment"
  },
  {
    key: "trading.sl_adjustment_long_pct",
    value: 1.5,
    type: "number",
    category: "trading",
    description: "SL widening percentage for LONG trades (e.g., 1.5 = 1.5% wider)"
  },
  {
    key: "trading.sl_adjustment_short_pct",
    value: 1.5,
    type: "number",
    category: "trading",
    description: "SL widening percentage for SHORT trades (e.g., 1.5 = 1.5% wider)"
  },

  // Tightening (3 settings)
  {
    key: "trading.enable_position_tightening",
    value: true,
    type: "boolean",
    category: "tightening",
    description: "Enable stop-loss tightening based on profit"
  },
  {
    key: "trading.enable_sl_tightening",
    value: false,
    type: "boolean",
    category: "tightening",
    description: "Enable RR-based stop-loss tightening"
  },
  {
    key: "trading.rr_tightening_steps",
    value: DEFAULT_RR_TIGHTENING_STEPS,
    type: "json",
    category: "tightening",
    description: "RR levels and SL positions for tightening"
  },

  // Position Sizing (5 settings)
  {
    key: "trading.use_enhanced_position_sizing",
    value: true,
    type: "boolean",
    category: "sizing",
    description: "Use confidence/volatility weighting for position sizing"
  },
  {
    key: "trading.min_position_value_usd",
    value: 50.0,
    type: "number",
    category: "sizing",
    description: "Minimum position size in USD"
  },
  {
    key: "trading.use_kelly_criterion",
    value: false,
    type: "boolean",
    category: "sizing",
    description: "Use Kelly Criterion for dynamic position sizing based on trade history"
  },
  {
    key: "trading.kelly_fraction",
    value: 0.3,
    type: "number",
    category: "sizing",
    description: "Fractional Kelly multiplier (0.3 = 30% of full Kelly, safer than 1.0)"
  },
  {
    key: "trading.kelly_window",
    value: 30,
    type: "number",
    category: "sizing",
    description: "Number of recent trades to analyze for Kelly Criterion calculation"
  },

  // Order Replacement (2 settings)
  {
    key: "trading.enable_intelligent_replacement",
    value: true,
    type: "boolean",
    category: "replacement",
    description: "Enable intelligent order replacement based on score"
  },
  {
    key: "trading.min_score_improvement_threshold",
    value: 0.15,
    type: "number",
    category: "replacement",
    description: "Minimum score improvement required to replace an order"
  },

  // Exchange (3 settings)
  {
    key: "bybit.use_testnet",
    value: false,
    type: "boolean",
    category: "exchange",
    description: "Use Bybit testnet instead of mainnet"
  },
  {
    key: "bybit.recv_window",
    value: 30000,
    type: "number",
    category: "exchange",
    description: "API receive window in milliseconds"
  },
  {
    key: "bybit.max_retries",
    value: 5,
    type: "number",
    category: "exchange",
    description: "Maximum API retry attempts"
  },

  // AI (2 settings)
  {
    key: "openai.model",
    value: "gpt-4.1-mini",
    type: "string",
    category: "ai",
    description: "OpenAI model for chart analysis"
  },
  {
    key: "openai.assistant_id",
    value: "asst_m11ds7XhdYfN7voO0pRvgbul",
    type: "string",
    category: "ai",
    description: "OpenAI Assistant ID for analysis (empty = use direct API)"
  },
   // TradingView (2 settings)
  {
    key: "tradingview.enabled",
    value: true,
    type: "boolean",
    category: "tradingview",
    description: "Enable TradingView chart capture"
  },
  {
    key: "tradingview.target_chart",
    value: "https://www.tradingview.com/chart/iXrxoaRu/",
    type: "string",
    category: "tradingview",
    description: "Target chart URL for TradingView navigation"
  },

  // Strategy-Specific Settings - Price-Based Strategies (3 settings)
  {
    key: "strategy_specific.price_based.enable_position_tightening",
    value: true,
    type: "boolean",
    category: "ai",
    description: "Enable position tightening for price-based strategies"
  },
  {
    key: "strategy_specific.price_based.min_rr",
    value: 1.0,
    type: "number",
    category: "ai",
    description: "Minimum risk-reward ratio for price-based strategies"
  },
  {
    key: "strategy_specific.price_based.enable_spread_monitoring",
    value: true,
    type: "boolean",
    category: "ai",
    description: "Enable spread monitoring for price-based strategies"
  },

  // Strategy-Specific Settings - Spread-Based Strategies (8 settings)
  {
    key: "strategy_specific.spread_based.z_score_entry_threshold",
    value: 2.0,
    type: "number",
    category: "ai",
    description: "Z-score entry threshold for spread-based strategies"
  },
  {
    key: "strategy_specific.spread_based.z_score_exit_threshold",
    value: 0.5,
    type: "number",
    category: "ai",
    description: "Z-score exit threshold for spread-based strategies"
  },
  {
    key: "strategy_specific.spread_based.lookback_period",
    value: 120,
    type: "number",
    category: "ai",
    description: "Lookback period (bars) for cointegration analysis"
  },
  {
    key: "strategy_specific.spread_based.max_spread_deviation",
    value: 3.0,
    type: "number",
    category: "ai",
    description: "Maximum z-score deviation before force-closing position"
  },
  {
    key: "strategy_specific.spread_based.min_z_distance",
    value: 0.5,
    type: "number",
    category: "ai",
    description: "Minimum z-score distance to stop loss for signal validation"
  },
];

/**
 * Convert a config value to its string representation for storage.
 * Handles JSON objects, booleans, and primitives.
 */
function valueToString(value: string | number | boolean | object, type: ConfigType): string {
  if (type === 'json') {
    return JSON.stringify(value);
  }
  if (type === 'boolean') {
    return value ? 'true' : 'false';
  }
  return String(value);
}

/**
 * Get default instance settings as a JSON object ready for database storage.
 * This creates the settings object that will be stored in instances.settings field.
 *
 * @returns Record<string, string> - Settings object with all keys as strings
 */
export function getDefaultInstanceSettings(): Record<string, string> {
  const settings: Record<string, string> = {};

  for (const config of DEFAULT_CONFIG) {
    settings[config.key] = valueToString(config.value, config.type);
  }

  return settings;
}

/**
 * Get default values for top-level instance fields.
 * These are extracted from the settings and stored in dedicated columns.
 */
export function getDefaultInstanceFields() {
  return {
    timeframe: null, // No default timeframe - user should set this
    min_confidence: 0.75, // From trading.min_confidence_threshold
    max_leverage: 2, // From trading.leverage
  };
}

/**
 * Get a human-readable summary of default settings for display.
 */
export function getDefaultSettingsSummary(): string {
  const settings = getDefaultInstanceSettings();
  const categories = new Set(DEFAULT_CONFIG.map(c => c.category));

  return `${Object.keys(settings).length} settings across ${categories.size} categories`;
}

