# Technical Deep Dive: Autotrader Bot Architecture

## 1. TRADING CYCLE ORCHESTRATION

### Current Python Implementation
```python
# run_autotrader.py - Main loop
async def run_autotrader(timeframe: str):
    while not shutdown_requested:
        # STEP 0: Cycle-level slot check
        should_skip, skip_reason = slot_manager.should_skip_cycle_due_to_slots()
        
        # STEP 1: Fresh Data Check
        current_cycle_trades = recommendation_service.check_current_cycle_recommendations()
        
        # STEP 2: Chart Capture & Analysis
        charts = sourcer.capture_charts()
        analysis = analyzer.analyze_charts(charts)
        
        # STEP 3: Signal Filtering
        filtered_signals = filtering_pipeline.execute()
        
        # STEP 4: Position Sizing
        position_sizes = risk_manager.calculate_position_sizes()
        
        # STEP 5: Telegram Confirmation
        confirmed_trades = telegram_bot.get_confirmation()
        
        # STEP 6: Trade Execution
        executed = trader.execute_trades(confirmed_trades)
        
        # Sleep until next cycle boundary
        await sleep_until_next_cycle()
```

### Next.js Implementation Strategy
```typescript
// lib/services/trading-engine.ts
class TradingEngine {
  async runTradingCycle(timeframe: string) {
    const cycleId = generateCycleId();
    
    // Use Bull job queue for reliability
    const job = await tradingQueue.add('trading-cycle', {
      timeframe,
      cycleId,
      timestamp: new Date()
    });
    
    // Process with error handling and retries
    return await job.finished();
  }
}

// jobs/trading-cycle.ts (Bull processor)
export const tradingCycleProcessor = async (job) => {
  const { timeframe, cycleId } = job.data;
  
  // Step 0-6 as separate service methods
  await slotManager.checkCycleLevelSlots();
  await chartAnalyzer.ensureFreshData();
  await signalFilter.filterAndRank();
  // ... etc
};
```

---

## 2. DATABASE ARCHITECTURE

### Schema Migration (SQLite → PostgreSQL)

#### analysis_results Table
```sql
CREATE TABLE analysis_results (
  id UUID PRIMARY KEY,
  symbol VARCHAR(20) NOT NULL,
  timeframe VARCHAR(10) NOT NULL,
  recommendation VARCHAR(10) NOT NULL,
  confidence DECIMAL(5,3) NOT NULL,
  entry_price DECIMAL(20,8),
  stop_loss DECIMAL(20,8),
  take_profit DECIMAL(20,8),
  image_path TEXT,
  analysis_data JSONB,  -- Full AI response
  timestamp TIMESTAMP NOT NULL,
  created_at TIMESTAMP DEFAULT NOW(),
  
  UNIQUE(symbol, timeframe, timestamp)
);
```

#### trades Table
```sql
CREATE TABLE trades (
  id UUID PRIMARY KEY,
  recommendation_id UUID REFERENCES analysis_results(id),
  symbol VARCHAR(20) NOT NULL,
  side VARCHAR(10) NOT NULL,  -- 'Buy' or 'Sell'
  quantity DECIMAL(20,8) NOT NULL,
  entry_price DECIMAL(20,8),
  take_profit DECIMAL(20,8),
  stop_loss DECIMAL(20,8),
  order_id VARCHAR(50) UNIQUE,
  pnl DECIMAL(20,8) DEFAULT 0,
  status VARCHAR(20) DEFAULT 'open',  -- 'open', 'closed', 'cancelled'
  prompt_name VARCHAR(100),
  created_at TIMESTAMP DEFAULT NOW(),
  closed_at TIMESTAMP,
  
  INDEX idx_symbol_status (symbol, status),
  INDEX idx_created_at (created_at)
);
```

#### position_tracking Table
```sql
CREATE TABLE position_tracking (
  id UUID PRIMARY KEY,
  trade_id UUID REFERENCES trades(id),
  symbol VARCHAR(20) NOT NULL,
  entry_price DECIMAL(20,8),
  current_price DECIMAL(20,8),
  live_rr DECIMAL(10,3),
  unrealized_pnl DECIMAL(20,8),
  checked_at TIMESTAMP,
  
  INDEX idx_symbol (symbol)
);
```

