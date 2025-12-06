/**
 * VNC Status API - Check if VNC server is available
 *
 * GET - Returns VNC availability and connection info
 */

import { NextResponse } from 'next/server';

// Force dynamic rendering - don't try to check VNC during build
export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    // Simple flag to enable/disable VNC (set in Railway environment)
    const enableVnc = process.env.ENABLE_VNC === 'true';
    console.log(`[VNC Status] ENABLE_VNC=${process.env.ENABLE_VNC}, enableVnc=${enableVnc}`);

    // noVNC port (default 6080)
    const vncPort = process.env.VNC_PORT || '6080';

    // For Railway internal connections, use localhost (works within the same container)
    // Railway's supervisor runs all services in the same container
    const vncHost = 'localhost';

    // Railway TCP Proxy configuration
    // When you add a TCP Proxy in Railway settings for port 6080,
    // Railway will provide a public address like: interchange.proxy.rlwy.net:13575
    // Set this in the RAILWAY_TCP_PROXY_DOMAIN and RAILWAY_TCP_PROXY_PORT env vars
    const railwayTcpDomain = process.env.RAILWAY_TCP_PROXY_DOMAIN;
    const railwayTcpPort = process.env.RAILWAY_TCP_PROXY_PORT;

    // Try to detect if VNC server is actually running by checking if we can reach it
    let vncServerReachable = false;
    let errorDetails = '';

    if (enableVnc) {
      try {
        // Try to fetch the noVNC index page (localhost since supervisor runs in same container)
        const vncCheckUrl = `http://${vncHost}:${vncPort}/vnc.html`;
        console.log(`[VNC Status] Checking VNC server at: ${vncCheckUrl}`);

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 2000); // 2 second timeout

        const response = await fetch(vncCheckUrl, {
          signal: controller.signal,
          method: 'HEAD'
        });
        clearTimeout(timeoutId);

        vncServerReachable = response.ok;
        console.log(`[VNC Status] VNC server check: ${vncCheckUrl} - Status: ${response.status} ${response.ok ? 'OK' : 'FAILED'}`);

        if (!response.ok) {
          errorDetails = `HTTP ${response.status} ${response.statusText}`;
        }
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : 'Unknown error';
        errorDetails = errorMsg;
        console.error(`[VNC Status] VNC server not reachable at ${vncHost}:${vncPort}:`, errorMsg);
        vncServerReachable = false;
      }
    } else {
      console.log(`[VNC Status] VNC disabled - ENABLE_VNC not set to 'true'`);
    }

    // Build VNC connection address for external VNC clients
    // If Railway TCP Proxy is configured, use that; otherwise fall back to localhost
    let vncUrl: string;
    if (railwayTcpDomain && railwayTcpPort) {
      // Railway TCP Proxy address for external VNC clients
      vncUrl = `${railwayTcpDomain}:${railwayTcpPort}`;
      console.log('[VNC Status] Using Railway TCP Proxy:', vncUrl);
    } else {
      // Fallback for local development
      vncUrl = `localhost:${vncPort}`;
      console.log('[VNC Status] Using localhost (development mode):', vncUrl);
    }

    // VNC is available if enabled AND server is reachable
    const available = enableVnc && vncServerReachable;

    const result = {
      available,
      enableVnc,
      vncServerReachable,
      vncPort,
      vncHost,
      vncUrl,
      railwayTcpConfigured: !!(railwayTcpDomain && railwayTcpPort),
      errorDetails: errorDetails || undefined,
      message: available
        ? railwayTcpDomain && railwayTcpPort
          ? `VNC server available at ${vncUrl} (Railway TCP Proxy)`
          : `VNC server available at ${vncUrl} (localhost)`
        : enableVnc
          ? `VNC enabled but server not reachable at ${vncHost}:${vncPort}${errorDetails ? ` - ${errorDetails}` : ''}`
          : 'VNC not enabled (set ENABLE_VNC=true in environment)'
    };

    console.log(`[VNC Status] Result:`, result);
    return NextResponse.json(result);
  } catch (error) {
    console.error('VNC status check error:', error);
    return NextResponse.json({
      available: false,
      error: 'Failed to check VNC status'
    }, { status: 500 });
  }
}

