# UI Components with shadcn/ui

## Design System

**Theme**: Dark mode trading dashboard
**Colors**: Green (profit), Red (loss), Neutral grays
**Font**: Inter (clean, readable numbers)

---

## Setup

```bash
# Initialize shadcn/ui
pnpm dlx shadcn@latest init

# Select options:
# - Style: New York
# - Base color: Neutral
# - CSS variables: Yes

# Install core components
pnpm dlx shadcn@latest add button card badge table skeleton \
  dialog dropdown-menu tabs toast input select form avatar \
  tooltip popover command sheet separator scroll-area
```

---

## Component Architecture

```
components/
├── ui/                    # shadcn base components
│   ├── button.tsx
│   ├── card.tsx
│   └── ...
├── trading/               # Trading-specific
│   ├── positions-table.tsx
│   ├── trade-form.tsx
│   ├── pnl-display.tsx
│   └── price-ticker.tsx
├── dashboard/             # Dashboard widgets
│   ├── stats-card.tsx
│   ├── balance-widget.tsx
│   └── recent-trades.tsx
└── charts/                # Chart components
    ├── pnl-chart.tsx
    └── candlestick.tsx
```

---

## Core Trading Components

### 1. PositionsTable

```tsx
// components/trading/positions-table.tsx
'use client';

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface Position {
  symbol: string;
  side: 'LONG' | 'SHORT';
  quantity: number;
  entryPrice: number;
  currentPrice: number;
  unrealizedPnl: number;
  unrealizedPnlPercent: number;
}

export function PositionsTable({ positions }: { positions: Position[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Symbol</TableHead>
          <TableHead>Side</TableHead>
          <TableHead className="text-right">Size</TableHead>
          <TableHead className="text-right">Entry</TableHead>
          <TableHead className="text-right">Current</TableHead>
          <TableHead className="text-right">P&L</TableHead>
          <TableHead></TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {positions.map((pos) => (
          <TableRow key={pos.symbol}>
            <TableCell className="font-medium">{pos.symbol}</TableCell>
            <TableCell>
              <Badge variant={pos.side === 'LONG' ? 'default' : 'destructive'}>
                {pos.side}
              </Badge>
            </TableCell>
            <TableCell className="text-right font-mono">{pos.quantity}</TableCell>
            <TableCell className="text-right font-mono">${pos.entryPrice.toFixed(2)}</TableCell>
            <TableCell className="text-right font-mono">${pos.currentPrice.toFixed(2)}</TableCell>
            <TableCell className={cn(
              "text-right font-mono font-medium",
              pos.unrealizedPnl >= 0 ? "text-green-500" : "text-red-500"
            )}>
              {pos.unrealizedPnl >= 0 ? '+' : ''}{pos.unrealizedPnlPercent.toFixed(2)}%
            </TableCell>
            <TableCell>
              <Button variant="ghost" size="sm">Close</Button>
            </TableCell>
          </TableRow>
        ))}
        {positions.length === 0 && (
          <TableRow>
            <TableCell colSpan={7} className="text-center text-muted-foreground py-8">
              No open positions
            </TableCell>
          </TableRow>
        )}
      </TableBody>
    </Table>
  );
}
```

### 2. StatsCard

```tsx
// components/dashboard/stats-card.tsx
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

interface StatsCardProps {
  title: string;
  value: string | number;
  change?: number;
  icon?: React.ReactNode;
}

export function StatsCard({ title, value, change, icon }: StatsCardProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
        {icon}
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        {change !== undefined && (
          <p className={cn(
            "text-xs",
            change >= 0 ? "text-green-500" : "text-red-500"
          )}>
            {change >= 0 ? '+' : ''}{change.toFixed(2)}% from last period
          </p>
        )}
      </CardContent>
    </Card>
  );
}
```

### 3. PnLDisplay

```tsx
// components/trading/pnl-display.tsx
import { cn } from '@/lib/utils';

interface PnLDisplayProps {
  value: number;
  percent?: number;
  size?: 'sm' | 'md' | 'lg';
}

export function PnLDisplay({ value, percent, size = 'md' }: PnLDisplayProps) {
  const isPositive = value >= 0;
  const sizeClasses = {
    sm: 'text-sm',
    md: 'text-lg',
    lg: 'text-2xl',
  };

  return (
    <div className={cn(
      "font-mono font-medium",
      sizeClasses[size],
      isPositive ? "text-green-500" : "text-red-500"
    )}>
      <span>{isPositive ? '+' : ''}{value.toFixed(2)}</span>
      {percent !== undefined && (
        <span className="text-muted-foreground ml-1">
          ({isPositive ? '+' : ''}{percent.toFixed(2)}%)
        </span>
      )}
    </div>
  );
}
```