---

## 3. BYBIT API INTEGRATION

### Key Endpoints Needed
```typescript
// lib/services/bybit.ts
class BybitClient {
  // Account
  async getWalletBalance(): Promise<WalletBalance>
  async getPositions(): Promise<Position[]>
  async getOpenOrders(): Promise<Order[]>
  
  // Trading
  async placeOrder(params: OrderParams): Promise<OrderResponse>
  async cancelOrder(orderId: string): Promise<void>
  async replaceOrder(orderId: string, newParams: OrderParams): Promise<OrderResponse>
  
  // Market Data
  async getTicker(symbol: string): Promise<Ticker>
  async getKlines(symbol: string, interval: string, limit: number): Promise<Kline[]>
}
```

### Order Lifecycle State Machine
```
PENDING → FILLED → CLOSED
       ↘ CANCELLED
       ↘ REJECTED
       
For TP/SL orders:
ENTRY_PLACED → ENTRY_FILLED → WAITING_EXIT
            → TP_FILLED (profit)
            → SL_FILLED (loss)
            → MANUAL_CLOSED
```

---

## 4. OPENAI INTEGRATION

### Chart Analysis Flow
```typescript
// lib/services/openai.ts
class ChartAnalyzer {
  async analyzeChart(
    imagePath: string,
    symbol: string,
    timeframe: string
  ): Promise<AnalysisResult> {
    // 1. Read image file
    const imageData = await readFile(imagePath);
    
    // 2. Call GPT-4 Vision with prompt
    const response = await openai.chat.completions.create({
      model: "gpt-4-vision-preview",
      messages: [{
        role: "user",
        content: [
          { type: "text", text: ANALYSIS_PROMPT },
          { type: "image_url", image_url: { url: imageData } }
        ]
      }],
      max_tokens: 2000
    });
    
    // 3. Parse JSON response
    return parseAnalysisResponse(response.content);
  }
}
```

### Confidence Calculation
```typescript
function calculateConfidence(analysis: AnalysisData): number {
  const setupQuality = analysis.setup_quality;      // 0-1
  const riskReward = analysis.risk_reward_ratio;    // 0-1
  const marketEnv = analysis.market_environment;    // 0-1
  
  // Weighted formula
  const confidence = 
    (setupQuality * 0.40) +
    (riskReward * 0.25) +
    (marketEnv * 0.35);
  
  // Round to 3 decimals
  return Math.round(confidence * 1000) / 1000;
}
```

---

## 5. REAL-TIME FEATURES

### WebSocket Architecture
```typescript
// lib/websocket/server.ts
import { Server } from 'socket.io';

const io = new Server(httpServer, {
  cors: { origin: process.env.FRONTEND_URL }
});

io.on('connection', (socket) => {
  // Subscribe to position updates
  socket.on('subscribe:positions', (symbol) => {
    socket.join(`positions:${symbol}`);
  });
});

// Emit updates from trading engine
function emitPositionUpdate(symbol: string, data: PositionData) {
  io.to(`positions:${symbol}`).emit('position:updated', data);
}
```

### Background Job Queue (Bull)
```typescript
// lib/queue/index.ts
import Queue from 'bull';

export const tradingQueue = new Queue('trading', {
  redis: { host: 'localhost', port: 6379 }
});

export const positionMonitorQueue = new Queue('position-monitor', {
  redis: { host: 'localhost', port: 6379 }
});

// Register processors
tradingQueue.process(tradingCycleProcessor);
positionMonitorQueue.process(positionMonitorProcessor);

// Schedule recurring jobs
positionMonitorQueue.add(
  { symbol: 'BTCUSDT' },
  { repeat: { every: 120000 } }  // Every 2 minutes
);
```

---

## 6. FRONTEND ARCHITECTURE

### Dashboard Pages Structure
```
/dashboard
  ├── /live - Real-time trading monitor
  ├── /trades - Trade history & analytics
  ├── /backtest - Backtest with images
  ├── /prompt-builder - Intelligent prompt builder
  └── /settings - Configuration
```

