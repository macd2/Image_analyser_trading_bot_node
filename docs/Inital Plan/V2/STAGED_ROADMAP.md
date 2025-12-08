# Staged Implementation Roadmap

## Philosophy: Trade First, Polish Later

The goal is to get to a working trading state as fast as possible, then add features incrementally.

---

## Stage 1: Core Trading Engine (Week 1-2)
**Milestone: Execute your first trade from Next.js**

### Week 1: Foundation

#### Day 1-2: Project Setup
```bash
# Initialize
pnpm create next-app@latest trading-bot --typescript --tailwind --eslint --app
cd trading-bot
pnpm add drizzle-orm postgres
pnpm add node-cron socket.io
pnpm add -D drizzle-kit @types/node-cron

# shadcn/ui
pnpm dlx shadcn@latest init
pnpm dlx shadcn@latest add button card table badge

# Railway CLI
npm i -g @railway/cli
railway login
```

**Deliverables:**
- [ ] Next.js 14 project with App Router
- [ ] shadcn/ui initialized
- [ ] Drizzle ORM configured
- [ ] Environment variables setup

#### Day 3-4: Database Schema
```typescript
// drizzle/schema.ts - Start minimal, expand later
export const trades = pgTable('trades', {
  id: text('id').primaryKey().$defaultFn(() => createId()),
  symbol: text('symbol').notNull(),
  side: text('side', { enum: ['LONG', 'SHORT'] }).notNull(),
  entryPrice: real('entry_price'),
  exitPrice: real('exit_price'),
  quantity: real('quantity').notNull(),
  stopLoss: real('stop_loss'),
  takeProfit: real('take_profit'),
  pnl: real('pnl'),
  pnlPercent: real('pnl_percent'),
  status: text('status', { enum: ['pending', 'open', 'closed', 'cancelled'] }).default('pending'),
  bybitOrderId: text('bybit_order_id'),
  createdAt: timestamp('created_at').defaultNow(),
  closedAt: timestamp('closed_at'),
});

export const positions = pgTable('positions', {
  id: text('id').primaryKey().$defaultFn(() => createId()),
  symbol: text('symbol').notNull().unique(),
  side: text('side', { enum: ['LONG', 'SHORT'] }).notNull(),
  quantity: real('quantity').notNull(),
  entryPrice: real('entry_price').notNull(),
  currentPrice: real('current_price'),
  unrealizedPnl: real('unrealized_pnl'),
  tradeId: text('trade_id').references(() => trades.id),
  updatedAt: timestamp('updated_at').defaultNow(),
});
```

**Deliverables:**
- [ ] Core schema (trades, positions)
- [ ] Database connection working
- [ ] Migrations running

#### Day 5: Bybit Integration
```typescript
// lib/services/bybit.ts - Minimal viable client
export class BybitClient {
  private baseUrl: string;
  private apiKey: string;
  private apiSecret: string;

  async getPositions(): Promise<Position[]> { ... }
  async getBalance(): Promise<Balance> { ... }
  async placeOrder(order: OrderParams): Promise<OrderResult> { ... }
  async closePosition(symbol: string): Promise<void> { ... }
}
```

**Deliverables:**
- [ ] Bybit API client with signing
- [ ] Get positions working
- [ ] Get balance working

### Week 2: Trading Core

#### Day 6-7: Trade Execution
```typescript
// lib/services/trading-engine.ts
export class TradingEngine {
  async executeTrade(signal: TradeSignal): Promise<TradeResult> {
    // 1. Validate signal
    // 2. Check risk limits
    // 3. Calculate position size
    // 4. Place order via Bybit
    // 5. Store in database
    // 6. Return result
  }
  
  async syncPositions(): Promise<void> {
    // Sync Bybit positions with our database
  }
}
```

**Deliverables:**
- [ ] Trade execution working
- [ ] Position sync working
- [ ] Basic error handling

