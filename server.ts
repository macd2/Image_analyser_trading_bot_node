import { createServer } from 'http';
import { parse } from 'url';
import next from 'next';
import fs from 'fs';
import path from 'path';
import { initSocketServer } from './lib/ws/socket-server';

// Auto-start simulator monitor on server boot
function startSimulatorMonitor() {
  const statusFile = path.join(process.cwd(), 'data', 'simulator_status.json');
  const dir = path.dirname(statusFile);

  // Ensure data directory exists
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }

  const status = {
    running: true,
    last_check: null,
    trades_checked: 0,
    trades_closed: 0,
    next_check: null,
    results: []
  };

  fs.writeFileSync(statusFile, JSON.stringify(status, null, 2));
  console.log('  ➜  Simulator: Auto-monitor started');
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

    // Auto-start the simulator monitor
    startSimulatorMonitor();
  });
});

