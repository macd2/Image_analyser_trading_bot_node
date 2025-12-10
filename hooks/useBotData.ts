'use client';

import { useState, useEffect, useCallback } from 'react';

/**
 * Generic hook for fetching bot data with polling support
 */
export function useBotData<T>(
  endpoint: string,
  options: {
    refreshInterval?: number; // ms, 0 = no polling
    enabled?: boolean;
  } = {}
) {
  const { refreshInterval = 0, enabled = true } = options;

  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  const fetchData = useCallback(async (isManualRefresh = false) => {
    if (!enabled) return;

    if (isManualRefresh) setRefreshing(true);

    try {
      const res = await fetch(endpoint);
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }
      const json = await res.json();
      setData(json);
      setError(null);
      setLastUpdate(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setLoading(false);
      if (isManualRefresh) setRefreshing(false);
    }
  }, [endpoint, enabled]);

  // Initial fetch
  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Polling
  useEffect(() => {
    if (refreshInterval > 0 && enabled) {
      const interval = setInterval(fetchData, refreshInterval);
      return () => clearInterval(interval);
    }
    return undefined;
  }, [fetchData, refreshInterval, enabled]);

  return { data, loading, refreshing, error, lastUpdate, refetch: fetchData };
}

// ============================================================
// SOURCER STATUS HOOK
// ============================================================

export interface SourcerStatus {
  next_capture: {
    time: string;
    seconds_remaining: number;
  };
  timeframe: string;
  watchlist: string[];
  current_cycle: {
    id: string | null;
    started_at: string | null;
    charts_captured: number;
    status: string;
  };
  recent_captures: {
    symbol: string;
    timeframe: string;
    timestamp: string;
    chart_path: string | null;
    status: 'success' | 'failed';
  }[];
  stats: {
    captured_today: number;
    failed_today: number;
    symbols_count: number;
  };
}

export function useSourcerStatus(refreshInterval = 5000, instanceId?: string) {
  const url = instanceId
    ? `/api/bot/sourcer?instance_id=${instanceId}`
    : '/api/bot/sourcer';
  return useBotData<SourcerStatus>(url, { refreshInterval });
}

// ============================================================
// POSITIONS HOOK
// ============================================================

export interface OpenPosition {
  id: string;
  symbol: string;
  side: 'LONG' | 'SHORT';
  entry_price: number;
  current_price: number | null;
  quantity: number;
  stop_loss: number;
  take_profit: number;
  pnl_percent: number;
  pnl_usd: number;
  duration: string;
  confidence: number | null;
  filled_at: string;
}

export interface ClosedTrade {
  id: string;
  symbol: string;
  side: 'LONG' | 'SHORT';
  result: 'TP Hit' | 'SL Hit' | 'Manual Close';
  pnl_percent: number;
  closed_at: string;
}

export interface PositionsData {
  open_positions: OpenPosition[];
  closed_today: ClosedTrade[];
  stats: {
    open_count: number;
    unrealized_pnl: number;
    closed_today_count: number;
    win_rate_today: number;
    total_pnl_today: number;
  };
}

export function usePositions(refreshInterval = 5000) {
  return useBotData<PositionsData>('/api/bot/positions', { refreshInterval });
}

// ============================================================
// CYCLES/ANALYSIS HOOK  
// ============================================================

export interface AnalysisResult {
  symbol: string;
  recommendation: string;
  confidence: number;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  risk_reward: number | null;
  setup_quality: number;
  rr_score: number;
  market_score: number;
  status: 'valid' | 'low' | 'skip';
  reasoning: string | null;
}

export interface CyclesData {
  cycles: Array<{
    id: string;
    timeframe: string;
    cycle_number: number;
    boundary_time: string;
    status: string;
    charts_captured: number;
    recommendations_generated: number;
    trades_executed: number;
    started_at: string;
  }>;
  current_cycle_analysis: AnalysisResult[];
  prompt_info: {
    name: string;
    model: string;
    avg_confidence: number;
  };
  stats: {
    total_cycles: number;
    images_analyzed: number;
    valid_signals: number;
    actionable_pct: number;
  };
}

export function useCyclesData(refreshInterval = 10000, instanceId?: string) {
  const baseUrl = '/api/bot/cycles?current_only=true';
  const url = instanceId
    ? `${baseUrl}&instance_id=${instanceId}`
    : baseUrl;
  return useBotData<CyclesData>(url, { refreshInterval });
}

// ============================================================
// TRADES/EXECUTION HOOK
// ============================================================

export interface TradeRecord {
  id: string;
  symbol: string;
  side: string;
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  quantity: number;
  status: string;
  order_id: string | null;
  fill_price: number | null;
  confidence: number | null;
  created_at: string;
  filled_at: string | null;
}

export interface TradesData {
  trades: TradeRecord[];
  stats: {
    total: number;
    winning: number;
    losing: number;
    win_rate: number;
    total_pnl_usd: number;
    avg_pnl_percent: number;
  };
}

export function useTradesData(refreshInterval = 5000, instanceId?: string) {
  const url = instanceId
    ? `/api/bot/trades?limit=50&instance_id=${instanceId}`
    : '/api/bot/trades?limit=50';
  return useBotData<TradesData>(url, { refreshInterval });
}

