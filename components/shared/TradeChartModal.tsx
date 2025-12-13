'use client'

import { X, TrendingUp, TrendingDown } from 'lucide-react'
import TradeChart, { TradeData } from './TradeChart'

interface TradeChartModalProps {
  isOpen: boolean
  onClose: () => void
  trade: TradeData | null
  mode?: 'live' | 'historical'
}

// Helper to calculate required decimal places for a price
function getPriceDecimals(price: number | null | undefined): number {
  if (!price) return 4
  const priceStr = price.toString()
  if (!priceStr.includes('.')) return 0
  const decimals = priceStr.split('.')[1]?.length || 0
  // Return at least what's needed to show the full precision, min 2, max 8
  return Math.max(2, Math.min(8, decimals))
}

export default function TradeChartModal({ isOpen, onClose, trade, mode = 'live' }: TradeChartModalProps) {
  if (!isOpen || !trade) return null

  // Normalize side to handle both 'Buy'/'Sell' and 'LONG'/'SHORT' formats
  const sideUpper = trade.side?.toUpperCase() || ''
  const isLong = sideUpper === 'BUY' || sideUpper === 'LONG'
  const isClosed = trade.status === 'closed' && trade.exit_price

  // Calculate required decimal precision from all prices
  const priceDecimals = Math.max(
    getPriceDecimals(trade.entry_price),
    getPriceDecimals(trade.stop_loss),
    getPriceDecimals(trade.take_profit),
    getPriceDecimals(trade.exit_price)
  )

  const formatPrice = (p: number | null | undefined) => p?.toFixed(priceDecimals) || '—'

  // Calculate PnL for closed trades
  const pnl = isClosed && trade.exit_price
    ? isLong
      ? (trade.exit_price - trade.entry_price) * 1 // qty assumed 1 for display
      : (trade.entry_price - trade.exit_price) * 1
    : null

  const pnlPercent = pnl !== null
    ? (pnl / trade.entry_price) * 100
    : null

  // Calculate Risk %, Reward %, and RR Ratio
  const riskPercent = trade.stop_loss && trade.entry_price
    ? isLong
      ? Math.abs((trade.stop_loss - trade.entry_price) / trade.entry_price) * 100
      : Math.abs((trade.stop_loss - trade.entry_price) / trade.entry_price) * 100
    : null

  const rewardPercent = trade.take_profit && trade.entry_price
    ? isLong
      ? Math.abs((trade.take_profit - trade.entry_price) / trade.entry_price) * 100
      : Math.abs((trade.entry_price - trade.take_profit) / trade.entry_price) * 100
    : null

  const rrRatio = riskPercent && rewardPercent && riskPercent !== 0
    ? rewardPercent / riskPercent
    : null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-black/70 backdrop-blur-sm" 
        onClick={onClose}
      />
      
      {/* Modal */}
      <div className="relative bg-slate-800 rounded-xl border border-slate-700 w-[90vw] max-w-5xl max-h-[90vh] overflow-hidden shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <div className="flex items-center gap-3 flex-wrap">
            {/* Symbol and Side */}
            <div className="flex items-center gap-2">
              {isLong ? (
                <TrendingUp className="w-6 h-6 text-green-400" />
              ) : (
                <TrendingDown className="w-6 h-6 text-red-400" />
              )}
              <span className="text-2xl font-bold text-white">{trade.symbol}</span>
              <span className={`px-3 py-1 rounded text-sm font-semibold ${
                isLong ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'
              }`}>
                {trade.side === 'Buy' ? 'LONG' : 'SHORT'}
              </span>
            </div>

            {/* Trade Type Badge - Paper vs Live */}
            <span className={`px-2 py-1 rounded text-xs font-medium flex items-center gap-1 ${
              trade.dry_run === 1 || trade.dry_run === undefined
                ? 'bg-yellow-900/50 text-yellow-400 border border-yellow-700/50'
                : 'bg-purple-900/50 text-purple-400 border border-purple-700/50'
            }`}>
              {trade.dry_run === 1 || trade.dry_run === undefined ? '📄 PAPER' : '💰 LIVE'}
            </span>

            {/* Status Badge */}
            <span className={`px-2 py-1 rounded text-xs font-medium ${
              trade.status === 'closed'
                ? pnl !== null && pnl >= 0 ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'
                : trade.status === 'rejected'
                  ? 'bg-red-900/50 text-red-400'
                  : trade.status === 'filled'
                    ? 'bg-blue-900/50 text-blue-400'
                    : trade.status === 'paper_trade' || trade.status === 'pending_fill'
                      ? 'bg-cyan-900/50 text-cyan-400'
                      : 'bg-slate-700 text-slate-400'
            }`}>
              {trade.status === 'closed' && trade.exit_reason
                ? trade.exit_reason === 'tp_hit' ? '✓ TP HIT' : '✗ SL HIT'
                : trade.status.toUpperCase().replace('_', ' ')}
            </span>

            {/* PnL for closed trades */}
            {isClosed && pnl !== null && (
              <span className={`px-3 py-1 rounded font-bold ${
                pnl >= 0 ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'
              }`}>
                {pnl >= 0 ? '+' : ''}{pnlPercent?.toFixed(2)}%
              </span>
            )}

            {/* Live indicator for chart mode */}
            {mode === 'live' && (
              <span className="flex items-center gap-1.5 bg-green-900/50 px-2 py-1 rounded text-xs text-green-400">
                <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
                LIVE
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500">{trade.timeframe || '1h'}</span>
            <button
              onClick={onClose}
              className="p-2 hover:bg-slate-700 rounded-lg transition-colors"
            >
              <X className="w-5 h-5 text-slate-400" />
            </button>
          </div>
        </div>

        {/* Rejection Reason Banner (if rejected) */}
        {trade.status === 'rejected' && trade.rejection_reason && (
          <div className="px-4 py-2 bg-red-900/30 border-b border-red-800/50">
            <span className="text-red-400 text-sm font-medium">Rejection Reason: </span>
            <span className="text-red-300 text-sm">{trade.rejection_reason}</span>
          </div>
        )}
        
        {/* Chart */}
        <div className="p-4 pb-2 relative">
          {/* Timezone indicator */}
          <div className="absolute top-6 right-6 text-xs text-slate-400 bg-slate-800/50 px-2 py-1 rounded">
            {Intl.DateTimeFormat().resolvedOptions().timeZone}
          </div>
          <TradeChart trade={trade} height={450} mode={mode} />
        </div>

        {/* Bottom Trade Info Cards */}
        <div className="grid grid-cols-4 gap-3 p-4 pt-2 border-t border-slate-700 bg-slate-900/30">
          {/* Entry Price */}
          <div className="bg-slate-800 border border-slate-600 rounded-lg p-3">
            <div className="text-xs text-slate-400 mb-1">Entry Price</div>
            <div className="text-xl font-bold text-white font-mono">${formatPrice(trade.entry_price)}</div>
            <div className="text-xs text-slate-500 mt-1">
              {trade.timeframe || '1h'} • {new Date(trade.created_at).toLocaleDateString()}
            </div>
          </div>

          {/* Stop Loss */}
          <div className="bg-slate-800 border border-red-900/50 rounded-lg p-3">
            <div className="text-xs text-slate-400 mb-1">Stop Loss</div>
            <div className="text-xl font-bold text-red-400 font-mono">${formatPrice(trade.stop_loss)}</div>
            <div className="text-xs text-red-400/70 mt-1">
              Risk: {riskPercent !== null ? `${riskPercent.toFixed(2)}%` : '—'}
            </div>
          </div>

          {/* Take Profit */}
          <div className="bg-slate-800 border border-green-900/50 rounded-lg p-3">
            <div className="text-xs text-slate-400 mb-1">Take Profit</div>
            <div className="text-xl font-bold text-green-400 font-mono">${formatPrice(trade.take_profit)}</div>
            <div className="text-xs text-green-400/70 mt-1">
              Reward: {rewardPercent !== null ? `${rewardPercent.toFixed(2)}%` : '—'}
            </div>
          </div>

          {/* RR Ratio & Exit Info */}
          <div className="bg-slate-800 border border-slate-600 rounded-lg p-3">
            <div className="text-xs text-slate-400 mb-1">R:R Ratio</div>
            <div className={`text-xl font-bold font-mono ${
              rrRatio !== null
                ? rrRatio >= 2 ? 'text-green-400' : rrRatio >= 1.5 ? 'text-yellow-400' : 'text-red-400'
                : 'text-slate-400'
            }`}>
              {rrRatio !== null ? rrRatio.toFixed(2) : '—'}
            </div>
            {trade.exit_price && (
              <div className="text-xs text-yellow-400/70 mt-1">
                Exit: ${formatPrice(trade.exit_price)}
              </div>
            )}
          </div>
        </div>

        {/* Timestamp Row */}
        <div className="grid grid-cols-4 gap-3 p-4 pt-2 bg-slate-900/30">
          {/* Entry Date/Time */}
          <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-3">
            <div className="text-xs text-slate-400 mb-1">Entry Date/Time</div>
            <div className="text-xs text-slate-300 font-mono">{new Date(trade.created_at).toISOString().replace('T', ' ').slice(0, 19)}</div>
          </div>

          {/* Entry to Fill Bars */}
          <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-3">
            <div className="text-xs text-slate-400 mb-1">Entry to Fill</div>
            <div className="text-xs text-slate-300 font-mono">
              {trade.filled_at ? `${Math.round((new Date(trade.filled_at).getTime() - new Date(trade.created_at).getTime()) / (1000 * 60 * (trade.timeframe === '1h' ? 60 : trade.timeframe === '2h' ? 120 : trade.timeframe === '4h' ? 240 : 60)))} bars` : '—'}
            </div>
          </div>

          {/* Filled Date/Time */}
          <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-3">
            <div className="text-xs text-slate-400 mb-1">Filled Date/Time</div>
            <div className="text-xs text-slate-300 font-mono">{trade.filled_at ? new Date(trade.filled_at).toISOString().replace('T', ' ').slice(0, 19) : '—'}</div>
          </div>

          {/* Fill to Close Bars */}
          <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-3">
            <div className="text-xs text-slate-400 mb-1">Fill to Close</div>
            <div className="text-xs text-slate-300 font-mono">
              {trade.filled_at && trade.closed_at ? `${Math.round((new Date(trade.closed_at).getTime() - new Date(trade.filled_at).getTime()) / (1000 * 60 * (trade.timeframe === '1h' ? 60 : trade.timeframe === '2h' ? 120 : trade.timeframe === '4h' ? 240 : 60)))} bars` : '—'}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

