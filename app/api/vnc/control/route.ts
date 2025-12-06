/**
 * VNC Control API - Start/Stop VNC services
 *
 * POST - Control VNC services (start/stop/restart/status)
 */
import { NextRequest, NextResponse } from 'next/server';
import { execSync } from 'child_process';

export async function POST(request: NextRequest) {
  try {
    const { action } = await request.json();

    // Validate action
    if (!['start', 'stop', 'restart', 'status'].includes(action)) {
      return NextResponse.json({
        success: false,
        error: `Invalid action: ${action}. Must be one of: start, stop, restart, status`
      }, { status: 400 });
    }

    let command: string;
    let successMessage: string;

    // Build supervisorctl command based on action
    // Note: Fluxbox and noVNC removed - only essential services
    switch (action) {
      case 'start':
        command = 'supervisorctl start xvfb x11vnc';
        successMessage = 'VNC services started successfully';
        break;
      case 'stop':
        command = 'supervisorctl stop xvfb x11vnc';
        successMessage = 'VNC services stopped successfully';
        break;
      case 'restart':
        command = 'supervisorctl restart xvfb x11vnc';
        successMessage = 'VNC services restarted successfully';
        break;
      case 'status':
        command = 'supervisorctl status xvfb x11vnc';
        successMessage = 'VNC services status retrieved';
        break;
      default:
        return NextResponse.json({
          success: false,
          error: 'Invalid action'
        }, { status: 400 });
    }

    // Execute supervisorctl command
    const result = execSync(command).toString();

    // Parse status output for better response
    const servicesStatus: Record<string, { status: string; raw: string }> = {};
    if (action === 'status') {
      const lines = result.trim().split('\n');
      lines.forEach(line => {
        const parts = line.split(/\s+/);
        const name = parts[0];
        const status = parts[1];
        if (name && status) {
          servicesStatus[name] = {
            status: status.includes('RUNNING') ? 'running' :
                   status.includes('STOPPED') ? 'stopped' :
                   status.includes('FATAL') ? 'error' : 'unknown',
            raw: line.trim()
          };
        }
      });
    }

    return NextResponse.json({
      success: true,
      message: successMessage,
      action,
      result: action === 'status' ? servicesStatus : result.trim(),
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('VNC control error:', error);
    return NextResponse.json({
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error',
      details: error instanceof Error ? error.stack : undefined
    }, { status: 500 });
  }
}

