'use client'

import { useState } from 'react'
import SpreadTradeChart from '@/components/shared/SpreadTradeChart'
import { useSpreadTradeData } from '@/hooks/useSpreadTradeData'
import { LoadingState, ErrorState } from '@/components/shared'

interface SpreadTradeChartExampleProps {
  tradeId: string
  showAssetPrices?: boolean
}

/**
 * Example component showing how to use SpreadTradeChart
 * 
 * Usage:
 * <SpreadTradeChartExample tradeId="trade-123" />
 */
export default function SpreadTradeChartExample({
  tradeId,
  showAssetPrices = true,
}: SpreadTradeChartExampleProps) {
  const { trade, loading, error } = useSpreadTradeData(tradeId)
  const [showChart, setShowChart] = useState(true)

  if (loading) return <LoadingState />
  if (error) return <ErrorState message={error} />
  if (!trade) return <ErrorState message="Trade not found" />

  // Validate this is a spread-based trade
  if (trade.strategy_type !== 'spread_based') {
    return (
      <ErrorState message={`This trade is not spread-based (type: ${trade.strategy_type})`} />
    )
  }

  return (
    <div className="space-y-4">
      {/* Trade Info Header */}
      <div className="bg-slate-900 border border-slate-700 rounded-lg p-4">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-xl font-bold text-white">{trade.symbol}</h2>
            <p className="text-sm text-slate-400">
              {trade.strategy_name} • {trade.strategy_type}
            </p>
          </div>
          <div className="text-right">
            <p className={`text-lg font-bold ${trade.pnl && trade.pnl > 0 ? 'text-green-400' : 'text-red-400'}`}>
              {trade.pnl ? `${trade.pnl > 0 ? '+' : ''}${trade.pnl.toFixed(2)}` : 'Pending'}
            </p>
            <p className="text-sm text-slate-400">
              {trade.status === 'closed' ? 'Closed' : 'Open'}
            </p>
          </div>
        </div>

        {/* Trade Details Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <p className="text-xs text-slate-400">Entry Price</p>
            <p className="text-sm font-semibold text-white">${trade.entry_price.toFixed(2)}</p>
          </div>
          <div>
            <p className="text-xs text-slate-400">Fill Price</p>
            <p className="text-sm font-semibold text-white">
              {trade.fill_price ? `$${trade.fill_price.toFixed(2)}` : 'N/A'}
            </p>
          </div>
          <div>
            <p className="text-xs text-slate-400">Stop Loss</p>
            <p className="text-sm font-semibold text-white">
              {trade.stop_loss ? `$${trade.stop_loss.toFixed(2)}` : 'N/A'}
            </p>
          </div>
          <div>
            <p className="text-xs text-slate-400">Take Profit</p>
            <p className="text-sm font-semibold text-white">
              {trade.take_profit ? `$${trade.take_profit.toFixed(2)}` : 'N/A'}
            </p>
          </div>
        </div>

        {/* Pair Symbol Info */}
        {trade.strategy_metadata?.pair_symbol && (
          <div className="mt-4 pt-4 border-t border-slate-700">
            <p className="text-xs text-slate-400">Pair Symbol</p>
            <p className="text-sm font-semibold text-white">{trade.strategy_metadata.pair_symbol}</p>
          </div>
        )}
      </div>

      {/* Chart Toggle */}
      <div className="flex gap-2">
        <button
          onClick={() => setShowChart(!showChart)}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition"
        >
          {showChart ? 'Hide Chart' : 'Show Chart'}
        </button>
      </div>

      {/* Spread Trade Chart */}
      {showChart && (
        <SpreadTradeChart
          trade={trade}
          height={800}
          mode="live"
          showAssetPrices={showAssetPrices}
        />
      )}
    </div>
  )
}

