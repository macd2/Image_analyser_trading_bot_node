import { Server as HTTPServer } from 'http';
import { Server as SocketIOServer } from 'socket.io';
import { BybitWebSocket, TickerData, PositionData, WalletData } from './bybit-ws';
import { processMonitor, ProcessStatusUpdate } from './process-monitor';
import { updateRunStatusByInstanceId, getRunningRuns, getRunningRunByInstanceId, getInstances } from '../db/trading-db';
import { restoreProcessStates } from '../process-state';

let io: SocketIOServer | null = null;
let bybit: BybitWebSocket | null = null;

// Dynamic watchlist - will be populated from active instances
let currentWatchlist: string[] = [];

// Store latest data
const tickers: Record<string, TickerData> = {};
const positions: PositionData[] = [];
let wallet: WalletData | null = null;

export function getSocketServer(): SocketIOServer | null {
  return io;
}

/**
 * Get all unique symbols from active instances
 */
async function getSymbolsFromInstances(): Promise<string[]> {
  try {
    const instances = await getInstances(true); // Get active instances only
    const symbolsSet = new Set<string>();

    for (const instance of instances) {
      if (instance.symbols) {
        try {
          const symbols = JSON.parse(instance.symbols);
          if (Array.isArray(symbols)) {
            symbols.forEach(s => symbolsSet.add(s));
          }
        } catch (e) {
          console.error(`[Socket.io] Failed to parse symbols for instance ${instance.name}:`, e);
        }
      }
    }

    const symbolsList = Array.from(symbolsSet);
    console.log(`[Socket.io] Found ${symbolsList.length} unique symbols from ${instances.length} active instances:`, symbolsList);
    return symbolsList;
  } catch (error) {
    console.error('[Socket.io] Failed to get symbols from instances:', error);
    // Fallback to common symbols
    return ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'];
  }
}

/**
 * Update WebSocket subscriptions with new symbol list
 */
export async function updateWatchlist(): Promise<void> {
  const newSymbols = await getSymbolsFromInstances();

  // Only update if symbols changed
  const symbolsChanged = JSON.stringify(newSymbols.sort()) !== JSON.stringify(currentWatchlist.sort());

  if (symbolsChanged && bybit) {
    console.log('[Socket.io] Watchlist changed, reconnecting with new symbols...');
    currentWatchlist = newSymbols;

    // Reconnect with new symbols
    try {
      await bybit.connectPublic(currentWatchlist);
    } catch (error) {
      console.error('[Socket.io] Failed to update watchlist:', error);
    }
  }
}

/**
 * Emit a log message to all connected clients
 */
export function emitLog(log: string, instanceId?: string): void {
  if (io) {
    io.emit('bot_log', { log, instanceId, timestamp: Date.now() });
  }
}

export function initSocketServer(httpServer: HTTPServer): SocketIOServer {
  if (io) return io;

  io = new SocketIOServer(httpServer, {
    cors: { origin: '*', methods: ['GET', 'POST'] },
    path: '/api/socketio'
  });

  // Initialize Process Monitor for bot status tracking
  initProcessMonitor();

  // Initialize Bybit WebSocket with error handling
  const initBybitConnection = async () => {
    try {
      const hasApiKey = !!process.env.BYBIT_API_KEY;
      const hasApiSecret = !!process.env.BYBIT_API_SECRET;

      console.log('[Socket.io] Bybit credentials check:', {
        hasApiKey,
        hasApiSecret,
        testnet: process.env.BYBIT_TESTNET === 'true'
      });

      bybit = new BybitWebSocket({
        apiKey: process.env.BYBIT_API_KEY,
        apiSecret: process.env.BYBIT_API_SECRET,
        testnet: process.env.BYBIT_TESTNET === 'true'
      });

      // Get symbols from active instances
      currentWatchlist = await getSymbolsFromInstances();

      // Connect to Bybit with dynamic watchlist
      bybit.connectPublic(currentWatchlist).catch(() => {
        // Silently catch - reconnect logic will handle it
      });

      if (hasApiKey && hasApiSecret) {
        console.log('[Socket.io] Connecting to Bybit private stream for wallet updates...');
        bybit.connectPrivate().catch(() => {
          // Silently catch - reconnect logic will handle it
        });
      } else {
        console.warn('[Socket.io] ⚠️ No Bybit API credentials - wallet updates will NOT be available via WebSocket');
      }
    } catch (error) {
      console.error('[Socket.io] Failed to initialize Bybit connection:', error);
    }
  };

  // Initialize connection asynchronously
  initBybitConnection();
    // Forward ticker updates
    bybit.on('ticker', (data: TickerData) => {
      tickers[data.symbol] = data;
      io?.emit('ticker', data);
    });

    // Forward position updates
    bybit.on('position', (data: PositionData[]) => {
      const openPositions = data.filter(p => parseFloat(p.size) !== 0);
      positions.length = 0;
      positions.push(...openPositions);
      io?.emit('positions', openPositions);
    });

    // Forward order updates
    bybit.on('order', (data: unknown) => {
      io?.emit('order', data);
    });

    // Forward wallet updates
    bybit.on('wallet', (data: any) => {
      console.log('[Socket.io] Received wallet event from Bybit:', JSON.stringify(data).substring(0, 200));

      // Bybit sends wallet data as array with coin array inside
      // Extract USDT wallet data
      if (Array.isArray(data)) {
        for (const walletData of data) {
          const coins = walletData.coin || [];
          for (const coinData of coins) {
            if (coinData.coin === 'USDT') {
              wallet = {
                coin: coinData.coin,
                walletBalance: coinData.walletBalance,
                availableToWithdraw: coinData.availableToWithdraw,
                equity: coinData.equity,
                unrealisedPnl: coinData.unrealisedPnl || '0'
              };
              io?.emit('wallet', wallet);
              console.log('[Socket.io] ✅ Wallet update emitted to clients:', {
                balance: wallet.walletBalance,
                available: wallet.availableToWithdraw,
                equity: wallet.equity
              });
              break;
            }
          }
        }
      } else {
        console.warn('[Socket.io] ⚠️ Unexpected wallet data format:', typeof data);
      }
    });
  } catch (err) {
    console.error('[Socket.io] Failed to initialize Bybit WS:', err);
    // Continue without real-time data - dashboard will still work
  }

  // Handle client connections
  io.on('connection', (socket) => {
    console.log('[Socket.io] Client connected:', socket.id);

    // Send current state on connect (include bot process statuses)
    socket.emit('init', {
      tickers,
      positions,
      wallet,
      runningInstances: processMonitor.getRunningInstanceIds()
    });

    socket.on('disconnect', () => {
      console.log('[Socket.io] Client disconnected:', socket.id);
    });
  });

  console.log('[Socket.io] Server initialized');
  return io;
}

