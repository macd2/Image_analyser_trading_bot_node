# Component Mapping: Python → Next.js

## Overview
This document maps each Python component to its Next.js equivalent, showing the migration path and implementation strategy.

---

## CORE TRADING ENGINE

### 1. ChartSourcer (trading_bot/core/sourcer.py)
**Purpose**: Capture charts from TradingView using Playwright automation

**Python Implementation**:
- Async Playwright browser automation
- TradingView login & navigation
- Screenshot capture with timestamp
- Local chart fallback

**Next.js Implementation**:
```typescript
// lib/services/chart-sourcer.ts
class ChartSourcer {
  private browser: Browser;
  
  async captureChart(symbol: string, timeframe: string): Promise<string> {
    // Use Playwright in Node.js
    const page = await this.browser.newPage();
    await page.goto(`https://www.tradingview.com/chart/?symbol=${symbol}`);
    const path = await page.screenshot({ path: `./charts/${symbol}_${timeframe}.png` });
    return path;
  }
}
```

**Migration Notes**:
- Playwright works in Node.js (no changes needed)
- Store images in `/public/charts` or cloud storage (S3)
- Use Bull queue for async processing

---

### 2. ChartAnalyzer (trading_bot/core/analyzer.py)
**Purpose**: Analyze charts using OpenAI GPT-4 Vision

**Python Implementation**:
- OpenAI API integration
- Image encoding and transmission
- JSON response parsing
- Prompt selection logic

**Next.js Implementation**:
```typescript
// lib/services/chart-analyzer.ts
class ChartAnalyzer {
  async analyzeChart(imagePath: string, symbol: string): Promise<AnalysisResult> {
    const imageData = await fs.readFile(imagePath);
    const base64 = imageData.toString('base64');
    
    const response = await openai.chat.completions.create({
      model: "gpt-4-vision-preview",
      messages: [{
        role: "user",
        content: [
          { type: "text", text: PROMPT },
          { type: "image_url", image_url: { url: `data:image/png;base64,${base64}` } }
        ]
      }]
    });
    
    return parseResponse(response.content[0].text);
  }
}
```

**Migration Notes**:
- Use `openai` npm package (same API)
- Store analysis results in PostgreSQL
- Cache results to avoid re-analysis

---

### 3. SignalValidator (trading_bot/core/validator.py)
**Purpose**: Validate trading signals against rules

**Python Implementation**:
- Confidence threshold checking
- Recent signal deduplication
- Risk score calculation

**Next.js Implementation**:
```typescript
// lib/services/signal-validator.ts
class SignalValidator {
  validate(signal: Signal): ValidationResult {
    const errors: string[] = [];
    
    if (signal.confidence < this.minConfidence) {
      errors.push('Confidence below threshold');
    }
    
    if (this.hasRecentSimilarSignal(signal)) {
      errors.push('Similar signal recently executed');
    }
    
    return {
      valid: errors.length === 0,
      errors
    };
  }
}
```

**Migration Notes**:
- Implement as middleware in API routes
- Use database for signal history
- Add rate limiting

---

### 4. TradeExecutor (trading_bot/core/trader.py)
**Purpose**: Execute trades on Bybit exchange

**Python Implementation**:
- Bybit API client (pybit library)
- Order placement with TP/SL
- Position validation
- Error handling & retries

**Next.js Implementation**:
```typescript
// lib/services/trade-executor.ts
class TradeExecutor {
  async executeTrade(signal: Signal): Promise<ExecutionResult> {
    // Validate parameters
    const validation = this.validateTradeParams(signal);
    if (!validation.valid) throw new Error(validation.error);
    
    // Place order on Bybit
    const order = await this.bybitClient.placeOrder({
      symbol: signal.symbol,
      side: signal.side,
      qty: signal.quantity,
      price: signal.entry_price,
      takeProfit: signal.take_profit,
      stopLoss: signal.stop_loss,
      orderType: 'Limit'
    });
    
    // Store in database
    await db.trades.create({
      symbol: signal.symbol,
      orderId: order.orderId,
      // ... other fields
    });
    
    return { success: true, orderId: order.orderId };
  }
}
```

**Migration Notes**:
- Use `axios` or `node-fetch` for Bybit API
- Implement circuit breaker for API failures
- Store order IDs immediately for tracking

---

### 5. PositionManager (trading_bot/core/position_manager.py)
**Purpose**: Track open positions and P&L

**Python Implementation**:
- Real-time position tracking
- P&L calculation
- Position display formatting

**Next.js Implementation**:
```typescript
// lib/services/position-manager.ts
class PositionManager {
  async getOpenPositions(): Promise<Position[]> {
    // Fetch from Bybit
    const positions = await this.bybitClient.getPositions();
    
    // Enrich with database data
    const enriched = await Promise.all(
      positions.map(async (pos) => ({
        ...pos,
        trade: await db.trades.findUnique({ where: { symbol: pos.symbol } }),
        unrealizedPnl: this.calculatePnL(pos)
      }))
    );
    
    return enriched;
  }
}
```

**Migration Notes**:
- Sync with Bybit every 2 minutes
- Cache in Redis for performance
- Emit WebSocket updates

---

### 6. RiskManager (trading_bot/core/risk_manager.py)
**Purpose**: Manage risk and position sizing

**Python Implementation**:
- Position size calculation
- Risk per trade validation
- Slot management

**Next.js Implementation**:
```typescript
// lib/services/risk-manager.ts
class RiskManager {
  calculatePositionSize(signal: Signal, balance: number): number {
    const riskAmount = balance * this.riskPercentage;
    const stopDistance = Math.abs(signal.entry_price - signal.stop_loss);
    const quantity = riskAmount / stopDistance;
    
    return this.validateQuantity(quantity, signal.symbol);
  }
  
