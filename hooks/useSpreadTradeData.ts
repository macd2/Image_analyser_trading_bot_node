/**
 * Hook for fetching and managing spread-based trade data
 */

import { useEffect, useState, useCallback } from 'react'
import { SpreadTradeData } from '@/components/shared/SpreadTradeChart.types'

interface UseSpreadTradeDataOptions {
  tradeId?: string
  symbol?: string
  enabled?: boolean
  pollInterval?: number // ms, 0 = disabled
}

interface UseSpreadTradeDataResult {
  trade: SpreadTradeData | null
  loading: boolean
  error: string | null
  refetch: () => Promise<void>
}

/**
 * Fetch a single spread-based trade by ID
 */
export function useSpreadTradeData(
  tradeId: string,
  options: UseSpreadTradeDataOptions = {}
): UseSpreadTradeDataResult {
  const { enabled = true, pollInterval = 0 } = options
  const [trade, setTrade] = useState<SpreadTradeData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchTrade = useCallback(async () => {
    if (!enabled || !tradeId) {
      setLoading(false)
      return
    }

    try {
      setLoading(true)
      setError(null)

      const response = await fetch(`/api/bot/trades/${tradeId}`)
      if (!response.ok) {
        throw new Error(`Failed to fetch trade: ${response.statusText}`)
      }

      const data = await response.json()
      
      // Parse strategy_metadata if it's a string
      if (data.strategy_metadata && typeof data.strategy_metadata === 'string') {
        data.strategy_metadata = JSON.parse(data.strategy_metadata)
      }

      setTrade(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch trade')
      setTrade(null)
    } finally {
      setLoading(false)
    }
  }, [tradeId, enabled])

  // Initial fetch
  useEffect(() => {
    fetchTrade()
  }, [fetchTrade])

  // Polling
  useEffect(() => {
    if (!pollInterval || pollInterval <= 0) return

    const interval = setInterval(fetchTrade, pollInterval)
    return () => clearInterval(interval)
  }, [fetchTrade, pollInterval])

  return { trade, loading, error, refetch: fetchTrade }
}

/**
 * Fetch all spread-based trades for a symbol
 */
export function useSpreadTradesForSymbol(
  symbol: string,
  options: UseSpreadTradeDataOptions = {}
): {
  trades: SpreadTradeData[]
  loading: boolean
  error: string | null
  refetch: () => Promise<void>
} {
  const { enabled = true, pollInterval = 0 } = options
  const [trades, setTrades] = useState<SpreadTradeData[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchTrades = useCallback(async () => {
    if (!enabled || !symbol) {
      setLoading(false)
      return
    }

    try {
      setLoading(true)
      setError(null)

      const response = await fetch(`/api/bot/trades?symbol=${symbol}&strategy_type=spread_based`)
      if (!response.ok) {
        throw new Error(`Failed to fetch trades: ${response.statusText}`)
      }

      const data = await response.json()
      
      // Parse strategy_metadata for each trade
      const trades = (data.trades || []).map((trade: any) => {
        if (trade.strategy_metadata && typeof trade.strategy_metadata === 'string') {
          trade.strategy_metadata = JSON.parse(trade.strategy_metadata)
        }
        return trade
      })

      setTrades(trades)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch trades')
      setTrades([])
    } finally {
      setLoading(false)
    }
  }, [symbol, enabled])

  // Initial fetch
  useEffect(() => {
    fetchTrades()
  }, [fetchTrades])

  // Polling
  useEffect(() => {
    if (!pollInterval || pollInterval <= 0) return

    const interval = setInterval(fetchTrades, pollInterval)
    return () => clearInterval(interval)
  }, [fetchTrades, pollInterval])

  return { trades, loading, error, refetch: fetchTrades }
}

