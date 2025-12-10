'use client'

import { useState } from 'react'
import { Brain, TrendingUp, TrendingDown, Minus, CheckCircle, AlertCircle, Image, RefreshCw, Loader2 } from 'lucide-react'
import { useCyclesData } from '@/hooks/useBotData'

function formatPrice(price: number | null): string {
  if (price === null) return '-'
  if (price >= 1000) return `$${price.toLocaleString()}`
  if (price >= 1) return `$${price.toFixed(2)}`
  return `$${price.toFixed(4)}`
}

export default function AnalysisView() {
  const { data, loading, error, refetch } = useCyclesData(10000)
  const [retryLoading, setRetryLoading] = useState(false)
  const [refreshLoading, setRefreshLoading] = useState(false)

  if (loading && !data) {
    return (
      <div className="p-6 flex items-center justify-center h-64">
        <Loader2 className="animate-spin text-blue-400" size={32} />
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="bg-red-900/30 border border-red-500 rounded-lg p-4 text-red-300">
          Error loading analysis data: {error}
          <button
            onClick={async () => {
              setRetryLoading(true)
              try {
                await refetch()
              } finally {
                setRetryLoading(false)
              }
            }}
            disabled={retryLoading}
            className="ml-4 text-blue-400 hover:underline flex items-center gap-1"
          >
            {retryLoading ? (
              <>
                <Loader2 className="animate-spin h-3 w-3" />
                Retrying...
              </>
            ) : (
              'Retry'
            )}
          </button>
        </div>
      </div>
    )
  }

  const analysisResults = data?.current_cycle_analysis || []
  const promptInfo = data?.prompt_info || { name: 'unknown', model: 'unknown', avg_confidence: 0 }
  const stats = data?.stats || { images_analyzed: 0, valid_signals: 0, actionable_pct: 0 }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white flex items-center gap-2">
            <Brain className="text-blue-400" /> AI Analysis
          </h2>
          <p className="text-slate-400 text-sm">Chart analyzer with confidence scoring</p>
        </div>
        <div className="flex items-center gap-4">
          <button
            onClick={async () => {
              setRefreshLoading(true)
              try {
                await refetch()
              } finally {
                setRefreshLoading(false)
              }
            }}
            disabled={refreshLoading}
            className="text-slate-400 hover:text-white"
          >
            <RefreshCw size={16} className={refreshLoading ? 'animate-spin' : ''} />
          </button>
          <div className="bg-slate-800 rounded-lg px-4 py-2 text-sm">
            <span className="text-slate-400">Prompt: </span>
            <span className="text-blue-400 font-mono">{promptInfo.name}</span>
            <span className="text-slate-500 ml-2">| {promptInfo.model}</span>
          </div>
        </div>
      </div>

      {/* Analysis Stats */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'Images Analyzed', value: stats.images_analyzed, color: 'text-blue-400' },
          { label: 'Valid Signals', value: stats.valid_signals, color: 'text-green-400' },
          { label: 'Avg Confidence', value: promptInfo.avg_confidence.toFixed(2), color: 'text-purple-400' },
          { label: 'Actionable', value: `${stats.actionable_pct}%`, color: 'text-yellow-400' },
        ].map((stat, i) => (
          <div key={i} className="bg-slate-800 rounded-lg p-4 text-center">
            <div className={`text-2xl font-bold ${stat.color}`}>{stat.value}</div>
            <div className="text-xs text-slate-400">{stat.label}</div>
          </div>
        ))}
      </div>

      {/* Analysis Results */}
      <div className="bg-slate-800 rounded-lg p-4">
        <h3 className="text-white font-semibold mb-3">Current Cycle Analysis</h3>
        {analysisResults.length === 0 ? (
          <div className="text-slate-500 text-center py-8">
            No analysis results for current cycle
          </div>
        ) : (
          <div className="space-y-3">
            {analysisResults.map((result, i) => (
              <div key={i} className={`bg-slate-700 rounded-lg p-4 border-l-4 ${
                result.status === 'valid' ? 'border-green-500' :
                result.status === 'low' ? 'border-yellow-500' : 'border-slate-500'
              }`}>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <Image size={16} className="text-slate-400" />
                    <span className="text-white font-mono">{result.symbol}</span>
                    <span className={`flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold ${
                      result.recommendation === 'LONG' ? 'bg-green-900 text-green-300' :
                      result.recommendation === 'SHORT' ? 'bg-red-900 text-red-300' :
                      'bg-slate-600 text-slate-300'
                    }`}>
                      {result.recommendation === 'LONG' && <TrendingUp size={12} />}
                      {result.recommendation === 'SHORT' && <TrendingDown size={12} />}
                      {result.recommendation === 'HOLD' && <Minus size={12} />}
                      {result.recommendation}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`text-lg font-bold ${
                      result.confidence >= 0.70 ? 'text-green-400' :
                      result.confidence >= 0.50 ? 'text-yellow-400' : 'text-red-400'
                    }`}>{(result.confidence * 100).toFixed(0)}%</span>
                    {result.status === 'valid' ? (
                      <CheckCircle size={16} className="text-green-400" />
                    ) : result.status === 'low' ? (
                      <AlertCircle size={16} className="text-yellow-400" />
                    ) : (
                      <Minus size={16} className="text-slate-400" />
                    )}
                  </div>
                </div>
                {result.entry_price && (
                  <div className="grid grid-cols-4 gap-4 text-sm mt-2 pt-2 border-t border-slate-600">
                    <div>
                      <span className="text-slate-400 text-xs">Entry</span>
                      <div className="text-white">{formatPrice(result.entry_price)}</div>
                    </div>
                    <div>
                      <span className="text-slate-400 text-xs">TP</span>
                      <div className="text-green-400">{formatPrice(result.take_profit)}</div>
                    </div>
                    <div>
                      <span className="text-slate-400 text-xs">SL</span>
                      <div className="text-red-400">{formatPrice(result.stop_loss)}</div>
                    </div>
                    <div>
                      <span className="text-slate-400 text-xs">Components</span>
                      <div className="text-slate-300 text-xs">
                        S:{(result.setup_quality * 100).toFixed(0)} R:{(result.rr_score * 100).toFixed(0)} M:{(result.market_score * 100).toFixed(0)}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Confidence Formula */}
      <div className="bg-slate-800 rounded-lg p-4">
        <h3 className="text-white font-semibold mb-3">Confidence Calculation</h3>
        <div className="bg-slate-700 rounded p-3 font-mono text-sm">
          <span className="text-blue-400">Confidence</span> =
          <span className="text-green-400"> (Setup × 0.40)</span> +
          <span className="text-yellow-400"> (R:R × 0.25)</span> +
          <span className="text-purple-400"> (Market × 0.35)</span>
        </div>
        <div className="grid grid-cols-3 gap-4 mt-3 text-center text-sm">
          <div className="bg-slate-700 rounded p-2">
            <div className="text-green-400 font-bold">40%</div>
            <div className="text-slate-400 text-xs">Setup Quality</div>
          </div>
          <div className="bg-slate-700 rounded p-2">
            <div className="text-yellow-400 font-bold">25%</div>
            <div className="text-slate-400 text-xs">Risk-Reward</div>
          </div>
          <div className="bg-slate-700 rounded p-2">
            <div className="text-purple-400 font-bold">35%</div>
            <div className="text-slate-400 text-xs">Market Env</div>
          </div>
        </div>
      </div>
    </div>
  )
}

