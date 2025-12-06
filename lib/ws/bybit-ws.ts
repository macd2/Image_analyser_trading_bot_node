import WebSocket from 'ws';
import crypto from 'crypto';
import { EventEmitter } from 'events';

export interface BybitWSConfig {
  apiKey?: string;
  apiSecret?: string;
  testnet?: boolean;
}

export interface TickerData {
  symbol: string;
  lastPrice: string;
  price24hPcnt: string;
  highPrice24h: string;
  lowPrice24h: string;
  volume24h: string;
  markPrice: string;
  bid1Price: string;
  ask1Price: string;
}

export interface PositionData {
  symbol: string;
  side: string;
  size: string;
  entryPrice: string;
  markPrice: string;
  unrealisedPnl: string;
  leverage: string;
  positionValue: string;
  liqPrice: string;
}

export interface WalletData {
  coin: string;
  walletBalance: string;
  availableToWithdraw: string;
  equity: string;
  unrealisedPnl: string;
}

export class BybitWebSocket extends EventEmitter {
  private publicWs: WebSocket | null = null;
  private privateWs: WebSocket | null = null;
  private config: BybitWSConfig;
  private reconnectAttempts = 0;
  private pingInterval: NodeJS.Timeout | null = null;
  private symbols: string[] = [];

  constructor(config: BybitWSConfig = {}) {
    super();
    this.config = config;
  }

  async connectPublic(symbols: string[]): Promise<void> {
    this.symbols = symbols;
    const url = this.config.testnet
      ? 'wss://stream-testnet.bybit.com/v5/public/linear'
      : 'wss://stream.bybit.com/v5/public/linear';

    try {
      this.publicWs = new WebSocket(url);

      // IMPORTANT: Add error handler BEFORE any other handlers to prevent uncaught exceptions
      this.publicWs.on('error', (err: Error & { code?: string }) => {
        // Silently handle network errors - just schedule reconnect
        const isNetworkError = err.code === 'ETIMEDOUT' || err.code === 'ENETUNREACH' ||
          err.message?.includes('ETIMEDOUT') || err.message?.includes('ENETUNREACH') ||
          err.message?.includes('AggregateError');
        if (!isNetworkError) {
          console.error('[Bybit WS] Public error:', err.message);
        }
        // Error handler prevents uncaught exception - reconnect is handled by close event
      });

      this.publicWs.on('open', () => {
        console.log('[Bybit WS] Public stream connected');
        const topics = symbols.map(s => `tickers.${s}`);
        this.publicWs!.send(JSON.stringify({ op: 'subscribe', args: topics }));
        this.startHeartbeat(this.publicWs!);
        this.reconnectAttempts = 0;
      });

      this.publicWs.on('message', (data) => {
        try {
          const msg = JSON.parse(data.toString());
          if (msg.topic?.startsWith('tickers.')) {
            this.emit('ticker', msg.data as TickerData);
          }
        } catch (e) {
          console.error('[Bybit WS] Parse error:', e);
        }
      });

      this.publicWs.on('close', () => {
        console.log('[Bybit WS] Public stream disconnected');
        this.scheduleReconnect('public');
      });
    } catch (err) {
      console.error('[Bybit WS] Failed to create WebSocket:', err);
      this.scheduleReconnect('public');
    }
  }

  async connectPrivate(): Promise<void> {
    if (!this.config.apiKey || !this.config.apiSecret) {
      console.log('[Bybit WS] No API credentials, skipping private stream');
      return;
    }

    const url = this.config.testnet
      ? 'wss://stream-testnet.bybit.com/v5/private'
      : 'wss://stream.bybit.com/v5/private';

    try {
      this.privateWs = new WebSocket(url);

      // IMPORTANT: Add error handler BEFORE any other handlers to prevent uncaught exceptions
      this.privateWs.on('error', (err: Error & { code?: string }) => {
        const isNetworkError = err.code === 'ETIMEDOUT' || err.code === 'ENETUNREACH' ||
          err.message?.includes('ETIMEDOUT') || err.message?.includes('ENETUNREACH') ||
          err.message?.includes('AggregateError');
        if (!isNetworkError) {
          console.error('[Bybit WS] Private error:', err.message);
        }
      });

      this.privateWs.on('open', () => {
        console.log('[Bybit WS] Private stream connected');
        this.authenticate();
      });

      this.privateWs.on('message', (data) => {
        try {
          const msg = JSON.parse(data.toString());
          if (msg.op === 'auth' && msg.success) {
            console.log('[Bybit WS] Authenticated');
            this.privateWs!.send(JSON.stringify({
              op: 'subscribe',
              args: ['position', 'order', 'wallet']
            }));
          }
          if (msg.topic === 'position') this.emit('position', msg.data);
          if (msg.topic === 'order') this.emit('order', msg.data);
          if (msg.topic === 'wallet') this.emit('wallet', msg.data);
        } catch (e) {
          console.error('[Bybit WS] Parse error:', e);
        }
      });

      this.privateWs.on('close', () => {
        console.log('[Bybit WS] Private stream disconnected');
        this.scheduleReconnect('private');
      });
    } catch (err) {
      console.error('[Bybit WS] Failed to create private WebSocket:', err);
      this.scheduleReconnect('private');
    }
  }

  private authenticate(): void {
    const expires = Date.now() + 10000;
    const signature = crypto
      .createHmac('sha256', this.config.apiSecret!)
      .update(`GET/realtime${expires}`)
      .digest('hex');
    this.privateWs!.send(JSON.stringify({
      op: 'auth',
      args: [this.config.apiKey, expires, signature]
    }));
  }

  private startHeartbeat(ws: WebSocket): void {
    if (this.pingInterval) clearInterval(this.pingInterval);
    this.pingInterval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ op: 'ping' }));
      }
    }, 20000);
  }

  private scheduleReconnect(type: 'public' | 'private'): void {
    if (this.reconnectAttempts >= 5) {
      console.error('[Bybit WS] Max reconnect attempts');
      return;
    }
    const delay = Math.pow(2, this.reconnectAttempts) * 1000;
    this.reconnectAttempts++;
    console.log(`[Bybit WS] Reconnecting ${type} in ${delay}ms...`);
    setTimeout(() => {
      if (type === 'public') this.connectPublic(this.symbols);
      else this.connectPrivate();
    }, delay);
  }

  disconnect(): void {
    if (this.pingInterval) clearInterval(this.pingInterval);
    this.publicWs?.close();
    this.privateWs?.close();
  }
}

