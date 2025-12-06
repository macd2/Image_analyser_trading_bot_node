'use client'

import { useState, useEffect } from 'react'
import { Camera, Clock, CheckCircle, AlertCircle, RefreshCw, Loader2 } from 'lucide-react'
import { useSourcerStatus } from '@/hooks/useBotData'

function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
}

function formatTimestamp(isoString: string): string {
  const date = new Date(isoString)
  return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
}

export default function CaptureView() {
  const { data, loading, error, refetch } = useSourcerStatus(5000)
  const [countdown, setCountdown] = useState<number>(0)

  // Real-time countdown
  useEffect(() => {
    if (data?.next_capture?.seconds_remaining) {
      setCountdown(data.next_capture.seconds_remaining)
    }
  }, [data?.next_capture?.seconds_remaining])

  useEffect(() => {
    const timer = setInterval(() => {
      setCountdown(prev => Math.max(0, prev - 1))
    }, 1000)
    return () => clearInterval(timer)
  }, [])

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
          Error loading capture data: {error}
          <button onClick={refetch} className="ml-4 text-blue-400 hover:underline">Retry</button>
        </div>
      </div>
    )
  }

  const watchlist = data?.watchlist || []
  const recentCaptures = data?.recent_captures || []
  const stats = data?.stats || { captured_today: 0, failed_today: 0, symbols_count: 0 }
  const timeframe = data?.timeframe || '1h'
  const currentCycle = data?.current_cycle

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white flex items-center gap-2">
            <Camera className="text-blue-400" /> Chart Capture
          </h2>
          <p className="text-slate-400 text-sm">TradingView chart sourcer</p>
        </div>
        <div className="flex items-center gap-4">
          <button onClick={refetch} className="text-slate-400 hover:text-white">
            <RefreshCw size={16} />
          </button>
          <div className="flex items-center gap-2 text-sm">
            <Clock size={16} className="text-slate-400" />
            <span className="text-slate-300">Next capture:
              <span className={`font-mono ml-1 ${countdown < 60 ? 'text-yellow-400' : 'text-blue-400'}`}>
                {formatTime(countdown)}
              </span>
            </span>
          </div>
        </div>
      </div>

      {/* Capture Stats */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'Symbols', value: stats.symbols_count, color: 'text-blue-400' },
          { label: 'Timeframe', value: timeframe, color: 'text-purple-400' },
          { label: 'Captured Today', value: stats.captured_today, color: 'text-green-400' },
          { label: 'Failed', value: stats.failed_today, color: 'text-red-400' },
        ].map((stat, i) => (
          <div key={i} className="bg-slate-800 rounded-lg p-4 text-center">
            <div className={`text-2xl font-bold ${stat.color}`}>{stat.value}</div>
            <div className="text-xs text-slate-400">{stat.label}</div>
          </div>
        ))}
      </div>

      {/* Current Cycle */}
      <div className="bg-slate-800 rounded-lg p-4">
        <h3 className="text-white font-semibold mb-3 flex items-center gap-2">
          Current Cycle
          {currentCycle?.status === 'running' && (
            <span className="text-xs bg-blue-600 px-2 py-0.5 rounded animate-pulse">Running</span>
          )}
          {currentCycle?.status === 'completed' && (
            <span className="text-xs bg-green-600 px-2 py-0.5 rounded">Completed</span>
          )}
        </h3>
        {recentCaptures.length === 0 ? (
          <div className="text-slate-500 text-center py-4">No recent captures</div>
        ) : (
          <div className="space-y-2">
            {recentCaptures.slice(0, 6).map((chart, i) => (
              <div key={i} className="flex items-center justify-between bg-slate-700 rounded p-3">
                <div className="flex items-center gap-3">
                  {chart.status === 'success' ? (
                    <CheckCircle size={16} className="text-green-400" />
                  ) : (
                    <AlertCircle size={16} className="text-red-400" />
                  )}
                  <span className="text-white font-mono">{chart.symbol}</span>
                  <span className="text-slate-400 text-sm">{chart.timeframe}</span>
                </div>
                <div className="flex items-center gap-4 text-sm">
                  <span className="text-slate-400">{formatTimestamp(chart.timestamp)}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Watchlist */}
      <div className="bg-slate-800 rounded-lg p-4">
        <h3 className="text-white font-semibold mb-3">Watchlist ({watchlist.length} symbols)</h3>
        {watchlist.length === 0 ? (
          <div className="text-slate-500">No symbols in watchlist</div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {watchlist.map((symbol) => (
              <span key={symbol} className="bg-slate-700 text-slate-300 px-3 py-1 rounded text-sm font-mono">
                {symbol}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Latest Capture Preview */}
      <div className="bg-slate-800 rounded-lg p-4">
        <h3 className="text-white font-semibold mb-3">Latest Capture</h3>
        <div className="bg-slate-900 rounded-lg h-48 flex items-center justify-center border border-slate-700">
          {recentCaptures[0] ? (
            <div className="text-center text-slate-400">
              <Camera size={48} className="mx-auto mb-2 opacity-50" />
              <p className="text-white font-mono">{recentCaptures[0].symbol} {recentCaptures[0].timeframe}</p>
              <p className="text-xs">{formatTimestamp(recentCaptures[0].timestamp)}</p>
              {recentCaptures[0].chart_path && (
                <p className="text-xs text-slate-500 mt-1 truncate max-w-xs">{recentCaptures[0].chart_path}</p>
              )}
            </div>
          ) : (
            <div className="text-center text-slate-500">
              <Camera size={48} className="mx-auto mb-2 opacity-50" />
              <p>No captures yet</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

