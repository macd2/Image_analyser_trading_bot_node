# API Specification: Next.js Autotrader

## Overview
Complete REST API specification for the Next.js autotrader application. All endpoints use JSON and follow RESTful conventions.

---

## TRADING ENDPOINTS

### POST /api/trades/execute
Execute a new trade based on a signal

**Request**:
```json
{
  "symbol": "BTCUSDT",
  "side": "Buy",
  "quantity": 0.01,
  "entryPrice": 45000,
  "takeProfit": 46000,
  "stopLoss": 44000,
  "confidence": 0.75,
  "promptName": "code_nova_improved"
}
```

**Response** (200):
```json
{
  "success": true,
  "tradeId": "uuid-123",
  "orderId": "bybit-order-id",
  "status": "pending",
  "createdAt": "2025-11-26T10:30:00Z"
}
```

**Error** (400):
```json
{
  "error": "Insufficient slots available",
  "code": "SLOTS_EXHAUSTED"
}
```

---

### GET /api/trades
List all trades with filtering

**Query Parameters**:
- `symbol`: Filter by symbol (optional)
- `status`: 'open' | 'closed' | 'cancelled' (optional)
- `limit`: Max results (default: 50)
- `offset`: Pagination offset (default: 0)
- `sortBy`: 'createdAt' | 'pnl' (default: 'createdAt')

**Response** (200):
```json
{
  "trades": [
    {
      "id": "uuid-123",
      "symbol": "BTCUSDT",
      "side": "Buy",
      "quantity": 0.01,
      "entryPrice": 45000,
      "currentPrice": 45500,
      "takeProfit": 46000,
      "stopLoss": 44000,
      "pnl": 5,
      "pnlPercent": 0.11,
      "status": "open",
      "createdAt": "2025-11-26T10:30:00Z"
    }
  ],
  "total": 150,
  "limit": 50,
  "offset": 0
}
```

---

### GET /api/trades/:id
Get single trade details

**Response** (200):
```json
{
  "id": "uuid-123",
  "symbol": "BTCUSDT",
  "side": "Buy",
  "quantity": 0.01,
  "entryPrice": 45000,
  "takeProfit": 46000,
  "stopLoss": 44000,
  "orderId": "bybit-order-id",
  "status": "open",
  "pnl": 5,
  "createdAt": "2025-11-26T10:30:00Z",
  "analysis": {
    "confidence": 0.75,
    "recommendation": "buy",
    "summary": "Strong uptrend with support at 44500"
  }
}
```

---

### PATCH /api/trades/:id/close
Close an open trade manually

**Request**:
```json
{
  "exitPrice": 45500,
  "reason": "manual_close"
}
```

**Response** (200):
```json
{
  "success": true,
  "pnl": 5,
  "pnlPercent": 0.11,
  "closedAt": "2025-11-26T11:00:00Z"
}
```

---

## POSITIONS ENDPOINTS

### GET /api/positions
Get all open positions

**Response** (200):
```json
{
  "positions": [
    {
      "symbol": "BTCUSDT",
      "side": "Buy",
      "quantity": 0.01,
      "entryPrice": 45000,
      "currentPrice": 45500,
      "unrealizedPnl": 5,
      "unrealizedPnlPercent": 0.11,
      "liveRR": 2.5,
      "takeProfit": 46000,
      "stopLoss": 44000,
      "createdAt": "2025-11-26T10:30:00Z"
    }
  ],
  "totalUnrealizedPnl": 15,
  "totalUnrealizedPnlPercent": 0.33
}
```

---

### GET /api/positions/:symbol
Get position for specific symbol

**Response** (200):
```json
{
  "symbol": "BTCUSDT",
  "side": "Buy",
  "quantity": 0.01,
  "entryPrice": 45000,
  "currentPrice": 45500,
  "unrealizedPnl": 5,
  "liveRR": 2.5,
  "takeProfit": 46000,
  "stopLoss": 44000
}
```

---

## ANALYSIS ENDPOINTS

### POST /api/analysis/chart
Analyze a chart image

**Request** (multipart/form-data):
- `image`: File (PNG/JPG)
- `symbol`: String
- `timeframe`: String

**Response** (200):
```json
{
  "id": "uuid-123",
  "symbol": "BTCUSDT",
  "timeframe": "1h",
  "recommendation": "buy",
  "confidence": 0.75,
  "entryPrice": 45000,
  "stopLoss": 44000,
  "takeProfit": 46000,
  "rr": 2.5,
  "summary": "Strong uptrend with support at 44500",
  "evidence": "Price above 200MA, RSI 65, MACD positive",
  "timestamp": "2025-11-26T10:30:00Z"
}
```

---

### GET /api/analysis/latest
Get latest analysis for all symbols

**Query Parameters**:
- `timeframe`: Filter by timeframe (optional)
- `limit`: Max results (default: 20)

