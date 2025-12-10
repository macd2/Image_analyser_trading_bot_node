'use client'

import { BarChart3, Camera, Brain, GraduationCap, Settings2, ChevronRight, Trophy, Bot, Activity, Monitor, Zap, Database, Cloud } from 'lucide-react'
import { useState, useEffect } from 'react'
import { usePathname } from 'next/navigation'
import Link from 'next/link'

interface InstanceStatus {
  runningCount: number
  totalCount: number
}

interface EnvConfig {
  db_type: 'sqlite' | 'postgres'
  storage_type: 'local' | 'supabase'
}

interface SimulatorStatus {
  running: boolean
  last_check: string | null
}

export default function Sidebar() {
  const pathname = usePathname()
  const [instanceStatus, setInstanceStatus] = useState<InstanceStatus>({ runningCount: 0, totalCount: 0 })
  const [envConfig, setEnvConfig] = useState<EnvConfig | null>(null)
  const [simulatorStatus, setSimulatorStatus] = useState<SimulatorStatus>({ running: false, last_check: null })

  // Poll instance status every 5 seconds
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await fetch('/api/bot/instances')
        if (res.ok) {
          const data = await res.json()
          const instances = data.instances || []
          const running = instances.filter((i: { is_running: number }) => i.is_running === 1).length
          setInstanceStatus({
            runningCount: running,
            totalCount: instances.length,
          })
        }
      } catch {
        // Ignore fetch errors
      }
    }

    fetchStatus()
    const interval = setInterval(fetchStatus, 5000)
    return () => clearInterval(interval)
  }, [])

  // Poll simulator status every 5 seconds
  useEffect(() => {
    const fetchSimulatorStatus = async () => {
      try {
        const res = await fetch('/api/bot/simulator/monitor')
        if (res.ok) {
          const data = await res.json()
          setSimulatorStatus({ running: data.running, last_check: data.last_check })
        }
      } catch {
        // Ignore fetch errors
      }
    }

    fetchSimulatorStatus()
    const interval = setInterval(fetchSimulatorStatus, 5000)
    return () => clearInterval(interval)
  }, [])

  // Fetch env config once on mount
  useEffect(() => {
    fetch('/api/config/env')
      .then(res => res.json())
      .then(data => setEnvConfig(data))
      .catch(() => {})
  }, [])

  const tabs = [
    { id: 'dashboard', href: '/', label: 'Dashboard', icon: BarChart3, desc: 'Overview' },
    { id: 'instances', href: '/instances', label: 'Instances', icon: Activity, desc: 'Instance View', showInstanceCount: true },
    { id: 'simulator', href: '/simulator', label: 'Simulator', icon: Zap, desc: 'Paper Trade Sim', showSimulatorStatus: true },
    { id: 'bot', href: '/bot', label: 'Bot Control', icon: Bot, desc: 'Start/Stop Bot' },
    { id: 'browser', href: '/browser', label: 'Browser View', icon: Monitor, desc: 'Live Debug' },
    { id: 'logs', href: '/logs', label: 'Log Trail', icon: Activity, desc: 'Audit Trail' },
    { id: 'capture', href: '/capture', label: '1. Capture', icon: Camera, desc: 'Chart Sourcer' },
    { id: 'analysis', href: '/analysis', label: '2. Analysis', icon: Brain, desc: 'AI Analyzer' },
    { id: 'learning', href: '/learning', label: '3. Learning', icon: GraduationCap, desc: 'Prompt Optimizer' },
    { id: 'advisor', href: '/advisor', label: 'Advisor', icon: Brain, desc: 'TA Advisor System' },
  ]

  const learningSubTabs = [
    { id: 'find-best-prompt', href: '/find-best-prompt', label: 'Find Best Prompt', icon: Trophy },
    { id: 'backtest', href: '/backtest', label: 'Run Backtest', icon: Settings2 },
  ]

  return (
    <aside className="w-56 bg-slate-900 border-r border-slate-700 p-4">
      <div className="mb-6">
        <h1 className="text-xl font-bold text-white">🤖 Trading Bot</h1>
        <p className="text-xs text-slate-400 mt-1">AI + Learning System</p>
      </div>

      <nav className="space-y-1">
        {tabs.map((tab) => {
          const Icon = tab.icon
          const isActive = pathname === tab.href || (tab.id === 'learning' && (pathname === '/backtest' || pathname === '/find-best-prompt'))
          const showInstanceCount = tab.showInstanceCount
          const showSimulatorStatus = 'showSimulatorStatus' in tab && tab.showSimulatorStatus
          return (
            <div key={tab.id}>
              <Link
                href={tab.href}
                className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg transition text-left ${
                  isActive ? 'bg-blue-600 text-white' : 'text-slate-300 hover:bg-slate-800'
                }`}
              >
                <Icon size={16} />
                <div className="flex-1">
                  <div className="text-sm font-medium flex items-center gap-1.5">
                    {tab.label}
                    {/* Simulator status indicator */}
                    {showSimulatorStatus && (
                      <span
                        className={`w-2 h-2 rounded-full ${
                          simulatorStatus.running
                            ? 'bg-green-500 animate-pulse'
                            : 'bg-slate-500'
                        }`}
                        title={simulatorStatus.running ? 'Auto-monitor running' : 'Auto-monitor stopped'}
                      />
                    )}
                    {/* Running instances count for Bot Control */}
                    {showInstanceCount && (
                      <span
                        className={`text-[10px] font-normal px-1.5 rounded ${
                          instanceStatus.runningCount > 0
                            ? 'bg-green-500/20 text-green-400'
                            : 'bg-slate-600/50 text-slate-400'
                        }`}
                      >
                        {instanceStatus.runningCount}/{instanceStatus.totalCount}
                      </span>
                    )}
                  </div>
                  <div className="text-xs opacity-60">{tab.desc}</div>
                </div>
              </Link>
              {/* Sub-menu for Learning */}
              {tab.id === 'learning' && (
                <div className="ml-4 mt-1 space-y-1">
                  {learningSubTabs.map((sub) => {
                    const SubIcon = sub.icon
                    return (
                      <Link
                        key={sub.id}
                        href={sub.href}
                        className={`w-full flex items-center gap-2 px-3 py-1.5 rounded transition text-left text-sm ${
                          pathname === sub.href
                            ? 'bg-slate-700 text-white'
                            : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
                        }`}
                      >
                        <ChevronRight size={12} className="text-slate-500" />
                        <SubIcon size={14} />
                        <span>{sub.label}</span>
                      </Link>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
      </nav>

      <div className="mt-6 pt-4 border-t border-slate-700">
        <div className="text-xs text-slate-400 space-y-1.5">
          <p className="flex items-center gap-1.5">
            Instances:{' '}
            {instanceStatus.runningCount > 0 ? (
              <span className="flex items-center gap-1 text-green-400">
                <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                {instanceStatus.runningCount} running
              </span>
            ) : (
              <span className="text-slate-500">
                {instanceStatus.totalCount} stopped
              </span>
            )}
          </p>
        </div>
      </div>

      {/* Environment Status */}
      {envConfig && (
        <div className="mt-4 pt-4 border-t border-slate-700">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">Environment</div>
          <div className="flex flex-wrap gap-1.5">
            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium ${
              envConfig.db_type === 'postgres'
                ? 'bg-blue-500/20 text-blue-400'
                : 'bg-amber-500/20 text-amber-400'
            }`}>
              <Database size={10} />
              {envConfig.db_type === 'postgres' ? 'PostgreSQL' : 'SQLite'}
            </span>
            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium ${
              envConfig.storage_type === 'supabase'
                ? 'bg-green-500/20 text-green-400'
                : 'bg-slate-500/20 text-slate-400'
            }`}>
              <Cloud size={10} />
              {envConfig.storage_type === 'supabase' ? 'Cloud' : 'Local'}
            </span>
          </div>
        </div>
      )}
    </aside>
  )
}