  async checkSlots(): Promise<{ available: number; max: number }> {
    const positions = await this.bybitClient.getPositions();
    const orders = await this.bybitClient.getOpenOrders();
    const occupied = positions.length + orders.length;
    
    return {
      available: this.maxSlots - occupied,
      max: this.maxSlots
    };
  }
}
```

**Migration Notes**:
- Implement slot checking before each cycle
- Store risk parameters in config
- Add validation for minimum/maximum quantities

---

### 7. Recommender (trading_bot/core/recommender.py)
**Purpose**: Generate trade recommendations

**Python Implementation**:
- Fetch latest analysis
- Apply filtering rules
- Rank candidates

**Next.js Implementation**:
```typescript
// lib/services/recommender.ts
class Recommender {
  async getRecommendations(timeframe: string): Promise<Recommendation[]> {
    // Get latest analysis for each symbol
    const analyses = await db.analysisResults.findMany({
      where: { timeframe },
      orderBy: { timestamp: 'desc' },
      distinct: ['symbol'],
      take: 1
    });
    
    // Filter and rank
    return analyses
      .filter(a => a.confidence >= this.minConfidence)
      .sort((a, b) => b.confidence - a.confidence);
  }
}
```

**Migration Notes**:
- Use Prisma for database queries
- Implement caching for performance
- Add recommendation history tracking

---

## REAL-TIME MONITORING

### 8. EnhancedPositionMonitor (trading_bot/core/enhanced_position_monitor.py)
**Purpose**: Background task for stop loss tightening

**Python Implementation**:
- Runs every 2 minutes
- Checks profitable positions
- Tightens stop losses

**Next.js Implementation**:
```typescript
// jobs/position-monitor.ts
export const positionMonitorProcessor = async (job) => {
  const positions = await positionManager.getOpenPositions();
  
  for (const pos of positions) {
    if (pos.unrealizedPnl > 0) {
      const newSL = calculateTightenedSL(pos);
      await tradeExecutor.updateStopLoss(pos.orderId, newSL);
    }
  }
};

