/**
 * Type definitions for Spread-Based Trading Chart Component
 */

export interface StrategyMetadata {
  // Current values (for realtime calculations)
  beta: number;
  spread_mean: number;
  spread_std: number;
  z_exit_threshold: number;
  pair_symbol: string;

  // Historical values at entry time (FROZEN - for chart and exit logic)
  z_score_at_entry: number;
  spread_mean_at_entry?: number;
  spread_std_at_entry?: number;

  // Prices at entry time (FROZEN - for fill)
  price_x_at_entry?: number;
  price_y_at_entry?: number;

  // Adaptive stop loss
  max_spread_deviation?: number;
}

export interface SpreadTradeData {
  id: string;
  symbol: string;
  side: 'Buy' | 'Sell';
  entry_price: number;
  stop_loss: number | null;
  take_profit: number | null;
  exit_price?: number | null;
  status: string;
  submitted_at?: string | null;
  filled_at?: string | null;
  fill_time?: string | null;
  fill_price?: number | null;
  closed_at?: string | null;
  created_at: string;
  timeframe?: string | null;
  dry_run?: number | null;
  rejection_reason?: string | null;
  exit_reason?: string | null;
  pnl?: number | null;
  strategy_type?: string | null;
  strategy_name?: string | null;
  strategy_metadata?: StrategyMetadata;
}

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface ZScorePoint {
  time: number;
  z_score: number;
  is_mean_reverting: boolean;
}

export interface SpreadPoint {
  time: number;
  spread: number;
  spread_mean: number;
  spread_std: number;
}

export interface PricePoint {
  time: number;
  price_x: number;
  price_y: number;
}

export interface TradeMarker {
  timeLabel: string;
  type: 'signal' | 'fill' | 'exit';
  color: string;
  label: string;
}

export interface ChartDataSet {
  zScores: ZScorePoint[];
  spreads: SpreadPoint[];
  prices: PricePoint[];
  entryTime?: number;
  exitTime?: number;
  signalMarker?: TradeMarker;
  fillMarker?: TradeMarker;
  exitMarker?: TradeMarker;
}

export interface SpreadTradeChartProps {
  trade: SpreadTradeData;
  height?: number;
  mode?: 'live' | 'historical';
  showAssetPrices?: boolean;
}