---

## Dashboard Layout

```tsx
// app/(dashboard)/layout.tsx
import { Sidebar } from '@/components/dashboard/sidebar';
import { Header } from '@/components/dashboard/header';

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen bg-background">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-auto p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
```

```tsx
// components/dashboard/sidebar.tsx
import Link from 'next/link';
import { cn } from '@/lib/utils';
import { LayoutDashboard, TrendingUp, History, Settings, Bot } from 'lucide-react';

const navItems = [
  { href: '/', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/positions', label: 'Positions', icon: TrendingUp },
  { href: '/trades', label: 'Trade History', icon: History },
  { href: '/analysis', label: 'Analysis', icon: Bot },
  { href: '/settings', label: 'Settings', icon: Settings },
];

export function Sidebar() {
  return (
    <aside className="w-64 border-r bg-card">
      <div className="p-6">
        <h1 className="text-xl font-bold">Trading Bot</h1>
      </div>
      <nav className="space-y-1 px-3">
        {navItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-md text-sm",
              "hover:bg-accent transition-colors"
            )}
          >
            <item.icon className="h-4 w-4" />
            {item.label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
```

---

## Real-Time Updates Hook (Socket.io)

```tsx
// hooks/use-positions.ts
'use client';

import { useEffect, useState } from 'react';
import { io, Socket } from 'socket.io-client';
import { useQuery, useQueryClient } from '@tanstack/react-query';

export function usePositions() {
  const queryClient = useQueryClient();

  // Initial fetch with React Query
  const { data: positions = [], isLoading } = useQuery({
    queryKey: ['positions'],
    queryFn: async () => {
      const res = await fetch('/api/positions');
      return res.json();
    },
  });

  // Real-time updates via Socket.io
  useEffect(() => {
    const socket: Socket = io();

    socket.emit('subscribe:positions');

    socket.on('positions:update', (updatedPositions) => {
      queryClient.setQueryData(['positions'], updatedPositions);
    });

    return () => {
      socket.disconnect();
    };
  }, [queryClient]);

  return { positions, loading: isLoading };
}
```

```typescript
// lib/websocket/server.ts - Socket.io server setup
import { Server } from 'socket.io';
import type { Server as HttpServer } from 'http';

let io: Server | null = null;

export function getIO(): Server | null {
  return io;
}

export function initSocketServer(httpServer: HttpServer) {
  io = new Server(httpServer, {
    path: '/api/socket',
    cors: { origin: '*' }
  });

  io.on('connection', (socket) => {
    console.log('Client connected:', socket.id);

    socket.on('subscribe:positions', () => {
      socket.join('positions');
    });

    socket.on('disconnect', () => {
      console.log('Client disconnected:', socket.id);
    });
  });

  return io;
}

// Call this when positions change
export function broadcastPositions(positions: Position[]) {
  if (io) {
    io.to('positions').emit('positions:update', positions);
  }
}
```

---

## Key Pages

### Main Dashboard

```tsx
// app/(dashboard)/page.tsx
import { StatsCard } from '@/components/dashboard/stats-card';
import { PositionsTable } from '@/components/trading/positions-table';
import { RecentTrades } from '@/components/dashboard/recent-trades';

export default async function DashboardPage() {
  const stats = await getStats();
  const positions = await getPositions();
  const trades = await getRecentTrades(10);

  return (
    <div className="space-y-6">
      {/* Stats Row */}
      <div className="grid grid-cols-4 gap-4">
        <StatsCard title="Balance" value={`$${stats.balance.toFixed(2)}`} />
        <StatsCard title="Today's P&L" value={`$${stats.todayPnl.toFixed(2)}`} change={stats.todayChange} />
        <StatsCard title="Open Positions" value={stats.openPositions} />
        <StatsCard title="Win Rate" value={`${stats.winRate}%`} />
      </div>

      {/* Positions */}
      <div className="rounded-lg border bg-card">
        <div className="p-4 border-b">
          <h2 className="font-semibold">Open Positions</h2>
        </div>
        <PositionsTable positions={positions} />
      </div>

      {/* Recent Trades */}
      <RecentTrades trades={trades} />
    </div>
  );
}
```

