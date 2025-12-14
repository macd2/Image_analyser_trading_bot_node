/**
 * Wallet API - GET current wallet balance from Bybit
 * This is a fallback endpoint when WebSocket wallet data is not available
 * 
 * GET /api/bot/wallet
 */

import { NextRequest, NextResponse } from 'next/server';
import { spawn } from 'child_process';
import path from 'path';

export const dynamic = 'force-dynamic';

interface WalletResponse {
  coin: string;
  walletBalance: string;
  availableToWithdraw: string;
  equity: string;
  unrealisedPnl: string;
  error?: string;
}

export async function GET(request: NextRequest) {
  try {
    // Call Python script to fetch wallet balance from Bybit API
    const pythonScript = path.join(process.cwd(), 'python', 'get_wallet_balance.py');
    
    return new Promise((resolve) => {
      const python = spawn('python', [pythonScript], {
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
        if (code !== 0) {
          console.error('[Wallet API] Python script error:', stderr);
          return resolve(NextResponse.json(
            { error: 'Failed to fetch wallet balance', details: stderr },
            { status: 500 }
          ));
        }

        try {
          const result = JSON.parse(stdout) as WalletResponse;
          
          if (result.error) {
            return resolve(NextResponse.json(
              { error: result.error },
              { status: 500 }
            ));
          }

          return resolve(NextResponse.json(result));
        } catch (e) {
          console.error('[Wallet API] Failed to parse response:', stdout);
          return resolve(NextResponse.json(
            { error: 'Failed to parse wallet response' },
            { status: 500 }
          ));
        }
      });

      // Timeout after 10 seconds
      setTimeout(() => {
        python.kill();
        resolve(NextResponse.json(
          { error: 'Wallet fetch timeout' },
          { status: 504 }
        ));
      }, 10000);
    });
  } catch (error) {
    console.error('[Wallet API] Error:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    );
  }
}

