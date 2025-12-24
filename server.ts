import { createServer } from 'http';
import { parse } from 'url';
import next from 'next';
import fs from 'fs';
import path from 'path';
import { initSocketServer } from './lib/ws/socket-server';

const STATUS_FILE = path.join(process.cwd(), 'data', 'simulator_status.json');
const AUTO_CLOSE_INTERVAL_MS = 60000; // Check every 60 seconds
let isAutoCloseCheckRunning = false; // Prevent overlapping checks

// Read simulator status
function getSimulatorStatus(): { running: boolean; last_check?: string | null } {
  try {
    if (fs.existsSync(STATUS_FILE)) {
      return JSON.parse(fs.readFileSync(STATUS_FILE, 'utf-8'));
    }
  } catch {
    // Ignore read errors
  }
  return { running: false };
}

// Update simulator status after check
function updateSimulatorStatus(tradesChecked: number, tradesClosed: number, results: unknown[] = [], tradesFilled: number = 0) {
  try {
    const current = getSimulatorStatus();
    const updated = {
      ...current,
      // Preserve the running state - don't overwrite it
      last_check: new Date().toISOString(),
      trades_checked: tradesChecked,
      trades_closed: tradesClosed,
      trades_filled: tradesFilled,
      next_check: Date.now() / 1000 + AUTO_CLOSE_INTERVAL_MS / 1000,
      results: results.slice(0, 20) // Keep last 20 results for UI
    };
    fs.writeFileSync(STATUS_FILE, JSON.stringify(updated, null, 2));
  } catch {
    // Ignore write errors
  }
}

// Background auto-close check - respects status.running from UI toggle
// When auto mode is ON in UI, this runs regardless of which page user is on
async function runAutoCloseCheck(baseUrl: string) {
  // Prevent overlapping checks if previous one is still running
  if (isAutoCloseCheckRunning) {
    console.log(`  ➜  Simulator: Previous check still running, skipping this interval - ${new Date().toISOString()}`);
    return;
  }

  const status = getSimulatorStatus();
  if (!status.running) {
    console.log(`  ➜  Simulator: Auto mode is OFF (skipping check) - ${new Date().toISOString()}`);
    return; // Auto mode is OFF in UI
  }

  isAutoCloseCheckRunning = true;
  const checkStartTime = Date.now();
  console.log(`  ➜  Simulator: Running background check... - ${new Date().toISOString()}`);

  try {
    const res = await fetch(`${baseUrl}/api/bot/simulator/auto-close`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });

    if (res.ok) {
      const data = await res.json();
      const checkDuration = ((Date.now() - checkStartTime) / 1000).toFixed(2);
      updateSimulatorStatus(data.checked || 0, data.closed || 0, data.results || [], data.filled || 0);
      console.log(`  ➜  Simulator: Checked ${data.checked || 0} trades, Filled ${data.filled || 0}, Closed ${data.closed || 0} (took ${checkDuration}s) - ${new Date().toISOString()}`);
    } else {
      console.error(`  ➜  Simulator: Auto-close API returned ${res.status} - ${new Date().toISOString()}`);
    }
  } catch (err) {
    console.error(`  ➜  Simulator: Background check failed: ${err instanceof Error ? err.message : String(err)} - ${new Date().toISOString()}`);
  } finally {
    isAutoCloseCheckRunning = false;
  }
}

// Auto-start simulator monitor on server boot
function startSimulatorMonitor(port: number) {
  const dir = path.dirname(STATUS_FILE);

  // Ensure data directory exists
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }

  const status = {
    running: true,
    last_check: null,
    trades_checked: 0,
    trades_closed: 0,
    next_check: Date.now() / 1000 + AUTO_CLOSE_INTERVAL_MS / 1000,
    results: []
  };

  fs.writeFileSync(STATUS_FILE, JSON.stringify(status, null, 2));
  console.log(`  ➜  Simulator: Auto-monitor started (background interval: ${AUTO_CLOSE_INTERVAL_MS / 1000}s)`);

  // Start background interval for auto-close checks
  const baseUrl = `http://localhost:${port}`;

  // Run immediately on startup (don't wait 60 seconds)
  setTimeout(() => runAutoCloseCheck(baseUrl), 5000); // Wait 5s for server to be ready

  // Then run every 60 seconds
  setInterval(() => runAutoCloseCheck(baseUrl), AUTO_CLOSE_INTERVAL_MS);
}

// Handle uncaught exceptions from WebSocket timeouts and DB pooler errors gracefully
process.on('uncaughtException', (err: Error & { code?: string }) => {
  // Ignore network timeout errors - they're handled by reconnect logic
  const isNetworkError =
    err.code === 'ETIMEDOUT' ||
    err.code === 'ENETUNREACH' ||
    err.message?.includes('ETIMEDOUT') ||
    err.message?.includes('ENETUNREACH') ||
    err.name === 'AggregateError';

  // Ignore Supabase pooler connection errors - pool will auto-reconnect
  // XX000 = DbHandler exited (Supabase pooler issue)
  // 57P01 = admin_shutdown, 57P02 = crash_shutdown
  const isPoolerError =
    err.code === 'XX000' ||
    err.code === '57P01' ||
    err.code === '57P02' ||
    err.message?.includes('DbHandler exited');

  if (isNetworkError) {
    // Silently ignore - WebSocket will auto-reconnect
    return;
  }

  if (isPoolerError) {
    console.warn('[Server] PostgreSQL pooler connection reset - will auto-reconnect');
    return;
  }

  console.error('Uncaught Exception:', err);
});

process.on('unhandledRejection', (reason) => {
  // Ignore network-related rejections
  const msg = String(reason);
  if (msg.includes('ETIMEDOUT') || msg.includes('ENETUNREACH') || msg.includes('AggregateError')) {
    return;
  }
  // Ignore Supabase pooler errors
  if (msg.includes('DbHandler exited') || msg.includes('XX000')) {
    console.warn('[Server] PostgreSQL pooler connection reset - will auto-reconnect');
    return;
  }
  console.error('Unhandled Rejection:', reason);
});

const dev = process.env.NODE_ENV !== 'production';
const hostname = 'localhost';
const port = parseInt(process.env.PORT || '3000', 10);

const app = next({ dev, hostname, port });
const handle = app.getRequestHandler();

app.prepare().then(() => {
  const httpServer = createServer(async (req, res) => {
    try {
      const parsedUrl = parse(req.url!, true);
      await handle(req, res, parsedUrl);
    } catch (err) {
      console.error('Error handling request:', err);
      res.statusCode = 500;
      res.end('internal server error');
    }
  });

  // Initialize Socket.io with Bybit WebSocket
  initSocketServer(httpServer);

  httpServer.listen(port, () => {
    console.log(`
  🚀 V2 Trading Bot Dashboard (with Real-Time)

  ➜  Local:   http://${hostname}:${port}
  ➜  Mode:    ${dev ? 'development' : 'production'}
  ➜  WS:      Bybit ${process.env.BYBIT_TESTNET === 'true' ? '(testnet)' : '(mainnet)'}
    `);

    // Auto-start the simulator monitor with background interval
    startSimulatorMonitor(port);
  });
});

