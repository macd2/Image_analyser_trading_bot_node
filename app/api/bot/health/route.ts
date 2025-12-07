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
  // For Railway health checks, we need a FAST response (< 5 seconds)
  // Don't check external services - just verify the app is alive

  // Simple health check: if we can respond, we're healthy
  const summary = {
    overall: 'healthy',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
    message: 'Application is running'
  }

  // Always return 200 - Railway just needs to know the app is alive
  return NextResponse.json(summary, {
    status: 200
  })
}

