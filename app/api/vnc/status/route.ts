/**
 * VNC Status API - Check if VNC server is available
 *
 * GET - Returns VNC availability and connection info
 */

import { NextResponse } from 'next/server';

export async function GET() {
  try {
    // Check if running on Railway (VNC should be available)
    const isRailway = process.env.RAILWAY_ENVIRONMENT !== undefined ||
                      process.env.RAILWAY_SERVICE_NAME !== undefined ||
                      process.env.RAILWAY_STATIC_URL !== undefined ||
                      process.env.RAILWAY_PUBLIC_DOMAIN !== undefined;

    // Check if VNC is enabled in environment
    const vncEnabled = process.env.VNC_ENABLED !== 'false'; // Default to true

    // noVNC port (default 6080)
    const vncPort = process.env.VNC_PORT || '6080';

    // Try to detect if VNC server is actually running by checking if we can reach it
    let vncServerReachable = false;
    try {
      // Try to fetch the noVNC index page
      const vncCheckUrl = `http://localhost:${vncPort}/vnc.html`;
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 1000); // 1 second timeout

      const response = await fetch(vncCheckUrl, {
        signal: controller.signal,
        method: 'HEAD'
      });
      clearTimeout(timeoutId);

      vncServerReachable = response.ok;
    } catch (error) {
      // VNC server not reachable (expected in local dev)
      vncServerReachable = false;
    }

    // Build VNC URL
    const vncUrl = vncServerReachable || isRailway
      ? `/vnc/vnc.html?autoconnect=true&resize=scale`
      : `http://localhost:${vncPort}/vnc.html?autoconnect=true&resize=scale`;

    // VNC is available if either Railway is detected OR VNC server is reachable
    const available = (isRailway || vncServerReachable) && vncEnabled;

    return NextResponse.json({
      available,
      isRailway,
      vncEnabled,
      vncServerReachable,
      vncPort,
      vncUrl,
      message: available
        ? 'VNC server available'
        : 'VNC not available (not running on Railway or VNC server not reachable)'
    });
  } catch (error) {
    console.error('VNC status check error:', error);
    return NextResponse.json({
      available: false,
      error: 'Failed to check VNC status'
    }, { status: 500 });
  }
}

