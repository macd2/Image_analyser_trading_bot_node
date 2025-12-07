import { NextResponse } from 'next/server'

interface HealthCheckResult {
  service: string
  status: 'ok' | 'error' | 'timeout'
  latency?: number
  error?: string
}

async function checkEndpoint(
  name: string,
  url: string,
  timeout: number = 5000,
  acceptedStatuses: number[] = [200, 401, 403, 405] // 401/403 means service is up but auth required
): Promise<HealthCheckResult> {
  const start = Date.now()
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeout)

  try {
    const response = await fetch(url, {
      signal: controller.signal,
      method: 'GET',
      headers: {
        'User-Agent': 'TradingBot/1.0'
      }
    })

    clearTimeout(timeoutId)
    const latency = Date.now() - start

    if (acceptedStatuses.includes(response.status)) {
      return {
        service: name,
        status: 'ok',
        latency
      }
    } else {
      return {
        service: name,
        status: 'error',
        latency,
        error: `HTTP ${response.status}`
      }
    }
  } catch (error: any) {
    clearTimeout(timeoutId)
    const latency = Date.now() - start

    if (error.name === 'AbortError') {
      return {
        service: name,
        status: 'timeout',
        latency,
        error: `Timeout after ${timeout}ms`
      }
    }

    return {
      service: name,
      status: 'error',
      latency,
      error: error instanceof Error ? error.message : 'Unknown error'
    }
  }
}

/**
 * Detailed health check endpoint for monitoring external services.
 * This is NOT used by Railway - it's for manual monitoring only.
 * Railway uses /api/bot/health which is fast and simple.
 */
export async function GET() {
  const checks: Promise<HealthCheckResult>[] = [
    // TradingView - Required for chart capture
    checkEndpoint('TradingView', 'https://www.tradingview.com/', 10000),
    // Bybit Mainnet - Required for trading
    checkEndpoint('Bybit Mainnet', 'https://api.bybit.com/v5/market/time', 5000),
    // Bybit Testnet - Optional, for paper trading
    checkEndpoint('Bybit Testnet', 'https://api-testnet.bybit.com/v5/market/time', 5000),
    // OpenAI - Required for analysis
    checkEndpoint('OpenAI', 'https://api.openai.com/v1/models', 5000),
  ]

  const results = await Promise.all(checks)

  // Critical services that affect trading capability
  const criticalServices = ['TradingView', 'Bybit Mainnet', 'OpenAI']
  const criticalOk = results
    .filter(r => criticalServices.includes(r.service))
    .every(r => r.status === 'ok')

  const summary = {
    overall: criticalOk ? 'healthy' : 'degraded',
    timestamp: new Date().toISOString(),
    checks: results,
    message: 'This is a detailed health check for monitoring. Railway uses /api/bot/health instead.'
  }

  // Always return 200 for monitoring - don't fail the request
  return NextResponse.json(summary, {
    status: 200
  })
}

