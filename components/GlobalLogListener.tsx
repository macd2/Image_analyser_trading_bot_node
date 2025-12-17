'use client'

import { useEffect, useRef, useCallback } from 'react'
import { useRealtime } from '@/hooks/useRealtime'
import { useLogs } from '@/lib/context/LogsContext'

/**
 * GlobalLogListener - Subscribes to Socket.IO bot_log events at the app level
 * and populates LogsContext with logs for all instances.
 *
 * This ensures that:
 * 1. Logs are captured in real-time as they arrive via Socket.IO
 * 2. InstanceCard's RecentLogsSection gets live updates
 * 3. Logs persist in context when navigating between pages
 * 4. Logs are recovered from database on browser reconnection
 */
export function GlobalLogListener() {
  const { socket } = useRealtime()
  const { addLog } = useLogs()
  const logsPerInstanceRef = useRef<Record<string, string[]>>({})

  // Fetch recent logs from database for an instance (on first connection)
  const fetchRecentLogs = useCallback(async (instanceId: string) => {
    try {
      const res = await fetch(`/api/bot/logs/recent?instance_id=${instanceId}&limit=500`)
      if (res.ok) {
        const data = await res.json()
        console.log(`[GlobalLogListener] Loaded ${data.count} recent logs for instance: ${instanceId}`)
        // Initialize logs for this instance from database
        logsPerInstanceRef.current[instanceId] = data.logs || []
      }
    } catch (err) {
      console.error(`[GlobalLogListener] Failed to fetch recent logs for ${instanceId}:`, err)
      logsPerInstanceRef.current[instanceId] = []
    }
  }, [])

  useEffect(() => {
    if (!socket) {
      console.log('[GlobalLogListener] No socket available yet')
      return
    }

    console.log('[GlobalLogListener] Subscribing to bot_log events')

    const handleBotLog = (data: { log: string; instanceId?: string; timestamp: number }) => {
      const targetInstanceId = data.instanceId || 'global'
      console.log('[GlobalLogListener] Received log for instance:', targetInstanceId, data.log.substring(0, 50))

      // On first log from this instance, fetch historical logs from database
      if (data.instanceId && !logsPerInstanceRef.current[data.instanceId]) {
        console.log(`[GlobalLogListener] First log from instance ${data.instanceId}, fetching historical logs...`)
        logsPerInstanceRef.current[data.instanceId] = []
        fetchRecentLogs(data.instanceId)
      }

      // Add the incoming log to context immediately
      console.log('[GlobalLogListener] Calling addLog with:', { targetInstanceId, logLength: data.log.length })
      addLog(data.log, targetInstanceId)
    }

    socket.on('bot_log', handleBotLog)

    return () => {
      console.log('[GlobalLogListener] Unsubscribing from bot_log events')
      socket.off('bot_log', handleBotLog)
    }
  }, [socket, addLog, fetchRecentLogs])

  // This component doesn't render anything
  return null
}

