'use client'

import { useEffect } from 'react'
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
 */
export function GlobalLogListener() {
  const { socket } = useRealtime()
  const { addLog } = useBotState()

  useEffect(() => {
    if (!socket) {
      console.log('[GlobalLogListener] No socket available yet')
      return
    }

    console.log('[GlobalLogListener] Subscribing to bot_log events')

    const handleBotLog = (data: { log: string; instanceId?: string; timestamp: number }) => {
      // Add log to the appropriate instance (or 'global' if no instanceId)
      const targetInstanceId = data.instanceId || 'global'
      console.log('[GlobalLogListener] Received log for instance:', targetInstanceId, data.log.substring(0, 50))
      addLog(data.log, targetInstanceId)
    }

    socket.on('bot_log', handleBotLog)

    return () => {
      console.log('[GlobalLogListener] Unsubscribing from bot_log events')
      socket.off('bot_log', handleBotLog)
    }
  }, [socket, addLog])

  // This component doesn't render anything
  return null
}

