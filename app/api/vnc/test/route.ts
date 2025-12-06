/**
 * VNC Test API - Test VNC server connectivity
 */

import { NextResponse } from 'next/server';

// Force dynamic rendering - don't try to check VNC during build
export const dynamic = 'force-dynamic';

export async function GET() {
  // Disable in production
  if (process.env.NODE_ENV === 'production') {
    return NextResponse.json({ error: 'Test endpoint disabled in production' }, { status: 404 });
  }
  const results: any = {
    timestamp: new Date().toISOString(),
    tests: []
  };

  // Test 1: Check environment variables
  results.tests.push({
    name: 'Environment Variables',
    ENABLE_VNC: process.env.ENABLE_VNC,
    VNC_PORT: process.env.VNC_PORT || '6080',
    NODE_ENV: process.env.NODE_ENV,
  });

  // Test 2: Try to fetch noVNC index page
  const vncPort = process.env.VNC_PORT || '6080';
  const vncHost = 'localhost';
  
  try {
    const vncCheckUrl = `http://${vncHost}:${vncPort}/vnc.html`;
    console.log(`[VNC Test] Attempting to fetch: ${vncCheckUrl}`);
    
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3000);
    
    const response = await fetch(vncCheckUrl, { 
      signal: controller.signal,
      method: 'HEAD'
    });
    clearTimeout(timeoutId);
    
    results.tests.push({
      name: 'VNC Server Reachability (HEAD)',
      url: vncCheckUrl,
      status: response.status,
      statusText: response.statusText,
      ok: response.ok,
      headers: Object.fromEntries(response.headers.entries())
    });
  } catch (error) {
    results.tests.push({
      name: 'VNC Server Reachability (HEAD)',
      url: `http://${vncHost}:${vncPort}/vnc.html`,
      error: error instanceof Error ? error.message : 'Unknown error',
      errorType: error instanceof Error ? error.constructor.name : typeof error
    });
  }

  // Test 3: Try to fetch with GET
  try {
    const vncCheckUrl = `http://${vncHost}:${vncPort}/vnc.html`;
    console.log(`[VNC Test] Attempting GET: ${vncCheckUrl}`);
    
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3000);
    
    const response = await fetch(vncCheckUrl, { 
      signal: controller.signal,
      method: 'GET'
    });
    clearTimeout(timeoutId);
    
    const contentType = response.headers.get('content-type');
    const contentLength = response.headers.get('content-length');
    
    results.tests.push({
      name: 'VNC Server Reachability (GET)',
      url: vncCheckUrl,
      status: response.status,
      statusText: response.statusText,
      ok: response.ok,
      contentType,
      contentLength
    });
  } catch (error) {
    results.tests.push({
      name: 'VNC Server Reachability (GET)',
      url: `http://${vncHost}:${vncPort}/vnc.html`,
      error: error instanceof Error ? error.message : 'Unknown error',
      errorType: error instanceof Error ? error.constructor.name : typeof error
    });
  }

  // Test 4: Check if port 5900 (VNC server) is reachable
  try {
    const vncServerUrl = `http://${vncHost}:5900`;
    console.log(`[VNC Test] Attempting to connect to VNC server: ${vncServerUrl}`);
    
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3000);
    
    const response = await fetch(vncServerUrl, { 
      signal: controller.signal,
      method: 'GET'
    });
    clearTimeout(timeoutId);
    
    results.tests.push({
      name: 'VNC Server Port 5900',
      url: vncServerUrl,
      status: response.status,
      ok: response.ok
    });
  } catch (error) {
    results.tests.push({
      name: 'VNC Server Port 5900',
      url: `http://${vncHost}:5900`,
      error: error instanceof Error ? error.message : 'Unknown error',
      note: 'This is expected to fail - VNC uses binary protocol, not HTTP'
    });
  }

  return NextResponse.json(results, { status: 200 });
}

