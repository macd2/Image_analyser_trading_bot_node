'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { io, Socket } from 'socket.io-client';

export interface Ticker {
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

export interface Position {
  symbol: string;
  side: string;
  size: string;
  entryPrice: string;
  markPrice?: string;
  unrealisedPnl: string;
  leverage?: string;
  positionValue?: string;
  liqPrice?: string;
}

export interface PendingOrder {
  symbol: string;
  side: string;
  orderQty: string | null;
  qty?: string;
  price: string;
  orderStatus: string;
  orderId?: string;
  createdTime?: string;  // milliseconds since epoch
  updatedTime?: string;
  orderType?: string;
  timeInForce?: string;
  takeProfit?: string;
  stopLoss?: string;
  cumExecQty?: string;
  avgPrice?: string;
  leavesQty?: string;
}

export interface Wallet {
  coin: string;
  walletBalance: string;
  availableToWithdraw: string;
  equity: string;
  unrealisedPnl: string;
}

export interface InstanceStatusUpdate {
  instanceId: string;
  runId: string | null;
  isRunning: boolean;
  reason?: 'crashed' | 'stopped' | 'killed';
}

interface RealtimeState {
  tickers: Record<string, Ticker>;
  positions: Position[];
  pendingOrders: PendingOrder[];
  wallet: Wallet | null;
  connected: boolean;
  lastUpdate: Date | null;
  runningInstances: string[];
}

// Merge ticker data, keeping existing values for missing fields
function mergeTicker(existing: Ticker | undefined, incoming: Ticker): Ticker {
  if (!existing) return incoming;
  return {
    symbol: incoming.symbol || existing.symbol,
    lastPrice: incoming.lastPrice || existing.lastPrice,
    price24hPcnt: incoming.price24hPcnt || existing.price24hPcnt,
    highPrice24h: incoming.highPrice24h || existing.highPrice24h,
    lowPrice24h: incoming.lowPrice24h || existing.lowPrice24h,
    volume24h: incoming.volume24h || existing.volume24h,
    markPrice: incoming.markPrice || existing.markPrice,
    bid1Price: incoming.bid1Price || existing.bid1Price,
    ask1Price: incoming.ask1Price || existing.ask1Price,
  };
}

export function useRealtime() {
  const [socket, setSocket] = useState<Socket | null>(null);
  const [state, setState] = useState<RealtimeState>({
    tickers: {},
    positions: [],
    pendingOrders: [],
    wallet: null,
    connected: false,
    lastUpdate: null,
    runningInstances: []
  });
  const tickersRef = useRef<Record<string, Ticker>>({});
  const instanceStatusCallbacksRef = useRef<Set<(update: InstanceStatusUpdate) => void>>(new Set());

  const connect = useCallback(() => {
    const s = io({
      path: '/api/socketio',
      transports: ['websocket', 'polling']
    });

    s.on('connect', () => {
      console.log('[Realtime] Connected');
      setState(prev => ({ ...prev, connected: true }));
    });

    s.on('disconnect', () => {
      console.log('[Realtime] Disconnected');
      setState(prev => ({ ...prev, connected: false }));
    });

    s.on('init', (data: { tickers: Record<string, Ticker>; positions: Position[]; pendingOrders?: PendingOrder[]; wallet?: Wallet | null; runningInstances?: string[] }) => {
      console.log('[Realtime] Init data received:', {
        tickerCount: Object.keys(data.tickers).length,
        positionCount: data.positions.length,
        pendingOrderCount: data.pendingOrders?.length || 0,
        positions: data.positions.map(p => ({ symbol: p.symbol, side: p.side, size: p.size }))
      });
      Object.entries(data.tickers).forEach(([symbol, ticker]) => {
        tickersRef.current[symbol] = mergeTicker(tickersRef.current[symbol], ticker);
      });
      setState(prev => ({
        ...prev,
        tickers: { ...tickersRef.current },
        positions: data.positions,
        pendingOrders: data.pendingOrders || [],
        wallet: data.wallet || null,
        runningInstances: data.runningInstances || [],
        lastUpdate: new Date()
      }));
    });

    s.on('ticker', (data: Ticker) => {
      tickersRef.current[data.symbol] = mergeTicker(tickersRef.current[data.symbol], data);
      setState(prev => ({
        ...prev,
        tickers: { ...tickersRef.current },
        lastUpdate: new Date()
      }));
    });

    s.on('positions', (data: Position[]) => {
      console.log('[Realtime] Positions update:', {
        count: data.length,
        positions: data.map(p => ({ symbol: p.symbol, side: p.side, size: p.size }))
      });
      setState(prev => ({
        ...prev,
        positions: data,
        lastUpdate: new Date()
      }));
    });

    s.on('wallet', (data: Wallet) => {
      console.log('[Realtime] Wallet update:', data);
      setState(prev => ({
        ...prev,
        wallet: data,
        lastUpdate: new Date()
      }));
    });

    s.on('trades', (data: { positions: Position[]; pendingOrders: PendingOrder[] }) => {
      setState(prev => ({
        ...prev,
        positions: data.positions,
        pendingOrders: data.pendingOrders,
        lastUpdate: new Date()
      }));
    });

    // Listen for instance status updates from the process monitor
    s.on('instance_status', (update: InstanceStatusUpdate) => {
      console.log('[Realtime] Instance status update:', update);

      // Update running instances list
      setState(prev => {
        const newRunning = update.isRunning
          ? [...new Set([...prev.runningInstances, update.instanceId])]
          : prev.runningInstances.filter(id => id !== update.instanceId);
        return { ...prev, runningInstances: newRunning };
      });

      // Notify all registered callbacks
      instanceStatusCallbacksRef.current.forEach(cb => cb(update));
    });

    setSocket(s);
    return s;
  }, []);

  useEffect(() => {
    const s = connect();
    return () => {
      s.disconnect();
    };
  }, [connect]);

  // Subscribe to instance status updates
  const onInstanceStatus = useCallback((callback: (update: InstanceStatusUpdate) => void) => {
    instanceStatusCallbacksRef.current.add(callback);
    return () => {
      instanceStatusCallbacksRef.current.delete(callback);
    };
  }, []);

  // Check if a specific instance is running
  const isInstanceRunning = useCallback((instanceId: string) => {
    return state.runningInstances.includes(instanceId);
  }, [state.runningInstances]);

  return {
    tickers: state.tickers,
    positions: state.positions,
    pendingOrders: state.pendingOrders,
    wallet: state.wallet,
    connected: state.connected,
    lastUpdate: state.lastUpdate,
    runningInstances: state.runningInstances,
    socket,
    onInstanceStatus,
    isInstanceRunning,
    reconnect: () => {
      socket?.disconnect()
      connect()
    }
  }
}

