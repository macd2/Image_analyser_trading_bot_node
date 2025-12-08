# Core Services Architecture

## Design Principle: One Service, One Job

Each service is small, focused, and testable. No god objects.

---

## Service Dependency Tree

```
TradingEngine (orchestrator)
    │
    ├── BybitClient (exchange API)
    ├── ChartAnalyzer (AI analysis)
    ├── RiskManager (position sizing)
    └── Database (Drizzle)
```

---

## 1. BybitClient

**Purpose**: All exchange communication
**Location**: `lib/services/bybit.ts`

```typescript
import crypto from 'crypto';

interface BybitConfig {
  apiKey: string;
  apiSecret: string;
  testnet?: boolean;
}

export class BybitClient {
  private baseUrl: string;
  private apiKey: string;
  private apiSecret: string;

  constructor(config: BybitConfig) {
    this.baseUrl = config.testnet 
      ? 'https://api-testnet.bybit.com'
      : 'https://api.bybit.com';
    this.apiKey = config.apiKey;
    this.apiSecret = config.apiSecret;
  }

  // Core methods only - keep it minimal
  async getBalance(): Promise<Balance> { }
  async getPositions(): Promise<Position[]> { }
  async getTicker(symbol: string): Promise<Ticker> { }
  async placeOrder(params: OrderParams): Promise<OrderResult> { }
  async cancelOrder(orderId: string): Promise<void> { }
  async amendOrder(orderId: string, updates: OrderUpdate): Promise<void> { }

  // Helper for signing requests
  private sign(params: Record<string, any>): string {
    const timestamp = Date.now();
    const queryString = Object.keys(params)
      .sort()
      .map(k => `${k}=${params[k]}`)
      .join('&');
    const signStr = `${timestamp}${this.apiKey}${queryString}`;
    return crypto.createHmac('sha256', this.apiSecret)
      .update(signStr)
      .digest('hex');
  }

  // Wrapper with retry logic
  private async request<T>(
    method: 'GET' | 'POST',
    endpoint: string,
    params?: Record<string, any>
  ): Promise<T> {
    const maxRetries = 3;
    let lastError: Error | null = null;

    for (let i = 0; i < maxRetries; i++) {
      try {
        // Add authentication headers
        // Make request
        // Parse response
        // Return data
      } catch (error) {
        lastError = error as Error;
        if (i < maxRetries - 1) {
          await new Promise(r => setTimeout(r, 1000 * (i + 1))); // Exponential backoff
        }
      }
    }
    throw lastError;
  }
}
```

**Key Features:**
- Automatic request signing
- Retry with exponential backoff
- Type-safe responses
- Testnet support

---

## 2. ChartAnalyzer

**Purpose**: AI-powered chart analysis
**Location**: `lib/services/chart-analyzer.ts`

```typescript
import OpenAI from 'openai';

interface AnalysisResult {
  recommendation: 'LONG' | 'SHORT' | 'HOLD';
  confidence: number;
  entryPrice: number;
  stopLoss: number;
  takeProfit: number;
  reasoning: string;
  raw: object; // Full response for debugging
}

export class ChartAnalyzer {
  private openai: OpenAI;
  private promptVersion: string;

  constructor(apiKey: string, promptVersion = 'v1') {
    this.openai = new OpenAI({ apiKey });
    this.promptVersion = promptVersion;
  }

  async analyze(imageUrl: string, context: AnalysisContext): Promise<AnalysisResult> {
    const prompt = this.buildPrompt(context);
    const startTime = Date.now();

    const response = await this.openai.chat.completions.create({
      model: 'gpt-4-vision-preview',
      max_tokens: 1000,
      messages: [{
        role: 'user',
        content: [
          { type: 'text', text: prompt },
          { type: 'image_url', image_url: { url: imageUrl } }
        ]
      }]
    });

    const duration = Date.now() - startTime;
    return this.parseResponse(response, duration);
  }

  private buildPrompt(context: AnalysisContext): string {
    // Load prompt based on version
    return prompts[this.promptVersion](context);
  }

  private parseResponse(response: any, durationMs: number): AnalysisResult {
    // Extract structured data from GPT response
    // Calculate confidence score
    // Return typed result
  }
}
```

---

## 3. RiskManager

**Purpose**: Position sizing and risk validation
**Location**: `lib/services/risk-manager.ts`

```typescript
interface RiskConfig {
  maxRiskPerTrade: number; // e.g., 0.02 = 2%
  maxOpenPositions: number;
  maxDailyLoss: number;
}

export class RiskManager {
  private config: RiskConfig;

  constructor(config: RiskConfig) {
    this.config = config;
  }

  // Calculate position size based on risk
  calculatePositionSize(
    balance: number,
    entryPrice: number,
    stopLoss: number
  ): number {
    const riskAmount = balance * this.config.maxRiskPerTrade;
    const stopDistance = Math.abs(entryPrice - stopLoss);
    const stopPercent = stopDistance / entryPrice;
    return riskAmount / (entryPrice * stopPercent);
  }

  // Check if trade is allowed
  async validateTrade(signal: TradeSignal, currentState: TradingState): Promise<ValidationResult> {
    const checks = [
      this.checkMaxPositions(currentState.openPositions),
      this.checkDailyLoss(currentState.dailyPnL),
      this.checkSymbolExposure(signal.symbol, currentState.positions),
      this.checkMinConfidence(signal.confidence),
    ];

    const failed = checks.filter(c => !c.passed);
    return {
      allowed: failed.length === 0,
      reasons: failed.map(c => c.reason),
    };
  }

  private checkMaxPositions(current: number): Check {
    return {
      passed: current < this.config.maxOpenPositions,
      reason: `Max ${this.config.maxOpenPositions} positions allowed`,
    };
  }

  private checkDailyLoss(pnl: number): Check {
    return {
      passed: pnl > -this.config.maxDailyLoss,
      reason: 'Daily loss limit reached',
    };
  }
}
```

