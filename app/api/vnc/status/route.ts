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
                      process.env.RAILWAY_SERVICE_NAME !== undefined;
    
    // Check if VNC is enabled in environment
    const vncEnabled = process.env.VNC_ENABLED !== 'false'; // Default to true
    
    // noVNC port (default 6080)
    const vncPort = process.env.VNC_PORT || '6080';
    
    // Build VNC URL
    const vncUrl = isRailway 
      ? `/vnc/vnc.html?autoconnect=true&resize=scale`
      : `http://localhost:${vncPort}/vnc.html?autoconnect=true&resize=scale`;
    
    return NextResponse.json({
      available: isRailway && vncEnabled,
      isRailway,
      vncEnabled,
      vncPort,
      vncUrl,
      message: isRailway 
        ? 'VNC server available on Railway' 
        : 'VNC not available (not running on Railway)'
    });
  } catch (error) {
    console.error('VNC status check error:', error);
    return NextResponse.json({
      available: false,
      error: 'Failed to check VNC status'
    }, { status: 500 });
  }
}

