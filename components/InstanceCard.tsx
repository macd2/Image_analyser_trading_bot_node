'use client'

import { useState } from 'react'
import { Play, StopCircle, Skull, ChevronRight, RefreshCw, Terminal } from 'lucide-react'
import Link from 'next/link'

export interface InstanceCardData {
  id: string
  name: string
  prompt_name: string | null
  is_running: boolean
  current_run_id: string | null
  total_trades: number
  live_trades: number
  dry_run_trades: number
  total_pnl: number
  win_rate: number
  config: {
    use_testnet: boolean
    paper_trading: boolean
  }
  recent_logs?: string[]
}

interface InstanceCardProps {
  instance: InstanceCardData
  onAction?: (instanceId: string, action: 'start' | 'stop' | 'kill') => Promise<void>
}

export default function InstanceCard({ instance, onAction }: InstanceCardProps) {
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  const handleAction = async (action: 'start' | 'stop' | 'kill') => {
    if (!onAction) return
    setActionLoading(action)
    try {
      await onAction(instance.id, action)
    } finally {
      setActionLoading(null)
    }
  }

  const isRunning = instance.is_running

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 hover:border-slate-600 transition overflow-hidden">
      {/* Header */}
      <Link href={`/bot/${instance.id}`} className="block">
        <div className="p-4 border-b border-slate-700 hover:bg-slate-700/50 transition cursor-pointer">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <h3 className="font-semibold text-white text-lg">{instance.name}</h3>
              {isRunning ? (
                <span className="px-2 py-0.5 text-xs font-medium bg-green-600/20 text-green-400 rounded-full flex items-center gap-1">
                  <span className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse"></span>
                  Running
                </span>
              ) : (
                <span className="px-2 py-0.5 text-xs font-medium bg-slate-600/30 text-slate-400 rounded-full">
                  Stopped
                </span>
              )}
            </div>
            <ChevronRight className="w-5 h-5 text-slate-500" />
          </div>
          <p className="text-sm text-blue-400 mt-1 truncate">
            {instance.prompt_name || 'No prompt set'}
          </p>
          <div className="flex items-center gap-2 mt-2 text-xs">
            <span className={`px-1.5 py-0.5 rounded ${instance.config.use_testnet ? 'bg-blue-600/20 text-blue-400' : 'bg-purple-600/20 text-purple-400'}`}>
              {instance.config.use_testnet ? 'Testnet' : 'Mainnet'}
            </span>
            <span className={`px-1.5 py-0.5 rounded ${instance.config.paper_trading ? 'bg-amber-600/20 text-amber-400' : 'bg-red-600/20 text-red-400'}`}>
              {instance.config.paper_trading ? 'Dry Run' : 'Hot'}
            </span>
          </div>
        </div>
      </Link>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-px bg-slate-700">
        <div className="bg-slate-800 p-3 text-center">
          <div className="text-xs text-slate-400 mb-1">Trades</div>
          <div className="text-lg font-semibold text-white">{instance.total_trades}</div>
          <div className="text-[10px] text-slate-500 mt-0.5">
            {instance.live_trades > 0 && <span className="text-red-400">{instance.live_trades} live</span>}
            {instance.live_trades > 0 && instance.dry_run_trades > 0 && <span className="mx-1">•</span>}
            {instance.dry_run_trades > 0 && <span className="text-amber-400">{instance.dry_run_trades} dry</span>}
          </div>
        </div>
        <div className="bg-slate-800 p-3 text-center">
          <div className="text-xs text-slate-400 mb-1">Win Rate</div>
          <div className="text-lg font-semibold text-white">{instance.win_rate.toFixed(0)}%</div>
          <div className="text-[10px] text-slate-500 mt-0.5">live only</div>
        </div>
        <div className="bg-slate-800 p-3 text-center">
          <div className="text-xs text-slate-400 mb-1">P&L</div>
          <div className={`text-lg font-semibold ${instance.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            ${instance.total_pnl.toFixed(2)}
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">live only</div>
        </div>
      </div>

      {/* Recent Logs */}
      {instance.recent_logs && instance.recent_logs.length > 0 && (
        <div className="p-3 bg-slate-900/50 border-t border-slate-700">
          <div className="flex items-center gap-1.5 text-xs text-slate-500 mb-2">
            <Terminal className="w-3 h-3" />
            <span>Recent Activity</span>
          </div>
          <div className="space-y-1 font-mono text-[10px] text-slate-400 max-h-16 overflow-hidden">
            {instance.recent_logs.slice(0, 3).map((log, i) => (
              <div key={i} className="truncate">{log}</div>
            ))}
          </div>
        </div>
      )}

      {/* Actions - Always show all buttons */}
      <div className="p-3 border-t border-slate-700 flex items-center gap-2">
        <button
          onClick={(e) => {
            e.preventDefault()
            e.stopPropagation()
            handleAction('start')
          }}
          disabled={actionLoading !== null || isRunning}
          className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 text-white text-sm font-medium rounded-lg transition disabled:opacity-50 ${
            instance.config.paper_trading
              ? 'bg-amber-600 hover:bg-amber-700'
              : 'bg-green-600 hover:bg-green-700'
          }`}
        >
          {isRunning || actionLoading === 'start' ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
          {isRunning ? 'Running' : (instance.config.paper_trading ? 'Dry' : 'Live')}
        </button>
        <button
          onClick={(e) => {
            e.preventDefault()
            e.stopPropagation()
            handleAction('stop')
          }}
          disabled={actionLoading !== null || !isRunning}
          className="flex-1 flex items-center justify-center gap-2 px-3 py-2 bg-amber-600 hover:bg-amber-700 text-white text-sm font-medium rounded-lg transition disabled:opacity-50"
        >
          {actionLoading === 'stop' ? <RefreshCw className="w-4 h-4 animate-spin" /> : <StopCircle className="w-4 h-4" />}
          Stop
        </button>
        <button
          onClick={(e) => {
            e.preventDefault()
            e.stopPropagation()
            if (confirm('⚠️ KILL SWITCH: Immediately terminate this instance?')) {
              handleAction('kill')
            }
          }}
          disabled={actionLoading !== null || !isRunning}
          className="flex items-center justify-center gap-2 px-3 py-2 bg-red-700 hover:bg-red-800 text-white text-sm font-medium rounded-lg transition disabled:opacity-50"
        >
          {actionLoading === 'kill' ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Skull className="w-4 h-4" />}
        </button>
      </div>
    </div>
  )
}