#### Day 8-9: API Routes
```typescript
// app/api/trades/route.ts
export async function POST(req: Request) {
  const signal = await req.json();
  const result = await tradingEngine.executeTrade(signal);
  return Response.json(result);
}

// app/api/positions/route.ts
export async function GET() {
  const positions = await tradingEngine.getPositions();
  return Response.json(positions);
}
```

**Deliverables:**
- [ ] POST /api/trades (execute trade)
- [ ] GET /api/positions (list positions)
- [ ] POST /api/positions/sync (sync with exchange)

#### Day 10: Minimal UI
```typescript
// app/page.tsx - Just enough to execute a trade
export default function TradingPage() {
  return (
    <div className="p-8">
      <h1>Trading Bot</h1>
      <PositionsTable />
      <ManualTradeForm />
    </div>
  );
}
```

**Deliverables:**
- [ ] Positions table showing current positions
- [ ] Manual trade form for testing
- [ ] Balance display

### ✅ Stage 1 Complete When:
- [ ] Can view current positions from Bybit
- [ ] Can execute a trade via API
- [ ] Trade appears in database
- [ ] Position syncs correctly

---

## Stage 2: Dashboard (Week 3-4)
**Milestone: Real-time monitoring dashboard**

### Week 3: Core Dashboard

#### shadcn/ui Components
```bash
pnpm dlx shadcn@latest add data-table tabs skeleton avatar \
  dropdown-menu dialog form input select toast
```

#### Dashboard Layout
```typescript
// app/(dashboard)/layout.tsx
export default function DashboardLayout({ children }) {
  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 overflow-auto">
        <Header />
        {children}
      </main>
    </div>
  );
}
```

**Features:**
- [ ] Dashboard layout with sidebar
- [ ] Positions widget (real-time)
- [ ] Account balance widget
- [ ] Recent trades widget
- [ ] P&L summary

### Week 4: Real-time Updates

#### Socket.io for Real-time
```typescript
// lib/websocket/server.ts
import { Server } from 'socket.io';

export function initSocketServer(httpServer: any) {
  const io = new Server(httpServer, {
    cors: { origin: '*' }
  });

  io.on('connection', (socket) => {
    console.log('Client connected');

    // Join room for position updates
    socket.on('subscribe:positions', () => {
      socket.join('positions');
    });
  });

  return io;
}

// Emit updates when positions change
export function emitPositionUpdate(io: Server, positions: Position[]) {
  io.to('positions').emit('positions:update', positions);
}
```

```typescript
// hooks/use-positions.ts (client)
'use client';
import { useEffect, useState } from 'react';
import { io } from 'socket.io-client';

export function usePositions() {
  const [positions, setPositions] = useState<Position[]>([]);

  useEffect(() => {
    const socket = io();
    socket.emit('subscribe:positions');
    socket.on('positions:update', setPositions);
    return () => { socket.disconnect(); };
  }, []);

  return positions;
}
```

**Features:**
- [ ] Real-time position updates via WebSocket
- [ ] Trade notifications (toast)
- [ ] Live P&L updates
- [ ] Connection status indicator

### ✅ Stage 2 Complete When:
- [ ] Dashboard shows all positions
- [ ] Updates happen in real-time
- [ ] Trade history is visible
- [ ] Charts show P&L over time

---

## Stage 3: AI Analysis (Week 5-6)
**Milestone: Automated chart analysis and signal generation**

### Week 5: Chart Analysis

#### OpenAI Integration
```typescript
// lib/services/openai.ts
export async function analyzeChart(imageUrl: string, context: ChartContext): Promise<Analysis> {
  const response = await openai.chat.completions.create({
    model: "gpt-4-vision-preview",
    messages: [{
      role: "user",
      content: [
        { type: "text", text: buildPrompt(context) },
        { type: "image_url", image_url: { url: imageUrl } }
      ]
    }]
  });
  return parseAnalysisResponse(response);
}
```

**Features:**
- [ ] Chart image upload
- [ ] OpenAI GPT-4 Vision integration
- [ ] Analysis response parsing
- [ ] Confidence calculation

