'use client'

import { useState } from 'react'
import { useRealtime } from '@/hooks/useRealtime'
import ConnectionStatus from './ConnectionStatus'
import SystemHealth from './dashboard/SystemHealth'
import StrategyPerformance from './dashboard/StrategyPerformance'
import SymbolPerformance from './dashboard/SymbolPerformance'
import PositionManagement from './dashboard/PositionManagement'
import CorrelationAnalysis from './dashboard/CorrelationAnalysis'
import PerformanceTrends from './dashboard/PerformanceTrends'
import AIInsights from './dashboard/AIInsights'
import DashboardFilters from './dashboard/DashboardFilters'

export default function Dashboard() {
  const { connected, lastUpdate, reconnect } = useRealtime()
  const [activeTab, setActiveTab] = useState<'overview' | 'strategy' | 'symbol' | 'position' | 'correlation' | 'trends' | 'insights'>('overview')

  const tabs = [
    { id: 'overview', label: 'System Health', icon: '📊' },
    { id: 'strategy', label: 'Strategy Performance', icon: '📈' },
    { id: 'symbol', label: 'Symbol Performance', icon: '💹' },
    { id: 'position', label: 'Position Management', icon: '📍' },
    { id: 'correlation', label: 'Correlation Analysis', icon: '🔗' },
    { id: 'trends', label: 'Performance Trends', icon: '📉' },
    { id: 'insights', label: 'AI Insights', icon: '🤖' },
  ]

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold text-white">Trading Dashboard v2.0</h2>
          <p className="text-slate-400 text-sm">Advanced analytics with strategy-timeframe performance tracking</p>
        </div>
        <ConnectionStatus connected={connected} lastUpdate={lastUpdate} onReconnect={reconnect} />
      </div>

      {/* Filters */}
      <DashboardFilters onFilterChange={() => {}} />

      {/* Tab Navigation */}
      <div className="flex gap-2 overflow-x-auto pb-2 border-b border-slate-700">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            className={`px-4 py-2 text-sm font-medium whitespace-nowrap transition ${
              activeTab === tab.id
                ? 'text-white border-b-2 border-blue-500'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            {tab.icon} {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="space-y-6">
        {activeTab === 'overview' && <SystemHealth />}
        {activeTab === 'strategy' && <StrategyPerformance />}
        {activeTab === 'symbol' && <SymbolPerformance />}
        {activeTab === 'position' && <PositionManagement />}
        {activeTab === 'correlation' && <CorrelationAnalysis />}
        {activeTab === 'trends' && <PerformanceTrends />}
        {activeTab === 'insights' && <AIInsights />}
      </div>


    </div>
  )
}

