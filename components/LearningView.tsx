'use client'

import { useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { GraduationCap, TrendingUp, Zap, Target, RefreshCw, AlertCircle, Database, Loader2 } from 'lucide-react'
import { useLearning } from '@/hooks/useLearning'
import PromptLeaderboard from './PromptLeaderboard'

export default function LearningView() {
  const { data, summary, loading, error, refresh } = useLearning();
  const [refreshLoading, setRefreshLoading] = useState(false);
  const [compareLoading, setCompareLoading] = useState(false);
  const [deployLoading, setDeployLoading] = useState(false);

  // Loading state
  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center h-64">
        <RefreshCw className="animate-spin text-blue-400 mr-2" />
        <span className="text-slate-400">Loading learning data...</span>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="p-6">
        <div className="bg-red-900/30 border border-red-500 rounded-lg p-4 flex items-start gap-3">
          <AlertCircle className="text-red-400 mt-0.5" />
          <div>
            <h3 className="text-red-400 font-semibold">Database Error</h3>
            <p className="text-slate-400 text-sm mt-1">{error}</p>
            <button
              onClick={async () => {
                setRefreshLoading(true)
                try {
                  await refresh()
                } finally {
                  setRefreshLoading(false)
                }
              }}
              disabled={refreshLoading}
              className="mt-3 text-sm bg-red-600 hover:bg-red-700 text-white px-3 py-1 rounded flex items-center gap-1"
            >
              {refreshLoading ? (
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
      </div>
    );
  }

  // No data state
  if (!data || !summary || data.prompts.length === 0) {
    return (
      <div className="p-6">
        <div className="bg-slate-800 border border-slate-600 rounded-lg p-6 text-center">
          <Database className="mx-auto text-slate-500 mb-3" size={48} />
          <h3 className="text-white font-semibold">No Backtest Data</h3>
          <p className="text-slate-400 text-sm mt-1">Run some backtests to see learning insights</p>
        </div>
      </div>
    );
  }

  // Transform data for charts
  const symbolChartData = data.symbols.slice(0, 6).map(s => ({
    symbol: s.symbol.replace('USDT', ''),
    accuracy: s.win_rate,
    trades: s.total_trades,
  }));

  const promptChartData = data.prompts.map((p) => ({
    name: p.prompt_name.length > 15 ? p.prompt_name.slice(0, 15) + '...' : p.prompt_name,
    winRate: p.win_rate,
    trades: p.total_trades,
  }));

  // Best prompt = highest avg_pnl with min 10 trades and 2 symbols
  const bestPrompt = data.prompts
    .filter(p => p.total_trades >= 10 && (p.symbol_count || 0) >= 2)
    .sort((a, b) => b.avg_pnl_pct - a.avg_pnl_pct)[0] || data.prompts[0];

  return (
    <div className="p-6 space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold text-white flex items-center gap-2">
            <GraduationCap className="text-green-400" /> Learning System
          </h2>
          <p className="text-slate-400 text-sm">Prompt optimization through backtesting</p>
        </div>
        <button
          onClick={async () => {
            setRefreshLoading(true)
            try {
              await refresh()
            } finally {
              setRefreshLoading(false)
            }
          }}
          disabled={refreshLoading}
          className="text-slate-400 hover:text-white p-2"
        >
          <RefreshCw size={18} className={refreshLoading ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* Summary Stats from DB */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'Total Trades', value: summary.totalTrades.toString(), color: 'text-blue-400' },
          { label: 'Win Rate', value: `${summary.overallWinRate}%`, color: summary.overallWinRate >= 50 ? 'text-green-400' : 'text-red-400' },
          { label: 'Total PnL', value: `${summary.totalPnl >= 0 ? '+' : ''}${summary.totalPnl.toFixed(1)}%`, color: summary.totalPnl >= 0 ? 'text-green-400' : 'text-red-400' },
          { label: 'Prompts Tested', value: summary.uniquePrompts.toString(), color: 'text-purple-400' },
        ].map((stat, i) => (
          <div key={i} className="bg-slate-800 rounded-lg p-4 text-center">
            <div className={`text-2xl font-bold ${stat.color}`}>{stat.value}</div>
            <div className="text-xs text-slate-400">{stat.label}</div>
          </div>
        ))}
      </div>

      {/* Enhanced Prompt Leaderboard */}
      <PromptLeaderboard prompts={data.prompts} />

      {/* Charts Row */}
      <div className="grid grid-cols-2 gap-4">
        {/* Prompt Win Rate Chart */}
        <div className="bg-slate-800 rounded-lg p-4">
          <h3 className="text-white font-semibold mb-3">Prompt Win Rates</h3>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={promptChartData} layout="vertical">
              <XAxis type="number" stroke="#94a3b8" domain={[0, 100]} />
              <YAxis type="category" dataKey="name" stroke="#94a3b8" width={100} tick={{ fontSize: 11 }} />
              <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} />
              <Bar dataKey="winRate" fill="#10b981" name="Win Rate %" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Symbol Performance from DB */}
        <div className="bg-slate-800 rounded-lg p-4">
          <h3 className="text-white font-semibold mb-3">Symbol Performance</h3>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={symbolChartData}>
              <XAxis dataKey="symbol" stroke="#94a3b8" />
              <YAxis stroke="#94a3b8" domain={[0, 100]} />
              <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} />
              <Bar dataKey="accuracy" fill="#3b82f6" name="Win Rate %" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Insights from DB */}
      <div className="bg-slate-800 rounded-lg p-4">
        <h3 className="text-white font-semibold mb-3">Key Insights</h3>
        <div className="grid grid-cols-2 gap-3">
          {data.insights.map((ins, i) => (
            <div key={i} className={`rounded p-3 ${
              ins.type === 'positive' ? 'bg-green-900/30 border border-green-700' :
              ins.type === 'negative' ? 'bg-red-900/30 border border-red-700' :
              'bg-slate-700'
            }`}>
              <div className="flex justify-between items-center">
                <span className="text-white text-sm font-medium">{ins.title}</span>
                {ins.metric !== undefined && (
                  <span className={`text-xs ${ins.type === 'positive' ? 'text-green-400' : ins.type === 'negative' ? 'text-red-400' : 'text-slate-400'}`}>
                    {ins.metric.toFixed(1)}
                  </span>
                )}
              </div>
              <p className="text-slate-400 text-xs mt-1">{ins.description}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Actions */}
      <div className="bg-slate-800 rounded-lg p-4 border border-blue-500">
        <h3 className="text-white font-semibold mb-3 flex items-center gap-2">
          <Zap size={16} className="text-blue-400" /> Quick Actions
        </h3>
        <div className="flex gap-3">
          <button
            onClick={() => {
              setCompareLoading(true)
              // Simulate async operation
              setTimeout(() => setCompareLoading(false), 2000)
            }}
            disabled={compareLoading}
            className="flex items-center gap-2 bg-slate-700 hover:bg-slate-600 text-white px-4 py-2 rounded text-sm disabled:opacity-50"
          >
            {compareLoading ? (
              <>
                <Loader2 className="animate-spin h-4 w-4" />
                Comparing...
              </>
            ) : (
              <>
                <Target size={14} /> Compare Prompts
              </>
            )}
          </button>
          <button
            onClick={() => {
              setDeployLoading(true)
              // Simulate async operation
              setTimeout(() => setDeployLoading(false), 2000)
            }}
            disabled={deployLoading}
            className="flex items-center gap-2 bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded text-sm disabled:opacity-50"
          >
            {deployLoading ? (
              <>
                <Loader2 className="animate-spin h-4 w-4" />
                Deploying...
              </>
            ) : (
              <>
                <TrendingUp size={14} /> Deploy Best: {bestPrompt?.prompt_name.slice(0, 20)}
              </>
            )}
          </button>
        </div>
      </div>

      {/* Last Updated */}
      <p className="text-slate-500 text-xs text-right">
        Last updated: {new Date(data.lastUpdated).toLocaleString()}
      </p>
    </div>
  );
}

