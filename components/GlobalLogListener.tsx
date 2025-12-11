'use client'

import { useEffect, useRef } from 'react'
import { useRealtime } from '@/hooks/useRealtime'
import { useBotState } from '@/lib/context/BotStateContext'

/**
 * GlobalLogListener - Subscribes to Socket.IO bot_log events at the app level
 * and populates BotStateContext with logs for all instances.
 *
 * This ensures that:
 * 1. Logs are captured even when not on the instance detail page
 * 2. InstanceCard's RecentLogsSection gets live updates
 * 3. Logs persist in context when navigating between pages
 * 4. Logs are recovered from database on browser reconnection
 */
export function GlobalLogListener() {
  const { socket } = useRealtime()
  const { setLogs } = useBotState()
  const loadedInstancesRef = useRef<Set<string>>(new Set())

  // Fetch recent logs from database for an instance
  const fetchRecentLogs = async (instanceId: string) => {
    if (loadedInstancesRef.current.has(instanceId)) {
      console.log(`[GlobalLogListener] Already loaded logs for instance: ${instanceId}`)
      return
    }

    try {
      const res = await fetch(`/api/bot/logs/recent?instance_id=${instanceId}&limit=100`)
      if (res.ok) {
        const data = await res.json()
        console.log(`[GlobalLogListener] Loaded ${data.count} recent logs for instance: ${instanceId}`)
        setLogs(data.logs, instanceId)
        loadedInstancesRef.current.add(instanceId)
      }
    } catch (err) {
      console.error(`[GlobalLogListener] Failed to fetch recent logs for ${instanceId}:`, err)
    }
  }

  useEffect(() => {
    if (!socket) {
      console.log('[GlobalLogListener] No socket available yet')
      return
    }

    console.log('[GlobalLogListener] Subscribing to bot_log events')

    const handleBotLog = (data: { log: string; instanceId?: string; timestamp: number }) => {
      const targetInstanceId = data.instanceId || 'global'
      console.log('[GlobalLogListener] Received log for instance:', targetInstanceId, data.log.substring(0, 50))

      // Fetch recent logs on first log from this instance
      if (data.instanceId && !loadedInstancesRef.current.has(data.instanceId)) {
        fetchRecentLogs(data.instanceId)
      }
    }

    socket.on('bot_log', handleBotLog)

    return () => {
      console.log('[GlobalLogListener] Unsubscribing from bot_log events')
      socket.off('bot_log', handleBotLog)
    }
  }, [socket, setLogs])

  // This component doesn't render anything
  return null
}

