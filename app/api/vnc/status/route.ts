/**
 * VNC Status API - Check if VNC server is available
 *
 * GET - Returns VNC availability and connection info
 */

import { NextResponse } from 'next/server';

export async function GET() {
  try {
    // Simple flag to enable/disable VNC (set in Railway environment)
    const enableVnc = process.env.ENABLE_VNC === 'true';

    // noVNC port (default 6080)
    const vncPort = process.env.VNC_PORT || '6080';

    // For Railway internal connections, use localhost (works within the same container)
    // Railway's supervisor runs all services in the same container
    const vncHost = 'localhost';

    // Try to detect if VNC server is actually running by checking if we can reach it
    let vncServerReachable = false;
    if (enableVnc) {
      try {
        // Try to fetch the noVNC index page (localhost since supervisor runs in same container)
        const vncCheckUrl = `http://${vncHost}:${vncPort}/vnc.html`;
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 2000); // 2 second timeout

        const response = await fetch(vncCheckUrl, {
          signal: controller.signal,
          method: 'HEAD'
        });
        clearTimeout(timeoutId);

        vncServerReachable = response.ok;
        console.log(`VNC server check: ${vncCheckUrl} - ${response.ok ? 'OK' : 'FAILED'}`);
      } catch (error) {
        console.log(`VNC server not reachable at ${vncHost}:${vncPort}:`, error instanceof Error ? error.message : 'Unknown error');
        vncServerReachable = false;
      }
    }

    // Build VNC URL - use /vnc/ proxy path configured in next.config.js
    const vncUrl = `/vnc/vnc.html?autoconnect=true&resize=scale`;

    // VNC is available if enabled AND server is reachable
    const available = enableVnc && vncServerReachable;

    return NextResponse.json({
      available,
      enableVnc,
      vncServerReachable,
      vncPort,
      vncHost,
      vncUrl,
      message: available
        ? 'VNC server available'
        : enableVnc
          ? `VNC enabled but server not reachable at ${vncHost}:${vncPort}`
          : 'VNC not enabled (set ENABLE_VNC=true in environment)'
    });
  } catch (error) {
    console.error('VNC status check error:', error);
    return NextResponse.json({
      available: false,
      error: 'Failed to check VNC status'
    }, { status: 500 });
  }
}

