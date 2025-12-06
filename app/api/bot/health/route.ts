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
      method: 'GET',
      signal: controller.signal,
      headers: {
        'User-Agent': 'TradingBot-HealthCheck/1.0'
      }
    })
    clearTimeout(timeoutId)
    const latency = Date.now() - start

    // Consider service OK if we got any response (even auth errors mean service is reachable)
    const isOk = acceptedStatuses.includes(response.status) || response.ok
    return {
      service: name,
      status: isOk ? 'ok' : 'error',
      latency,
      error: isOk ? undefined : `HTTP ${response.status}`
    }
  } catch (error: unknown) {
    clearTimeout(timeoutId)
    const latency = Date.now() - start

    if (error instanceof Error && error.name === 'AbortError') {
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
    checks: results
  }

  // Return 200 if critical services are up, 503 if any critical service is down
  return NextResponse.json(summary, {
    status: criticalOk ? 200 : 503
  })
}

