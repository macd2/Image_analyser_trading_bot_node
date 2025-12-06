/**
 * VNC Proxy API - Proxy requests to noVNC server
 * 
 * This avoids CORS issues when embedding noVNC in the dashboard
 */

import { NextRequest, NextResponse } from 'next/server';

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const path = searchParams.get('path') || '';
    
    // noVNC runs on port 6080 internally
    const vncPort = process.env.VNC_PORT || '6080';
    const vncHost = process.env.VNC_HOST || 'localhost';
    const vncUrl = `http://${vncHost}:${vncPort}/${path}`;
    
    // Fetch from noVNC server
    const response = await fetch(vncUrl);
    
    if (!response.ok) {
      return NextResponse.json({
        error: 'Failed to connect to VNC server',
        status: response.status
      }, { status: response.status });
    }
    
    // Get content type
    const contentType = response.headers.get('content-type') || 'text/html';
    
    // Return proxied response
    const data = await response.arrayBuffer();
    
    return new NextResponse(data, {
      headers: {
        'Content-Type': contentType,
        'Cache-Control': 'no-cache, no-store, must-revalidate',
      },
    });
  } catch (error) {
    console.error('VNC proxy error:', error);
    return NextResponse.json({
      error: 'Failed to proxy VNC request'
    }, { status: 500 });
  }
}

