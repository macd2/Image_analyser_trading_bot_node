/**
 * Learning data queries
 */

import { query } from './client';
import type {
  PromptStats,
  SymbolStats,
  TimeframeStats,
  ConfidenceBucket,
  Trade
} from '@/types/learning';

/**
 * Get prompt performance stats - ranked by win rate
 */
export async function getPromptStats(): Promise<PromptStats[]> {
  const sql = `
    SELECT
      prompt_name,
      COUNT(*) as total_trades,
      SUM(CASE WHEN LOWER(outcome) = 'win' THEN 1 ELSE 0 END) as wins,
      SUM(CASE WHEN LOWER(outcome) = 'loss' THEN 1 ELSE 0 END) as losses,
      ROUND(SUM(CASE WHEN LOWER(outcome) = 'win' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as win_rate,
      ROUND(AVG(COALESCE(realized_pnl_percent, 0)), 3) as avg_pnl_pct,
      ROUND(SUM(COALESCE(realized_pnl_percent, 0)), 3) as total_pnl_pct,
      ROUND(AVG(COALESCE(confidence, 0)), 3) as avg_confidence,
      ROUND(AVG(COALESCE(rr_ratio, 0)), 2) as avg_rr_ratio,
      COUNT(DISTINCT symbol) as symbol_count
    FROM trades
    WHERE outcome IS NOT NULL AND LOWER(outcome) NOT IN ('pending', 'expired')
    GROUP BY prompt_name
    ORDER BY avg_pnl_pct DESC, win_rate DESC, total_trades DESC
  `;
  return query<PromptStats>(sql);
}

/**
 * Get symbol performance stats
 */
export async function getSymbolStats(): Promise<SymbolStats[]> {
  const sql = `
    SELECT
      symbol,
      COUNT(*) as total_trades,
      SUM(CASE WHEN LOWER(outcome) = 'win' THEN 1 ELSE 0 END) as wins,
      SUM(CASE WHEN LOWER(outcome) = 'loss' THEN 1 ELSE 0 END) as losses,
      ROUND(SUM(CASE WHEN LOWER(outcome) = 'win' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as win_rate,
      ROUND(AVG(COALESCE(realized_pnl_percent, 0)), 3) as avg_pnl_pct
    FROM trades
    WHERE outcome IS NOT NULL AND LOWER(outcome) NOT IN ('pending', 'expired')
    GROUP BY symbol
    ORDER BY total_trades DESC
  `;
  return query<SymbolStats>(sql);
}

/**
 * Get timeframe performance stats
 */
export async function getTimeframeStats(): Promise<TimeframeStats[]> {
  const sql = `
    SELECT
      timeframe,
      COUNT(*) as total_trades,
      SUM(CASE WHEN LOWER(outcome) = 'win' THEN 1 ELSE 0 END) as wins,
      ROUND(SUM(CASE WHEN LOWER(outcome) = 'win' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as win_rate,
      ROUND(AVG(COALESCE(realized_pnl_percent, 0)), 3) as avg_pnl_pct
    FROM trades
    WHERE outcome IS NOT NULL AND LOWER(outcome) NOT IN ('pending', 'expired')
    GROUP BY timeframe
    ORDER BY total_trades DESC
  `;
  return query<TimeframeStats>(sql);
}

/**
 * Get confidence buckets for correlation analysis
 */
export async function getConfidenceBuckets(): Promise<ConfidenceBucket[]> {
  const sql = `
    SELECT
      ROUND(confidence, 1) as bucket,
      COUNT(*) as trades,
      SUM(CASE WHEN LOWER(outcome) = 'win' THEN 1 ELSE 0 END) as wins,
      ROUND(SUM(CASE WHEN LOWER(outcome) = 'win' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as win_rate
    FROM trades
    WHERE outcome IS NOT NULL AND LOWER(outcome) NOT IN ('pending', 'expired') AND confidence IS NOT NULL
    GROUP BY bucket
    ORDER BY bucket
  `;
  return query<ConfidenceBucket>(sql);
}

/**
 * Get recent trades for a prompt
 */
export async function getRecentTrades(promptName?: string, limit = 50): Promise<Trade[]> {
  let sql = `
    SELECT * FROM trades
    WHERE outcome IS NOT NULL AND LOWER(outcome) NOT IN ('pending', 'expired')
  `;
  const params: unknown[] = [];
  
  if (promptName) {
    sql += ` AND prompt_name = ?`;
    params.push(promptName);
  }
  
  sql += ` ORDER BY timestamp DESC LIMIT ?`;
  params.push(limit);
  
  return query<Trade>(sql, params);
}

/**
 * Get total summary stats
 */
export async function getSummaryStats(): Promise<{
  totalTrades: number;
  totalWins: number;
  overallWinRate: number;
  totalPnl: number;
  uniquePrompts: number;
  uniqueSymbols: number;
}> {
  const sql = `
    SELECT
      COUNT(*) as totalTrades,
      SUM(CASE WHEN LOWER(outcome) = 'win' THEN 1 ELSE 0 END) as totalWins,
      ROUND(SUM(CASE WHEN LOWER(outcome) = 'win' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as overallWinRate,
      ROUND(SUM(COALESCE(realized_pnl_percent, 0)), 3) as totalPnl,
      COUNT(DISTINCT prompt_name) as uniquePrompts,
      COUNT(DISTINCT symbol) as uniqueSymbols
    FROM trades
    WHERE outcome IS NOT NULL AND LOWER(outcome) NOT IN ('pending', 'expired')
  `;
  const results = await query<{
    totaltrades: number;
    totalwins: number;
    overallwinrate: number;
    totalpnl: number;
    uniqueprompts: number;
    uniquesymbols: number;
  }>(sql);
  const row = results[0];
  // Ensure numeric types (PostgreSQL returns strings for aggregates and lowercase column names)
  return {
    totalTrades: Number(row?.totaltrades) || 0,
    totalWins: Number(row?.totalwins) || 0,
    overallWinRate: Number(row?.overallwinrate) || 0,
    totalPnl: Number(row?.totalpnl) || 0,
    uniquePrompts: Number(row?.uniqueprompts) || 0,
    uniqueSymbols: Number(row?.uniquesymbols) || 0,
  };
}

