import { NextResponse } from 'next/server'

/**
 * Fast health check endpoint for Railway.
 * This endpoint must respond quickly (< 5 seconds) to prevent Railway from killing the container.
 * For detailed health checks of external services, use /api/bot/health-detailed instead.
 */
export async function GET() {
  // For Railway health checks, we need a FAST response (< 5 seconds)
  // Don't check external services - just verify the app is alive

  // Simple health check: if we can respond, we're healthy
  const summary = {
    overall: 'healthy' as const,
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
    message: 'Application is running',
    // Include empty checks array for UI compatibility
    checks: []
  }

  // Always return 200 - Railway just needs to know the app is alive
  return NextResponse.json(summary, {
    status: 200
  })
}

