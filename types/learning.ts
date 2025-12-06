// Types for learning/backtest data - matches prompt_performance/core/backtest_store.py schema

export interface Run {
  id: number;
  run_signature: string;
  started_at: string | null;
  finished_at: string | null;
  duration_sec: number | null;
  charts_dir: string | null;
  selection_strategy: string | null;
  num_images: number | null;
  prompts_json: string | null;
  symbols_json: string | null;
}

export interface Analysis {
  id: number;
  run_id: number;
  prompt_name: string;
  prompt_version: string | null;
  prompt_hash: string | null;
  symbol: string;
  timeframe: string;
  timestamp: string;
  image_path: string;
  recommendation: string | null;
  confidence: number | null;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  rr_ratio: number | null;
  status: string | null;
  raw_response: string | null;
  rationale: string | null;
  error_message: string | null;
  assistant_id: string | null;
  assistant_model: string | null;
}

export interface Trade {
  id: number;
  run_id: number;
  prompt_name: string;
  prompt_version: string | null;
  prompt_hash: string | null;
  symbol: string;
  timeframe: string;
  timestamp: string;
  direction: 'LONG' | 'SHORT';
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  confidence: number | null;
  rr_ratio: number | null;
  outcome: 'WIN' | 'LOSS' | 'PENDING' | null;
  duration_candles: number | null;
  achieved_rr: number | null;
  exit_price: number | null;
  exit_candle_index: number | null;
  entry_candle_index: number | null;
  mfe_price: number | null;
  mae_price: number | null;
  mfe_percent: number | null;
  mae_percent: number | null;
  mfe_r: number | null;
  mae_r: number | null;
  realized_pnl_price: number | null;
  realized_pnl_percent: number | null;
  image_path: string;
}

// Aggregated stats for dashboard
export interface PromptStats {
  prompt_name: string;
  total_trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  avg_pnl_pct: number;
  total_pnl_pct: number;
  avg_confidence: number;
  avg_rr_ratio: number;
  symbol_count: number;
}

export interface SymbolStats {
  symbol: string;
  total_trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  avg_pnl_pct: number;
}

export interface TimeframeStats {
  timeframe: string;
  total_trades: number;
  wins: number;
  win_rate: number;
  avg_pnl_pct: number;
}

export interface ConfidenceBucket {
  bucket: number; // 0.0, 0.1, 0.2, ... 1.0
  trades: number;
  wins: number;
  win_rate: number;
}

export interface LearningInsight {
  type: 'positive' | 'negative' | 'neutral';
  title: string;
  description: string;
  metric?: number;
}

export interface LearningData {
  prompts: PromptStats[];
  symbols: SymbolStats[];
  timeframes: TimeframeStats[];
  confidenceBuckets: ConfidenceBucket[];
  insights: LearningInsight[];
  lastUpdated: string;
}

