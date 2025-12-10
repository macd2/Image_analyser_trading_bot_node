import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

/**
 * Simple Password Protection Middleware
 * 
 * Protects the dashboard with HTTP Basic Auth.
 * Set DASHBOARD_PASSWORD in your environment variables.
 * 
 * Usage:
 *   - Set DASHBOARD_PASSWORD=your-secure-password in Railway/env
 *   - Browser will prompt for password on first visit
 *   - Username can be anything (or empty), only password is checked
 */

const PROTECTED_PATHS = [
  '/',           // Dashboard root
  '/analysis',
  '/backtest', 
  '/bot',
  '/browser',
  '/capture',
  '/execution',
  '/find-best-prompt',
  '/instances',
  '/learning',
  '/logs',
  '/monitoring',
  '/simulator',
]

// API routes that should also be protected (except health check)
const PROTECTED_API_PREFIXES = [
  '/api/bot',
  '/api/config',
  '/api/learning',
  '/api/settings',
  '/api/tournament',
  '/api/backtest',
]

// Paths that should NOT require auth (health checks, public assets)
const PUBLIC_PATHS = [
  '/api/bot/health',  // Health check for monitoring
  '/api/bot/simulator/auto-close',  // Internal auto-close endpoint called by monitor
  '/_next',           // Next.js assets
  '/favicon.ico',
]

function isPublicPath(pathname: string): boolean {
  return PUBLIC_PATHS.some(path => pathname.startsWith(path))
}

function isProtectedPath(pathname: string): boolean {
  // Check exact matches for dashboard pages
  if (PROTECTED_PATHS.includes(pathname)) return true
  
  // Check API prefixes
  if (PROTECTED_API_PREFIXES.some(prefix => pathname.startsWith(prefix))) return true
  
  // Dashboard routes under (dashboard) group
  if (pathname.startsWith('/') && !pathname.startsWith('/api') && !pathname.startsWith('/_next')) {
    return true
  }
  
  return false
}

function unauthorized(): NextResponse {
  return new NextResponse('Authentication required', {
    status: 401,
    headers: {
      'WWW-Authenticate': 'Basic realm="Trading Bot Dashboard"',
      'Content-Type': 'text/plain',
    },
  })
}

export function middleware(request: NextRequest) {
  const pathname = request.nextUrl.pathname
  
  // Skip auth for public paths
  if (isPublicPath(pathname)) {
    return NextResponse.next()
  }
  
  // Check if path needs protection
  if (!isProtectedPath(pathname)) {
    return NextResponse.next()
  }
  
  // Get password from environment
  const expectedPassword = process.env.DASHBOARD_PASSWORD
  
  // If no password set, allow access (development mode)
  if (!expectedPassword) {
    console.warn('[Middleware] DASHBOARD_PASSWORD not set - dashboard is unprotected!')
    return NextResponse.next()
  }
  
  // Check Authorization header
  const authHeader = request.headers.get('authorization')
  
  if (!authHeader || !authHeader.startsWith('Basic ')) {
    return unauthorized()
  }
  
  // Decode Basic Auth credentials
  try {
    const base64Credentials = authHeader.split(' ')[1]
    const credentials = Buffer.from(base64Credentials, 'base64').toString('utf-8')

    // Split only on the first colon to handle passwords containing colons
    // Format is "username:password" but username is ignored
    const colonIndex = credentials.indexOf(':')
    if (colonIndex === -1) {
      return unauthorized()
    }

    const password = credentials.substring(colonIndex + 1)

    if (password === expectedPassword) {
      return NextResponse.next()
    }
  } catch {
    // Invalid auth header format
  }
  
  return unauthorized()
}

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     */
    '/((?!_next/static|_next/image|favicon.ico).*)',
  ],
}