/**
 * Initialize process monitor and sync with database
 */
function initProcessMonitor(): void {
  // Restore process states from persistent storage
  console.log('[ProcessMonitor] Restoring process states from disk...');
  const restored = restoreProcessStates();

  if (restored.length > 0) {
    console.log(`[ProcessMonitor] Found ${restored.length} running process(es)`);
    // Register with process monitor
    for (const state of restored) {
      processMonitor.registerProcess(state.instanceId, state.pid);
      console.log(`[ProcessMonitor] Restored: instance=${state.instanceId}, PID=${state.pid}`);
    }
  } else {
    console.log('[ProcessMonitor] No running processes to restore');
  }

  // Start the process monitor
  processMonitor.start();

  // On status updates, update the database and emit to clients
  processMonitor.on('status', async (update: ProcessStatusUpdate) => {
    console.log(`[ProcessMonitor] Status update: instance=${update.instanceId}, alive=${update.isAlive}, reason=${update.reason}`);

    // Update database when process dies - update by instance_id
    if (!update.isAlive && update.reason) {
      try {
        const dbStatus = update.reason === 'crashed' ? 'crashed' : 'stopped';
        const updated = await updateRunStatusByInstanceId(update.instanceId, dbStatus, `Process ${update.reason}`);
        console.log(`[ProcessMonitor] Updated DB: instance=${update.instanceId} -> ${dbStatus} (${updated} runs affected)`);
      } catch (err) {
        console.error('[ProcessMonitor] Failed to update DB:', err);
      }
    }

    // Get current run_id for the instance (if any)
    const currentRun = await getRunningRunByInstanceId(update.instanceId);

    // Emit to all connected clients
    io?.emit('instance_status', {
      instanceId: update.instanceId,
      runId: currentRun?.id || null,
      isRunning: update.isAlive,
      reason: update.reason
    });
  });

  // On startup, check for stale "running" entries in DB and clean them up
  syncStaleRuns();
}

/**
 * Sync stale runs on startup - mark runs as crashed if their process is not running
 * Uses persistent process state to determine which processes are actually running
 */
async function syncStaleRuns(): Promise<void> {
  try {
    const runningRuns = await getRunningRuns();
    // Get tracked instances from process monitor (which was restored from persistent state)
    const trackedInstanceIds = processMonitor.getRunningInstanceIds();

    console.log(`[ProcessMonitor] Syncing stale runs: ${runningRuns.length} DB runs, ${trackedInstanceIds.length} tracked processes`);

    for (const run of runningRuns) {
      // If this run is marked as running but we don't have a process for its instance, mark as crashed
      if (!run.instance_id || !trackedInstanceIds.includes(run.instance_id)) {
        console.log(`[ProcessMonitor] Stale run detected: ${run.id} (instance: ${run.instance_id}) - marking as crashed`);
        if (run.instance_id) {
          await updateRunStatusByInstanceId(run.instance_id, 'crashed', 'Process not found on startup');
        }
      }
    }
  } catch (err) {
    console.error('[ProcessMonitor] Failed to sync stale runs:', err);
  }
}

export function shutdownSocketServer(): void {
  processMonitor.stop();
  bybit?.disconnect();
  io?.close();
  io = null;
  bybit = null;
}