---

## 4. TradingEngine (Orchestrator)

**Purpose**: Coordinates all services
**Location**: `lib/services/trading-engine.ts`

```typescript
export class TradingEngine {
  private bybit: BybitClient;
  private analyzer: ChartAnalyzer;
  private risk: RiskManager;
  private db: Database;

  constructor(deps: Dependencies) {
    this.bybit = deps.bybit;
    this.analyzer = deps.analyzer;
    this.risk = deps.risk;
    this.db = deps.db;
  }

  // Main trading cycle
  async runCycle(timeframe: string): Promise<CycleResult> {
    // 1. Check if we can trade
    const state = await this.getCurrentState();
    if (state.openPositions >= this.risk.config.maxOpenPositions) {
      return { skipped: true, reason: 'slots_full' };
    }

    // 2. Get signals
    const signals = await this.getSignals(timeframe);
    if (signals.length === 0) {
      return { skipped: true, reason: 'no_signals' };
    }

    // 3. Validate and execute
    const results: TradeResult[] = [];
    for (const signal of signals) {
      const result = await this.executeSignal(signal, state);
      results.push(result);
      if (!result.success) break; // Stop on first failure
    }

    return { executed: results.filter(r => r.success).length, results };
  }

  // Execute a single trade signal
  async executeSignal(signal: TradeSignal, state: TradingState): Promise<TradeResult> {
    // 1. Validate with risk manager
    const validation = await this.risk.validateTrade(signal, state);
    if (!validation.allowed) {
      await this.logSkippedSignal(signal, validation.reasons);
      return { success: false, reason: validation.reasons.join(', ') };
    }

    // 2. Calculate position size
    const size = this.risk.calculatePositionSize(
      state.balance,
      signal.entryPrice,
      signal.stopLoss
    );

    // 3. Execute on exchange
    try {
      const order = await this.bybit.placeOrder({
        symbol: signal.symbol,
        side: signal.side === 'LONG' ? 'Buy' : 'Sell',
        qty: size,
        price: signal.entryPrice,
        stopLoss: signal.stopLoss,
        takeProfit: signal.takeProfit,
      });

      // 4. Store in database
      const trade = await this.db.insert(trades).values({
        symbol: signal.symbol,
        side: signal.side,
        quantity: size,
        entryPrice: signal.entryPrice,
        stopLoss: signal.stopLoss,
        takeProfit: signal.takeProfit,
        bybitOrderId: order.orderId,
        status: 'pending',
        decisionId: signal.decisionId,
      }).returning();

      return { success: true, trade: trade[0] };
    } catch (error) {
      await this.logError(signal, error);
      return { success: false, reason: error.message };
    }
  }

  // Sync positions with exchange
  async syncPositions(): Promise<void> {
    const exchangePositions = await this.bybit.getPositions();
    
    for (const pos of exchangePositions) {
      await this.db.insert(positions)
        .values({
          symbol: pos.symbol,
          side: pos.side,
          quantity: pos.size,
          entryPrice: pos.avgPrice,
          currentPrice: pos.markPrice,
          unrealizedPnl: pos.unrealisedPnl,
        })
        .onConflictDoUpdate({
          target: positions.symbol,
          set: {
            currentPrice: pos.markPrice,
            unrealizedPnl: pos.unrealisedPnl,
            syncedAt: new Date(),
          },
        });
    }
  }
}
```

---

## Dependency Injection

```typescript
// lib/services/index.ts
import { BybitClient } from './bybit';
import { ChartAnalyzer } from './chart-analyzer';
import { RiskManager } from './risk-manager';
import { TradingEngine } from './trading-engine';
import { db } from '@/lib/db';

// Create instances with config
const bybit = new BybitClient({
  apiKey: process.env.BYBIT_API_KEY!,
  apiSecret: process.env.BYBIT_API_SECRET!,
  testnet: process.env.BYBIT_TESTNET === 'true',
});

const analyzer = new ChartAnalyzer(
  process.env.OPENAI_API_KEY!,
  'v1' // Default prompt version
);

const risk = new RiskManager({
  maxRiskPerTrade: 0.02,
  maxOpenPositions: 5,
  maxDailyLoss: 0.10,
});

export const tradingEngine = new TradingEngine({
  bybit,
  analyzer,
  risk,
  db,
});
```

---

## Error Handling Pattern

```typescript
// lib/utils/safe-call.ts
export async function safeCall<T>(
  fn: () => Promise<T>,
  options: {
    fallback?: T;
    retries?: number;
    onError?: (error: Error) => void;
  } = {}
): Promise<T | undefined> {
  const { fallback, retries = 1, onError } = options;
  
  for (let i = 0; i < retries; i++) {
    try {
      return await fn();
    } catch (error) {
      onError?.(error as Error);
      if (i === retries - 1) {
        if (fallback !== undefined) return fallback;
        throw error;
      }
      await new Promise(r => setTimeout(r, 1000 * (i + 1)));
    }
  }
}

// Usage
const positions = await safeCall(
  () => bybit.getPositions(),
  { fallback: [], retries: 3 }
);
```

