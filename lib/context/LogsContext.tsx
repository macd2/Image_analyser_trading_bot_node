'use client'

import { createContext, useContext, useState, useCallback, ReactNode, useRef, useEffect } from 'react'

interface LogsState {
  // Persistent logs per instance (survives route changes)
  logs: Record<string, string[]>  // instanceId -> logs array
  stderrLogs: Record<string, string[]>
  
  // Actions
  addLog: (log: string, instanceId?: string) => void
  addStderrLog: (log: string, instanceId?: string) => void
  setLogs: (logs: string[], instanceId?: string) => void
  setStderrLogs: (logs: string[], instanceId?: string) => void
  clearLogs: (instanceId?: string) => void
}

const LogsContext = createContext<LogsState | null>(null)

export function LogsProvider({ children }: { children: ReactNode }) {
  const [logs, setLogsState] = useState<Record<string, string[]>>({})
  const [stderrLogs, setStderrLogsState] = useState<Record<string, string[]>>({})
  
  // Use refs to avoid stale closures in callbacks
  const logsRef = useRef(logs)
  const stderrRef = useRef(stderrLogs)
  
  useEffect(() => { logsRef.current = logs }, [logs])
  useEffect(() => { stderrRef.current = stderrLogs }, [stderrLogs])

  const addLog = useCallback((log: string, instanceId?: string) => {
    const key = instanceId || 'global'
    console.log('[LogsContext] addLog', { key, log: log.substring(0, 100) })
    setLogsState(prev => {
      const instanceLogs = prev[key] || []
      const newLogs = [...instanceLogs, log]
      // Keep last 2000 logs per instance to prevent memory issues
      const updated = { ...prev, [key]: newLogs.slice(-2000) }
      console.log('[LogsContext] Updated logs for', key, 'new count:', updated[key].length)
      return updated
    })
  }, [])

  const addStderrLog = useCallback((log: string, instanceId?: string) => {
    const key = instanceId || 'global'
    setStderrLogsState(prev => {
      const instanceLogs = prev[key] || []
      const newLogs = [...instanceLogs, log]
      return { ...prev, [key]: newLogs.slice(-2000) }
    })
  }, [])

  const setLogs = useCallback((newLogs: string[], instanceId?: string) => {
    const key = instanceId || 'global'
    setLogsState(prev => {
      const sliced = newLogs.slice(-2000)
      const instanceLogs = prev[key] || []
      // Fast check: if same length and last entry is same, skip update
      if (instanceLogs.length === sliced.length && instanceLogs[instanceLogs.length - 1] === sliced[sliced.length - 1]) {
        return prev
      }
      return { ...prev, [key]: sliced }
    })
  }, [])

  const setStderrLogs = useCallback((newLogs: string[], instanceId?: string) => {
    const key = instanceId || 'global'
    setStderrLogsState(prev => ({
      ...prev,
      [key]: newLogs.slice(-2000)
    }))
  }, [])

  const clearLogs = useCallback((instanceId?: string) => {
    if (instanceId) {
      setLogsState(prev => ({ ...prev, [instanceId]: [] }))
      setStderrLogsState(prev => ({ ...prev, [instanceId]: [] }))
    } else {
      setLogsState({})
      setStderrLogsState({})
    }
  }, [])

  return (
    <LogsContext.Provider value={{
      logs,
      stderrLogs,
      addLog,
      addStderrLog,
      setLogs,
      setStderrLogs,
      clearLogs,
    }}>
      {children}
    </LogsContext.Provider>
  )
}

export function useLogs() {
  const context = useContext(LogsContext)
  if (!context) {
    throw new Error('useLogs must be used within LogsProvider')
  }
  return context
}

