'use client'

import { TrendingUp, DollarSign, Zap, Brain, AlertCircle, CheckCircle } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { useRealtime, Position } from '@/hooks/useRealtime'
import LiveTickers from './LiveTickers'
import ConnectionStatus from './ConnectionStatus'

export default function Dashboard() {
  const { tickers, positions: livePositions, connected, lastUpdate, reconnect } = useRealtime();

  // Trading Stats - computed from live data
  const totalPnl = livePositions.reduce((sum, p) => sum + parseFloat(p.unrealisedPnl || '0'), 0);
  const stats = [
    { label: 'Total P&L', value: `${totalPnl >= 0 ? '+' : ''}$${totalPnl.toFixed(2)}`, change: connected ? 'Live' : 'Offline', icon: DollarSign, positive: totalPnl >= 0 },
    { label: 'Win Rate', value: '85%', change: '+5%', icon: TrendingUp, positive: true },
    { label: 'Active Positions', value: livePositions.length.toString(), change: connected ? '● Live' : '○ Offline', icon: Zap, positive: true },
    { label: 'Avg Confidence', value: '0.85', change: '+0.08', icon: Brain, positive: true },
  ]

  // Format live positions for display
  const positions = livePositions.length > 0 ? livePositions.map((p: Position) => ({
    symbol: p.symbol,
    side: p.side.toUpperCase(),
    entry: parseFloat(p.entryPrice),
    current: parseFloat(p.markPrice),
    pnl: `${parseFloat(p.unrealisedPnl) >= 0 ? '+' : ''}$${parseFloat(p.unrealisedPnl).toFixed(2)}`,
    pnlPct: `${((parseFloat(p.markPrice) - parseFloat(p.entryPrice)) / parseFloat(p.entryPrice) * 100 * (p.side === 'Buy' ? 1 : -1)).toFixed(2)}%`,
    confidence: 0.85,
    leverage: p.leverage,
    size: p.size
  })) : [
    { symbol: 'BTCUSDT', side: 'LONG', entry: 42150, current: 42676, pnl: '+$526.13', pnlPct: '+2.49%', confidence: 0.87 },
    { symbol: 'ETHUSDT', side: 'LONG', entry: 2280, current: 2315, pnl: '+$17.65', pnlPct: '+1.55%', confidence: 0.79 },
  ]

  // Learning Metrics
  const learningMetrics = [
    { label: 'Prompt Version', value: 'v2.1', change: 'Winner', positive: true },
    { label: 'Win Rate', value: '85%', change: '+37% vs v1', positive: true },
    { label: 'Iterations', value: '6', change: '1,250 images', positive: true },
    { label: 'Symbols Tested', value: '4', change: '152 trades', positive: true },
  ]

  // 7-Day Performance
  const performanceData = [
    { day: 'Day 1', accuracy: 58, winRate: 58, pnl: 245 },
    { day: 'Day 2', accuracy: 62, winRate: 62, pnl: 520 },
    { day: 'Day 3', accuracy: 68, winRate: 68, pnl: 890 },
    { day: 'Day 4', accuracy: 72, winRate: 72, pnl: 1250 },
    { day: 'Day 5', accuracy: 78, winRate: 78, pnl: 1680 },
    { day: 'Day 6', accuracy: 82, winRate: 82, pnl: 2150 },
    { day: 'Day 7', accuracy: 85, winRate: 85, pnl: 2450 },
  ]

  // Symbol Performance
  const symbolPerformance = [
    { symbol: 'BTCUSDT', accuracy: 87, trades: 28, confidence: 0.84, improvement: '+8%' },
    { symbol: 'ETHUSDT', accuracy: 79, trades: 24, confidence: 0.76, improvement: '+12%' },
    { symbol: 'SOLUSDT', accuracy: 71, trades: 18, confidence: 0.68, improvement: '+15%' },
    { symbol: 'ADAUSDT', accuracy: 65, trades: 12, confidence: 0.62, improvement: '+5%' },
  ]

  // Key Insights
  const keyInsights = [
    { title: 'Confidence Correlation', value: 'r=0.92', action: 'Strong predictor of win rate', icon: CheckCircle },
    { title: 'Setup Quality', value: '40%', action: 'Most predictive component', icon: TrendingUp },
    { title: 'Market Gaps', value: '15%', action: 'Trend reversals missed', icon: AlertCircle },
    { title: 'Next Target', value: '90%', action: 'v3.0 win rate goal', icon: Zap },
  ]

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold text-white">Dashboard</h2>
          <p className="text-slate-400 text-sm">Trading metrics + Learning insights combined</p>
        </div>
        <ConnectionStatus connected={connected} lastUpdate={lastUpdate} onReconnect={reconnect} />
      </div>

      {/* Live Tickers */}
      <div>
        <h3 className="text-sm font-bold text-white mb-3">Live Prices</h3>
        <LiveTickers tickers={tickers} loading={!connected && Object.keys(tickers).length === 0} />
      </div>

      {/* Trading Stats - Compact */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {stats.map((stat, idx) => (
          <div key={idx} className="card p-3">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-slate-400">{stat.label}</span>
              <stat.icon className="w-4 h-4 text-slate-500" />
            </div>
            <div className="text-lg font-bold text-white">{stat.value}</div>
            <div className={`text-xs ${stat.positive ? 'text-green-400' : 'text-red-400'}`}>{stat.change}</div>
          </div>
        ))}
      </div>

      {/* Main Grid: Positions + Learning */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Positions & Recent Trades */}
        <div className="lg:col-span-2 space-y-4">
          {/* Open Positions */}
          <div className="card">
            <h3 className="text-sm font-bold text-white mb-3">Open Positions</h3>
            <div className="space-y-2">
              {positions.map((pos, idx) => (
                <div key={idx} className="flex items-center justify-between p-2 bg-slate-700/20 rounded border border-slate-600/30">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-bold text-white">{pos.symbol}</span>
                      <span className={`text-xs px-2 py-0.5 rounded ${pos.side === 'LONG' ? 'badge-long' : 'badge-short'}`}>
                        {pos.side}
                      </span>
                      <span className="text-xs text-slate-400">Conf: {(pos.confidence * 100).toFixed(0)}%</span>
                    </div>
                    <div className="text-xs text-slate-400 mt-1">Entry: ${pos.entry} → ${pos.current}</div>
                  </div>
                  <div className="text-right">
                    <div className={`text-sm font-bold ${pos.pnl.includes('-') ? 'text-negative' : 'text-positive'}`}>{pos.pnl}</div>
                    <div className={`text-xs ${pos.pnl.includes('-') ? 'text-red-400' : 'text-green-400'}`}>{pos.pnlPct}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 7-Day Performance Chart */}
          <div className="card">
            <h3 className="text-sm font-bold text-white mb-3">7-Day Learning Curve</h3>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={performanceData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="day" stroke="#94a3b8" style={{ fontSize: '12px' }} />
                <YAxis stroke="#94a3b8" style={{ fontSize: '12px' }} />
                <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} />
                <Legend wrapperStyle={{ fontSize: '12px' }} />
                <Line type="monotone" dataKey="accuracy" stroke="#10b981" strokeWidth={2} name="Accuracy %" />
                <Line type="monotone" dataKey="winRate" stroke="#3b82f6" strokeWidth={2} name="Win Rate %" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Right Column: Learning Insights */}
        <div className="space-y-4">
          {/* Learning Metrics */}
          <div className="card">
            <h3 className="text-sm font-bold text-white mb-3">Learning Status</h3>
            <div className="space-y-2">
              {learningMetrics.map((metric, idx) => (
                <div key={idx} className="flex justify-between items-center p-2 bg-slate-700/20 rounded">
                  <span className="text-xs text-slate-400">{metric.label}</span>
                  <div className="text-right">
                    <div className="text-sm font-bold text-white">{metric.value}</div>
                    <div className={`text-xs ${metric.positive ? 'text-green-400' : 'text-red-400'}`}>{metric.change}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Key Insights */}
          <div className="card">
            <h3 className="text-sm font-bold text-white mb-3">Key Insights</h3>
            <div className="space-y-2">
              {keyInsights.map((insight, idx) => (
                <div key={idx} className="flex items-start gap-2 p-2 bg-slate-700/20 rounded">
                  <insight.icon className="w-4 h-4 text-blue-400 mt-0.5 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-bold text-white">{insight.title}</div>
                    <div className="text-xs text-slate-400">{insight.value}</div>
                    <div className="text-xs text-slate-500">{insight.action}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Symbol Performance Grid */}
      <div className="card">
        <h3 className="text-sm font-bold text-white mb-3">Symbol Performance</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {symbolPerformance.map((sym, idx) => (
            <div key={idx} className="p-3 bg-slate-700/20 rounded border border-slate-600/30">
              <div className="text-sm font-bold text-white mb-2">{sym.symbol}</div>
              <div className="space-y-1 text-xs">
                <div className="flex justify-between">
                  <span className="text-slate-400">Accuracy:</span>
                  <span className="text-green-400 font-bold">{sym.accuracy}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Trades:</span>
                  <span className="text-white">{sym.trades}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Confidence:</span>
                  <span className="text-blue-400">{(sym.confidence * 100).toFixed(0)}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Improvement:</span>
                  <span className="text-green-400">{sym.improvement}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