### Week 6: Trading Cycle

#### Background Jobs with node-cron
```typescript
// lib/services/scheduler.ts
import cron from 'node-cron';
import { tradingEngine } from './trading-engine';

export function initScheduler() {
  // Trading cycle - every hour at minute 0
  cron.schedule('0 * * * *', async () => {
    console.log('🔄 Running trading cycle...');

    try {
      // 1. Check slots
      const slots = await tradingEngine.getAvailableSlots();
      if (slots === 0) {
        console.log('⏭️ No slots available, skipping');
        return;
      }

      // 2. Analyze charts
      const signals = await tradingEngine.analyzeActiveSymbols();

      // 3. Execute trades
      await tradingEngine.executeSignals(signals);

      console.log('✅ Trading cycle complete');
    } catch (error) {
      console.error('❌ Trading cycle failed:', error);
    }
  });

  // Position sync - every 2 minutes
  cron.schedule('*/2 * * * *', async () => {
    await tradingEngine.syncPositions();
  });

  console.log('📅 Scheduler initialized');
}
```

```typescript
// app/api/init/route.ts - Initialize on first request
import { initScheduler } from '@/lib/services/scheduler';

let initialized = false;

export async function GET() {
  if (!initialized) {
    initScheduler();
    initialized = true;
  }
  return Response.json({ status: 'ok' });
}
```

**Features:**
- [ ] Automated trading cycle
- [ ] Signal validation
- [ ] Risk management checks
- [ ] Telegram notifications (optional)

### ✅ Stage 3 Complete When:
- [ ] Bot analyzes charts automatically
- [ ] Generates trade signals
- [ ] Executes trades on schedule
- [ ] All decisions logged

---

## Stage 4: Learning System (Week 7-8)
**Milestone: System learns and improves**

### Week 7: Data Collection

#### Enhanced Schema
```typescript
export const decisions = pgTable('decisions', {
  id: text('id').primaryKey(),
  // Input
  chartHash: text('chart_hash'),
  symbol: text('symbol'),
  timeframe: text('timeframe'),
  marketSnapshot: jsonb('market_snapshot'),
  // Analysis
  recommendation: text('recommendation'),
  confidence: real('confidence'),
  reasoning: text('reasoning'),
  promptVersion: text('prompt_version'),
  // Execution
  traded: boolean('traded').default(false),
  skipReason: text('skip_reason'),
  tradeId: text('trade_id').references(() => trades.id),
  // Outcome (filled later)
  actualPnl: real('actual_pnl'),
  maxDrawdown: real('max_drawdown'),
  // Meta
  createdAt: timestamp('created_at').defaultNow(),
});
```

### Week 8: Analytics & Backtesting

**Features:**
- [ ] Prompt performance comparison
- [ ] Win rate by symbol/timeframe
- [ ] Confidence vs outcome correlation
- [ ] Simple backtesting engine
- [ ] Export data for analysis

### ✅ Stage 4 Complete When:
- [ ] Every decision is tracked
- [ ] Can compare prompt performance
- [ ] Backtesting works
- [ ] Clear metrics for improvement

---

## Timeline Summary

| Week | Focus | Key Deliverable |
|------|-------|-----------------|
| 1 | Foundation | Project setup, database, Bybit API |
| 2 | Trading Core | Execute first trade |
| 3 | Dashboard UI | shadcn dashboard |
| 4 | Real-time | Live updates working |
| 5 | AI Analysis | Chart analysis pipeline |
| 6 | Trading Cycle | Full automation |
| 7 | Data Collection | Decision tracking |
| 8 | Learning | Analytics & backtesting |

---

## Risk Mitigation

1. **API Failures**: Circuit breaker + retry logic from Day 1
2. **Data Loss**: PostgreSQL transactions, no SQLite for trading data
3. **Rate Limits**: Queue system prevents API spam
4. **Bad Trades**: Risk manager validates before execution

---

## Next Stage: Future Enhancements (Optional)

- Advanced risk management
- ML-based signal validation

