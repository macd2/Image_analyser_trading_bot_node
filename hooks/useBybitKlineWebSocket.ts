import { useEffect, useRef, useCallback } from 'react'

interface KlineData {
  start: number
  end: number
  interval: string
  open: string
  close: string
  high: string
  low: string
  volume: string
  turnover: string
  confirm: boolean
  timestamp: number
}

interface KlineMessage {
  topic: string
  type: string
  ts: number
  data: KlineData[]
}

interface UseBybitKlineWebSocketProps {
  symbol: string
  interval: string
  onKlineUpdate: (kline: KlineData) => void
  enabled?: boolean
}

/**
 * Hook to subscribe to Bybit real-time kline/candle updates via WebSocket
 * 
 * @param symbol - Trading pair (e.g., BTCUSDT)
 * @param interval - Candle interval (1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, W, M)
 * @param onKlineUpdate - Callback when new kline data arrives
 * @param enabled - Whether to connect to WebSocket (default: true)
 */
export function useBybitKlineWebSocket({
  symbol,
  interval,
  onKlineUpdate,
  enabled = true
}: UseBybitKlineWebSocketProps) {
  const wsRef = useRef<WebSocket | null>(null)
  const pingIntervalRef = useRef<NodeJS.Timeout | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  const connect = useCallback(() => {
    if (!enabled) return

    try {
      // Bybit public WebSocket endpoint for linear perpetuals
      const ws = new WebSocket('wss://stream.bybit.com/v5/public/linear')
      wsRef.current = ws

      ws.onopen = () => {
        console.log('[Bybit WS] Connected')
        
        // Subscribe to kline topic
        const subscribeMsg = {
          op: 'subscribe',
          args: [`kline.${interval}.${symbol}`]
        }
        ws.send(JSON.stringify(subscribeMsg))
        console.log(`[Bybit WS] Subscribed to kline.${interval}.${symbol}`)

        // Start ping interval (every 20 seconds as per Bybit docs)
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ op: 'ping' }))
          }
        }, 20000)
      }

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)

          // Handle pong response
          if (message.op === 'pong') {
            return
          }

          // Handle subscription confirmation
          if (message.success && message.op === 'subscribe') {
            console.log('[Bybit WS] Subscription confirmed')
            return
          }

          // Handle kline data
          if (message.topic && message.topic.startsWith('kline.') && message.data) {
            const klineMsg = message as KlineMessage
            if (klineMsg.data && klineMsg.data.length > 0) {
              onKlineUpdate(klineMsg.data[0])
            }
          }
        } catch (err) {
          console.error('[Bybit WS] Failed to parse message:', err)
        }
      }

      ws.onerror = (error) => {
        console.error('[Bybit WS] Error:', error)
      }

      ws.onclose = () => {
        console.log('[Bybit WS] Disconnected')
        
        // Clear ping interval
        if (pingIntervalRef.current) {
          clearInterval(pingIntervalRef.current)
          pingIntervalRef.current = null
        }

        // Attempt to reconnect after 5 seconds
        if (enabled) {
          reconnectTimeoutRef.current = setTimeout(() => {
            console.log('[Bybit WS] Reconnecting...')
            connect()
          }, 5000)
        }
      }
    } catch (err) {
      console.error('[Bybit WS] Connection error:', err)
    }
  }, [symbol, interval, onKlineUpdate, enabled])

  const disconnect = useCallback(() => {
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current)
      pingIntervalRef.current = null
    }

    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }

    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
  }, [])

  useEffect(() => {
    connect()
    return () => disconnect()
  }, [connect, disconnect])

  return { disconnect }
}

