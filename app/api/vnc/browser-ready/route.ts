/**
 * VNC Browser Ready API - Signal that VNC is ready and browser should launch
 *
 * POST - Set browser_open_requested state to signal Python to launch browser
 */
import { NextRequest, NextResponse } from 'next/server';
import { execSync } from 'child_process';
import path from 'path';

export async function POST(request: NextRequest) {
  try {
    // Path to Python login state manager
    const pythonDir = path.join(process.cwd(), 'python');
    
    // Call Python script to set browser_open_requested state
    const command = `cd ${pythonDir} && python3 -c "from trading_bot.core.login_state_manager import set_browser_open_requested; set_browser_open_requested()"`;
    
    execSync(command);
    
    console.log('[VNC Browser Ready] Browser open requested state set successfully');
    
    return NextResponse.json({
      success: true,
      message: 'Browser open requested - Python will launch browser',
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('[VNC Browser Ready] Error setting state:', error);
    return NextResponse.json({
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error',
      details: error instanceof Error ? error.stack : undefined
    }, { status: 500 });
  }
}