### Real-time Updates (React)
```typescript
// components/LivePositions.tsx
import { useEffect, useState } from 'react';
import { io } from 'socket.io-client';

export function LivePositions() {
  const [positions, setPositions] = useState([]);
  
  useEffect(() => {
    const socket = io(process.env.NEXT_PUBLIC_API_URL);
    
    socket.on('position:updated', (data) => {
      setPositions(prev => 
        prev.map(p => p.symbol === data.symbol ? data : p)
      );
    });
    
    return () => socket.disconnect();
  }, []);
  
  return <PositionsTable data={positions} />;
}
```

---

## 7. ERROR HANDLING & RESILIENCE

### Circuit Breaker Pattern
```typescript
class CircuitBreaker {
  private state: 'CLOSED' | 'OPEN' | 'HALF_OPEN' = 'CLOSED';
  private failureCount = 0;
  private lastFailureTime = 0;
  
  async execute<T>(fn: () => Promise<T>): Promise<T> {
    if (this.state === 'OPEN') {
      if (Date.now() - this.lastFailureTime > 60000) {
        this.state = 'HALF_OPEN';
      } else {
        throw new Error('Circuit breaker is OPEN');
      }
    }
    
    try {
      const result = await fn();
      this.onSuccess();
      return result;
    } catch (error) {
      this.onFailure();
      throw error;
    }
  }
}
```

### Retry Logic
```typescript
async function retryWithBackoff<T>(
  fn: () => Promise<T>,
  maxRetries: number = 3,
  baseDelay: number = 1000
): Promise<T> {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await fn();
    } catch (error) {
      if (i === maxRetries - 1) throw error;
      const delay = baseDelay * Math.pow(2, i);
      await new Promise(r => setTimeout(r, delay));
    }
  }
}
```

---

## 8. DEPLOYMENT ARCHITECTURE

### Docker Compose Setup
```yaml
version: '3.8'
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: autotrader
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
  
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
  
  app:
    build: .
    ports:
      - "3000:3000"
    environment:
      DATABASE_URL: postgresql://user:pass@postgres:5432/autotrader
      REDIS_URL: redis://redis:6379
      BYBIT_API_KEY: ${BYBIT_API_KEY}
      OPENAI_API_KEY: ${OPENAI_API_KEY}
    depends_on:
      - postgres
      - redis
```

---

## 9. PERFORMANCE OPTIMIZATION

### Database Indexing Strategy
```sql
-- Critical indexes for trading queries
CREATE INDEX idx_trades_symbol_status ON trades(symbol, status);
CREATE INDEX idx_trades_created_at ON trades(created_at DESC);
CREATE INDEX idx_analysis_symbol_timeframe ON analysis_results(symbol, timeframe);
CREATE INDEX idx_positions_symbol ON position_tracking(symbol);
```

### Caching Strategy
```typescript
// Redis caching for frequently accessed data
const cache = new Redis();

async function getCachedPositions(symbol: string) {
  const cached = await cache.get(`positions:${symbol}`);
  if (cached) return JSON.parse(cached);
  
  const positions = await db.positions.findMany({ where: { symbol } });
  await cache.setex(`positions:${symbol}`, 300, JSON.stringify(positions));
  return positions;
}
```

---

## 10. TESTING STRATEGY

### Unit Tests
```typescript
// __tests__/services/confidence-calculator.test.ts
describe('ConfidenceCalculator', () => {
  it('should calculate confidence correctly', () => {
    const result = calculateConfidence({
      setup_quality: 0.8,
      risk_reward_ratio: 0.9,
      market_environment: 0.7
    });
    expect(result).toBe(0.795);
  });
});
```

### Integration Tests
```typescript
// __tests__/integration/trading-cycle.test.ts
describe('Trading Cycle', () => {
  it('should complete full cycle', async () => {
    const result = await tradingEngine.runTradingCycle('1h');
    expect(result.status).toBe('completed');
    expect(result.tradesExecuted).toBeGreaterThan(0);
  });
});
```

---

**Document Version**: 1.0  
**Last Updated**: 2025-11-26