**Response** (200):
```json
{
  "analyses": [
    {
      "symbol": "BTCUSDT",
      "timeframe": "1h",
      "recommendation": "buy",
      "confidence": 0.75,
      "timestamp": "2025-11-26T10:30:00Z"
    }
  ]
}
```

---

## ACCOUNT ENDPOINTS

### GET /api/account/balance
Get wallet balance

**Response** (200):
```json
{
  "totalBalance": 10000,
  "availableBalance": 9500,
  "unrealizedPnl": 500,
  "currency": "USDT"
}
```

---

### GET /api/account/stats
Get trading statistics

**Response** (200):
```json
{
  "totalTrades": 150,
  "winningTrades": 95,
  "losingTrades": 55,
  "winRate": 0.633,
  "totalPnl": 2500,
  "profitFactor": 2.1,
  "expectedValue": 16.67,
  "avgWin": 50,
  "avgLoss": -25,
  "maxWin": 500,
  "maxLoss": -200
}
```

---

## CYCLE ENDPOINTS

### POST /api/cycles/start
Start a new trading cycle

**Request**:
```json
{
  "timeframe": "1h"
}
```

**Response** (200):
```json
{
  "cycleId": "uuid-123",
  "timeframe": "1h",
  "status": "running",
  "startedAt": "2025-11-26T10:00:00Z"
}
```

---

### GET /api/cycles/:id
Get cycle status

**Response** (200):
```json
{
  "cycleId": "uuid-123",
  "timeframe": "1h",
  "status": "completed",
  "startedAt": "2025-11-26T10:00:00Z",
  "completedAt": "2025-11-26T10:05:00Z",
  "steps": {
    "slotCheck": { "status": "completed", "duration": 100 },
    "chartCapture": { "status": "completed", "duration": 2000 },
    "analysis": { "status": "completed", "duration": 5000 },
    "filtering": { "status": "completed", "duration": 500 },
    "positioning": { "status": "completed", "duration": 300 },
    "confirmation": { "status": "completed", "duration": 1000 },
    "execution": { "status": "completed", "duration": 800 }
  },
  "tradesExecuted": 3,
  "errors": []
}
```

---

## CONFIGURATION ENDPOINTS

### GET /api/config
Get current configuration

**Response** (200):
```json
{
  "trading": {
    "maxSlots": 5,
    "minConfidence": 0.55,
    "riskPercentage": 0.01
  },
  "timeframes": ["15m", "1h", "4h"],
  "symbols": ["BTCUSDT", "ETHUSDT"]
}
```

---

### PATCH /api/config
Update configuration

**Request**:
```json
{
  "trading": {
    "maxSlots": 10,
    "minConfidence": 0.60
  }
}
```

**Response** (200):
```json
{
  "success": true,
  "updated": ["trading.maxSlots", "trading.minConfidence"]
}
```

---

## WEBSOCKET EVENTS

### Connection
```typescript
const socket = io('http://localhost:3000');
socket.on('connect', () => console.log('Connected'));
```

### Subscribe to Position Updates
```typescript
socket.emit('subscribe:positions', { symbol: 'BTCUSDT' });
socket.on('position:updated', (data) => {
  console.log('Position updated:', data);
});
```

### Subscribe to Trade Events
```typescript
socket.emit('subscribe:trades');
socket.on('trade:executed', (trade) => {
  console.log('Trade executed:', trade);
});
socket.on('trade:closed', (trade) => {
  console.log('Trade closed:', trade);
});
```

### Subscribe to Cycle Events
```typescript
socket.emit('subscribe:cycles');
socket.on('cycle:started', (cycle) => {
  console.log('Cycle started:', cycle);
});
socket.on('cycle:completed', (cycle) => {
  console.log('Cycle completed:', cycle);
});
```

---

## ERROR RESPONSES

### Standard Error Format
```json
{
  "error": "Error message",
  "code": "ERROR_CODE",
  "details": {
    "field": "Additional context"
  }
}
```

### Common Error Codes
- `VALIDATION_ERROR` (400): Invalid input
- `SLOTS_EXHAUSTED` (400): No available trading slots
- `INSUFFICIENT_BALANCE` (400): Not enough balance
- `SYMBOL_LOCKED` (400): Symbol already has open position
- `BYBIT_ERROR` (502): Exchange API error
- `OPENAI_ERROR` (502): AI analysis failed
- `INTERNAL_ERROR` (500): Server error

---

## RATE LIMITING

- **Default**: 100 requests per minute per IP
- **Trading endpoints**: 10 requests per minute
- **Analysis endpoints**: 30 requests per minute

Response headers:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1700000000
```

---

## AUTHENTICATION

All endpoints require API key in header:
```
Authorization: Bearer YOUR_API_KEY
```

---

**Document Version**: 1.0  
**Last Updated**: 2025-11-26

