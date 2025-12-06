/**
 * Bot Status API - GET current bot status, positions, orders, wallet
 * 
 * This endpoint calls the Python trading bot to get real-time status
 */

import { NextResponse } from 'next/server';
import { spawn } from 'child_process';
import path from 'path';

export interface BotStatus {
  running: boolean;
  mode: 'paper' | 'live';
  network: 'testnet' | 'mainnet';
  uptime_seconds: number | null;
  wallet: {
    balance_usdt: number;
    available_usdt: number;
    equity_usdt: number;
  };
  positions: Array<{
    symbol: string;
    side: 'Buy' | 'Sell';
    size: number;
    entry_price: number;
    mark_price: number;
    pnl: number;
    leverage: string;
  }>;
  open_orders: Array<{
    order_id: string;
    symbol: string;
    side: string;
    price: number;
    qty: number;
    status: string;
  }>;
  slots: {
    used: number;
    max: number;
    available: number;
  };
  last_cycle: string | null;
  error: string | null;
}

export async function GET() {
  const pythonDir = path.join(process.cwd(), 'python');
  
  const pythonCode = `
import sys
sys.path.insert(0, '${pythonDir}')
import json

from trading_bot.engine.order_executor import OrderExecutor
from trading_bot.config.settings_v2 import ConfigV2
from trading_bot.db.init_trading_db import get_connection

try:
    config = ConfigV2.load()
    executor = OrderExecutor(testnet=False)
    
    # Get wallet balance
    wallet = executor.get_wallet_balance()
    
    # Get positions
    positions_result = executor.get_positions()
    
    # Get config for slots
    db = get_connection()
    cursor = db.execute("SELECT value FROM config WHERE key = 'trading.max_concurrent_trades'")
    row = cursor.fetchone()
    max_trades = int(row[0]) if row else 3
    
    # Get last cycle
    cursor = db.execute("SELECT started_at FROM cycles ORDER BY started_at DESC LIMIT 1")
    last_cycle_row = cursor.fetchone()
    last_cycle = last_cycle_row[0] if last_cycle_row else None
    
    status = {
        "running": False,  # TODO: Check actual process status
        "mode": "paper" if config.trading.paper_trading else "live",
        "network": "mainnet",
        "uptime_seconds": None,
        "wallet": {
            "balance_usdt": wallet.get("wallet_balance", 0),
            "available_usdt": wallet.get("available", 0),
            "equity_usdt": wallet.get("equity", 0),
        },
        "positions": positions_result.get("positions", []),
        "open_orders": [],  # TODO: Add open orders query
        "slots": {
            "used": len(positions_result.get("positions", [])),
            "max": max_trades,
            "available": max_trades - len(positions_result.get("positions", [])),
        },
        "last_cycle": last_cycle,
        "error": None,
    }
    
    print(json.dumps(status))
    
except Exception as e:
    print(json.dumps({"error": str(e)}))
`;

  return new Promise<Response>((resolve) => {
    const pythonProcess = spawn('python3', ['-c', pythonCode], {
      cwd: pythonDir,
      env: { ...process.env },
    });

    let output = '';
    let errorOutput = '';

    pythonProcess.stdout.on('data', (data) => {
      output += data.toString();
    });

    pythonProcess.stderr.on('data', (data) => {
      errorOutput += data.toString();
    });

    pythonProcess.on('close', (code) => {
      if (code !== 0) {
        resolve(NextResponse.json(
          { error: `Python process failed: ${errorOutput}` },
          { status: 500 }
        ));
        return;
      }

      try {
        const status = JSON.parse(output.trim());
        resolve(NextResponse.json(status));
      } catch {
        resolve(NextResponse.json(
          { error: `Failed to parse response: ${output}` },
          { status: 500 }
        ));
      }
    });

    // Timeout after 10 seconds
    setTimeout(() => {
      pythonProcess.kill();
      resolve(NextResponse.json(
        { error: 'Request timeout' },
        { status: 504 }
      ));
    }, 10000);
  });
}

