/**
 * Bot Status API - GET current bot status, positions, orders, wallet
 *
 * This endpoint calls the Python trading bot to get real-time status
 */

import { NextRequest, NextResponse } from 'next/server';
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

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const instanceId = searchParams.get('instance_id') || '';
  const pythonDir = path.join(process.cwd(), 'python');

  // Use centralized db client that respects DB_TYPE for SQLite/PostgreSQL switching
  const pythonCode = `
import sys
sys.path.insert(0, '${pythonDir}')
import json

from trading_bot.engine.order_executor import OrderExecutor
from trading_bot.config.settings_v2 import ConfigV2
from trading_bot.db.client import get_connection, query_one, query, DB_TYPE

try:
    config = ConfigV2.load()
    executor = OrderExecutor(testnet=False)

    # Get wallet balance
    wallet = executor.get_wallet_balance()

    # Get positions
    positions_result = executor.get_positions()

    # Get max_concurrent_trades from instance settings (respects DB_TYPE)
    instance_id = '${instanceId}'
    max_trades = 3  # default

    if instance_id:
        conn = get_connection()
        # Query instance settings JSON - works with both SQLite and PostgreSQL
        if DB_TYPE == 'postgres':
            row = query_one(conn, "SELECT settings FROM instances WHERE id = %s", (instance_id,))
        else:
            row = query_one(conn, "SELECT settings FROM instances WHERE id = ?", (instance_id,))

        if row:
            settings = row.get('settings') if isinstance(row, dict) else row[0]
            if settings:
                import json as json_mod
                settings_dict = json_mod.loads(settings) if isinstance(settings, str) else settings
                max_trades = int(settings_dict.get('trading.max_concurrent_trades', 3))
        conn.close()

    # Get last cycle using centralized client
    conn = get_connection()
    if DB_TYPE == 'postgres':
        last_cycle_row = query_one(conn, "SELECT started_at FROM cycles ORDER BY started_at DESC LIMIT 1", ())
    else:
        last_cycle_row = query_one(conn, "SELECT started_at FROM cycles ORDER BY started_at DESC LIMIT 1", ())
    last_cycle = None
    if last_cycle_row:
        last_cycle = last_cycle_row.get('started_at') if isinstance(last_cycle_row, dict) else last_cycle_row[0]
    conn.close()

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
    import traceback
    print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}))
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

