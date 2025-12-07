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
from trading_bot.db.client import get_connection, query_one, query, DB_TYPE, get_boolean_comparison

try:
    import sys

    # Get instance_id from query params
    instance_id = '${instanceId}'
    config = None

    if instance_id:
        # Load config from specific instance
        config = ConfigV2.from_instance(instance_id)
        print(f"[DEBUG] Config loaded from instance {instance_id}: paper_trading={config.trading.paper_trading}", file=sys.stderr)
    else:
        # Try to get first active instance
        conn = get_connection()
        is_active_check = get_boolean_comparison('is_active', True)
        first_instance = query_one(conn, f"SELECT id, settings FROM instances WHERE {is_active_check} LIMIT 1", ())
        conn.close()

        if first_instance:
            instance_id = first_instance.get('id') if isinstance(first_instance, dict) else first_instance[0]
            config = ConfigV2.from_instance(instance_id)
            print(f"[DEBUG] Config loaded from first active instance {instance_id}", file=sys.stderr)
        else:
            print(f"[ERROR] No active instance found", file=sys.stderr)
            raise Exception("No active instance found. Please create and activate an instance in the dashboard.")

    # Get max_concurrent_trades from config (REQUIRED - no defaults for trading settings)
    max_trades = config.trading.max_concurrent_trades
    print(f"[DEBUG] Max concurrent trades from config: {max_trades}", file=sys.stderr)

    # Check if paper trading mode
    is_paper_trading = config.trading.paper_trading
    print(f"[DEBUG] Paper trading mode: {is_paper_trading}", file=sys.stderr)

    if is_paper_trading:
        # In paper trading mode, get positions from database
        conn = get_connection()
        dry_run_check = get_boolean_comparison('dry_run', True)

        if DB_TYPE == 'postgres':
            positions_rows = query(conn, f"""
                SELECT symbol, side, entry_price, stop_loss, take_profit, quantity
                FROM trades
                WHERE instance_id = %s AND status = 'open' AND {dry_run_check}
            """, (instance_id,))
        else:
            positions_rows = query(conn, f"""
                SELECT symbol, side, entry_price, stop_loss, take_profit, quantity
                FROM trades
                WHERE instance_id = ? AND status = 'open' AND {dry_run_check}
            """, (instance_id,))
        conn.close()

        # Format positions like API response
        positions = []
        for row in positions_rows:
            positions.append({
                "symbol": row.get('symbol') if isinstance(row, dict) else row[0],
                "side": row.get('side') if isinstance(row, dict) else row[1],
                "size": row.get('quantity', 0) if isinstance(row, dict) else (row[5] if len(row) > 5 else 0),
                "entry_price": row.get('entry_price', 0) if isinstance(row, dict) else (row[2] if len(row) > 2 else 0),
                "mark_price": row.get('entry_price', 0) if isinstance(row, dict) else (row[2] if len(row) > 2 else 0),  # Use entry as mark for paper
                "pnl": 0,  # TODO: Calculate from current price
                "leverage": "1x",
            })

        wallet = {
            "wallet_balance": 10000,  # Mock wallet for paper trading
            "available": 10000,
            "equity": 10000,
        }
        positions_result = {"positions": positions}
    else:
        # In live mode, call Bybit API
        executor = OrderExecutor(testnet=False)
        print(f"[DEBUG] OrderExecutor initialized", file=sys.stderr)

        # Get wallet balance
        wallet = executor.get_wallet_balance()

        # Log wallet response for debugging
        print(f"[DEBUG] Wallet response: {wallet}", file=sys.stderr)

        # Get positions
        positions_result = executor.get_positions()

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

    # Check if wallet has error
    wallet_error = wallet.get("error")
    if wallet_error:
        print(f"[ERROR] Wallet API error: {wallet_error}", file=sys.stderr)

    status = {
        "running": False,  # TODO: Check actual process status
        "mode": "paper" if config.trading.paper_trading else "live",
        "network": "mainnet",
        "uptime_seconds": None,
        "wallet": {
            "balance_usdt": wallet.get("wallet_balance", 0) if not wallet_error else 0,
            "available_usdt": wallet.get("available", 0) if not wallet_error else 0,
            "equity_usdt": wallet.get("equity", 0) if not wallet_error else 0,
        },
        "positions": positions_result.get("positions", []),
        "open_orders": [],  # TODO: Add open orders query
        "slots": {
            "used": len(positions_result.get("positions", [])),
            "max": max_trades,
            "available": max_trades - len(positions_result.get("positions", [])),
        },
        "last_cycle": last_cycle,
        "error": wallet_error,  # Include wallet error if present
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
    let resolved = false;

    // Set timeout to prevent hanging (8 seconds to stay under 10s Railway timeout)
    const timeout = setTimeout(() => {
      if (!resolved) {
        resolved = true;
        pythonProcess.kill();
        resolve(NextResponse.json(
          { error: 'Request timeout - API call took too long' },
          { status: 504 }
        ));
      }
    }, 8000);

    pythonProcess.stdout.on('data', (data) => {
      output += data.toString();
    });

    pythonProcess.stderr.on('data', (data) => {
      errorOutput += data.toString();
    });

    pythonProcess.on('close', (code) => {
      if (resolved) return; // Already timed out
      clearTimeout(timeout);
      resolved = true;

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