// Schedule in lib/queue/index.ts
positionMonitorQueue.add(
  {},
  { repeat: { every: 120000 } }  // Every 2 minutes
);
```

**Migration Notes**:
- Use Bull queue for scheduling
- Emit WebSocket updates for UI
- Log all SL adjustments

---

### 9. RealTimeTradeTracker (trading_bot/core/realtime_trade_tracker.py)
**Purpose**: Sync trades with exchange in real-time

**Python Implementation**:
- Fetch closed trades from Bybit
- Update database
- Calculate P&L

**Next.js Implementation**:
```typescript
// lib/services/realtime-trade-tracker.ts
class RealTimeTradeTracker {
  async syncTrades(): Promise<void> {
    const closedTrades = await this.bybitClient.getClosedTrades();
    
    for (const trade of closedTrades) {
      await db.trades.update({
        where: { orderId: trade.orderId },
        data: {
          status: 'closed',
          pnl: trade.pnl,
          closedAt: new Date(trade.closedTime)
        }
      });
    }
  }
}
```

**Migration Notes**:
- Run every 5 minutes
- Handle partial fills
- Update P&L calculations

---

## NOTIFICATIONS

### 10. TelegramBot (trading_bot/core/telegram_bot.py)
**Purpose**: Send notifications and get user confirmations

**Python Implementation**:
- Telegram Bot API integration
- Message sending
- Callback handling

**Next.js Implementation**:
```typescript
// lib/services/telegram-bot.ts
class TelegramBot {
  async sendTradeSignal(signal: Signal): Promise<void> {
    const message = this.formatSignalMessage(signal);
    
    await fetch('https://api.telegram.org/bot${TOKEN}/sendMessage', {
      method: 'POST',
      body: JSON.stringify({
        chat_id: this.chatId,
        text: message,
        reply_markup: {
          inline_keyboard: [
            [{ text: 'Approve', callback_data: 'approve' }],
            [{ text: 'Reject', callback_data: 'reject' }]
          ]
        }
      })
    });
  }
}
```

**Migration Notes**:
- Use Telegram Bot API directly
- Store user responses in database
- Implement timeout handling

---

## DATABASE LAYER

### 11. DataAgent (trading_bot/core/data_agent.py)
**Purpose**: Database access layer

**Python Implementation**:
- SQLite connection management
- Query execution
- Transaction handling

**Next.js Implementation**:
```typescript
// lib/db/prisma.ts
import { PrismaClient } from '@prisma/client';

export const prisma = new PrismaClient();

// Use in services
const trades = await prisma.trades.findMany({
  where: { symbol: 'BTCUSDT' },
  orderBy: { createdAt: 'desc' }
});
```

**Migration Notes**:
- Use Prisma ORM for type safety
- Implement connection pooling
- Add query logging

---

## CONFIGURATION

### 12. Config (trading_bot/config/settings.py)
**Purpose**: Configuration management

**Python Implementation**:
- YAML-based config
- Environment variable overrides

**Next.js Implementation**:
```typescript
// lib/config/index.ts
export const config = {
  trading: {
    maxSlots: parseInt(process.env.MAX_SLOTS || '5'),
    minConfidence: parseFloat(process.env.MIN_CONFIDENCE || '0.55'),
    riskPercentage: parseFloat(process.env.RISK_PERCENTAGE || '0.01')
  },
  bybit: {
    apiKey: process.env.BYBIT_API_KEY!,
    apiSecret: process.env.BYBIT_API_SECRET!,
    testnet: process.env.BYBIT_TESTNET === 'true'
  },
  openai: {
    apiKey: process.env.OPENAI_API_KEY!,
    model: process.env.OPENAI_MODEL || 'gpt-4-vision-preview'
  }
};
```

**Migration Notes**:
- Use `.env.local` for secrets
- Validate config on startup
- Support environment-specific configs

---

## SUMMARY TABLE

| Python Component | Next.js Location | Type | Priority |
|------------------|------------------|------|----------|
| ChartSourcer | lib/services/chart-sourcer.ts | Service | P0 |
| ChartAnalyzer | lib/services/chart-analyzer.ts | Service | P0 |
| SignalValidator | lib/services/signal-validator.ts | Service | P0 |
| TradeExecutor | lib/services/trade-executor.ts | Service | P0 |
| PositionManager | lib/services/position-manager.ts | Service | P0 |
| RiskManager | lib/services/risk-manager.ts | Service | P0 |
| Recommender | lib/services/recommender.ts | Service | P0 |
| EnhancedPositionMonitor | jobs/position-monitor.ts | Job | P1 |
| RealTimeTradeTracker | lib/services/realtime-trade-tracker.ts | Service | P1 |
| TelegramBot | lib/services/telegram-bot.ts | Service | P1 |
| DataAgent | lib/db/prisma.ts | ORM | P0 |
| Config | lib/config/index.ts | Config | P0 |

---

**Document Version**: 1.0  
**Last Updated**: 2025-11-26

