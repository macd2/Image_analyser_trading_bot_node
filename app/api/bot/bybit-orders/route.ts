import { NextResponse } from 'next/server';
import { spawn } from 'child_process';
import path from 'path';

/**
 * GET /api/bot/bybit-orders - Fetch open orders from Bybit REST API
 * Used to get initial state when WebSocket connects
 */
export async function GET(): Promise<Response> {
  try {
    // Call Python script to fetch orders from Bybit API
    const pythonScript = path.join(process.cwd(), 'python', 'get_bybit_orders.py');
    
    return new Promise((resolve) => {
      const python = spawn('python3', [pythonScript], {
        cwd: process.cwd(),
        env: { ...process.env }
      });

      let stdout = '';
      let stderr = '';

      python.stdout.on('data', (data) => {
        stdout += data.toString();
      });

      python.stderr.on('data', (data) => {
        stderr += data.toString();
      });

      python.on('close', (code) => {
        if (code === 0) {
          try {
            const result = JSON.parse(stdout);
            resolve(NextResponse.json({
              success: true,
              orders: result.orders || [],
              timestamp: new Date().toISOString()
            }));
          } catch (e) {
            console.error('[Bybit Orders] Failed to parse Python output:', stdout);
            resolve(NextResponse.json(
              { success: false, error: 'Failed to parse orders', orders: [] },
              { status: 500 }
            ));
          }
        } else {
          console.error('[Bybit Orders] Python script error:', stderr);
          resolve(NextResponse.json(
            { success: false, error: stderr || 'Failed to fetch orders', orders: [] },
            { status: 500 }
          ));
        }
      });

      // Timeout after 10 seconds
      setTimeout(() => {
        python.kill();
        resolve(NextResponse.json(
          { success: false, error: 'Request timeout', orders: [] },
          { status: 504 }
        ));
      }, 10000);
    });
  } catch (error) {
    console.error('[Bybit Orders] Error:', error);
    return NextResponse.json(
      { success: false, error: String(error), orders: [] },
      { status: 500 }
    );
  }
}

