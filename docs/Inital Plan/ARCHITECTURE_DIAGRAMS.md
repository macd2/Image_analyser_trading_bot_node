# Architecture Diagrams: Autotrader Next.js

## 1. SYSTEM OVERVIEW

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INTERFACE                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Live Monitor │  │ Trade History│  │ Backtest     │           │
│  │ (Real-time)  │  │ & Analytics  │  │ & Prompt     │           │
│  │              │  │              │  │ Builder      │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│         │                 │                  │                   │
│         └─────────────────┼──────────────────┘                   │
│                           │                                      │
│                    WebSocket + REST API                          │
│                           │                                      │
└───────────────────────────┼──────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────┐
│                    NEXT.JS API LAYER                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ /api/trades  │  │ /api/positions│  │ /api/analysis│           │
│  │ /api/cycles  │  │ /api/account  │  │ /api/config  │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│                           │                                      │
└───────────────────────────┼──────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────┐
│                  BACKEND SERVICES (Node.js)                      │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ TRADING ENGINE                                          │    │
│  │ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐    │    │
│  │ │ChartSourcer  │ │ChartAnalyzer │ │SignalValidator    │    │
│  │ │(TradingView) │ │(OpenAI GPT4) │ │(Validation)  │    │    │
│  │ └──────────────┘ └──────────────┘ └──────────────┘    │    │
│  │ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐    │    │
│  │ │TradeExecutor │ │PositionMgr   │ │RiskManager   │    │    │
│  │ │(Bybit)       │ │(Tracking)    │ │(Sizing)      │    │    │
│  │ └──────────────┘ └──────────────┘ └──────────────┘    │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ REAL-TIME SERVICES                                      │    │
│  │ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐    │    │
│  │ │WebSocket     │ │Job Queue     │ │Position      │    │    │
│  │ │Server        │ │(Bull/Redis)  │ │Monitor       │    │    │
│  │ │(Socket.io)   │ │              │ │(Every 2min)  │    │    │
│  │ └──────────────┘ └──────────────┘ └──────────────┘    │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ EXTERNAL INTEGRATIONS                                   │    │
│  │ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐    │    │
│  │ │Bybit API     │ │OpenAI API    │ │Telegram Bot  │    │    │
│  │ │(Trading)     │ │(Analysis)    │ │(Notifications)    │    │
│  │ └──────────────┘ └──────────────┘ └──────────────┘    │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                   │
└───────────────────────────┬──────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
   ┌────▼──────┐      ┌─────▼──────┐      ┌────▼──────┐
   │ PostgreSQL │      │   Redis    │      │  SQLite   │
   │ (Primary)  │      │  (Cache)   │      │  (Local)  │
   │            │      │            │      │           │
   │ - Trades   │      │ - Sessions │      │ - Backup  │
   │ - Analysis │      │ - Cache    │      │ - Logs    │
   │ - Positions│      │ - Queue    │      │           │
   │ - Stats    │      │            │      │           │
   └────────────┘      └────────────┘      └───────────┘
```

---

## 2. TRADING CYCLE FLOW

```
START CYCLE
    │
    ▼
┌─────────────────────────────────────┐
│ STEP 0: Cycle-Level Slot Check      │
│ - Check if slots available          │
│ - Skip if full                      │
└─────────────────────────────────────┘
    │
    ├─ NO SLOTS ──────────────────────┐
    │                                  │
    │                            SKIP CYCLE
    │                                  │
    ▼                                  │
┌─────────────────────────────────────┐│
│ STEP 1: Fresh Data Check            ││
│ - Check for existing analysis       ││
│ - Use if exists, capture if not     ││
└─────────────────────────────────────┘│
    │                                  │
    ▼                                  │
┌─────────────────────────────────────┐│
│ STEP 2: Chart Capture & Analysis    ││
│ - Capture from TradingView          ││
│ - Analyze with GPT-4 Vision         ││
│ - Store results in DB               ││
└─────────────────────────────────────┘│
    │                                  │
    ▼                                  │
┌─────────────────────────────────────┐│
│ STEP 3: Signal Filtering            ││
│ - Validate signals                  ││
│ - Deduplicate by symbol             ││
│ - Rank by score                     ││
│ - Keep top N (N = available slots)  ││
└─────────────────────────────────────┘│
    │                                  │
    ▼                                  │
┌─────────────────────────────────────┐│
│ STEP 4: Position Sizing             ││
│ - Calculate risk per trade          ││
│ - Calculate position size           ││
│ - Validate min/max quantities       ││
└─────────────────────────────────────┘│
    │                                  │
    ▼                                  │
┌─────────────────────────────────────┐│
│ STEP 5: Telegram Confirmation       ││
│ - Send to user (if manual mode)     ││
│ - Wait for approval (60s timeout)   ││
│ - Auto-approve if enabled           ││
└─────────────────────────────────────┘│
    │                                  │
    ▼                                  │
┌─────────────────────────────────────┐│
│ STEP 6: Trade Execution             ││
│ - Place orders on Bybit             ││
│ - Store in database                 ││
│ - Emit WebSocket updates            ││
└─────────────────────────────────────┘│
    │                                  │
    ▼                                  │
┌─────────────────────────────────────┐│
│ Sleep until next cycle boundary     ││
│ (e.g., next :00 for 1h timeframe)   ││
└─────────────────────────────────────┘│
    │                                  │
    └──────────────────────────────────┘
         │
         ▼
    REPEAT CYCLE
```

---

## 3. DATA FLOW: CHART TO TRADE

```
TradingView
    │
    ▼
┌──────────────────────┐
│ ChartSourcer         │
│ (Playwright)         │
│ Capture PNG          │
└──────────────────────┘
    │
    ▼
┌──────────────────────┐
│ Store Image          │
│ /public/charts/      │
└──────────────────────┘
    │
    ▼
┌──────────────────────┐
│ ChartAnalyzer        │
│ (OpenAI GPT-4)       │
│ Analyze Image        │
└──────────────────────┘
    │
    ▼
┌──────────────────────┐
│ Parse Response       │
│ Extract:             │
│ - Recommendation     │
│ - Confidence         │
│ - Entry/SL/TP        │
│ - Summary            │
└──────────────────────┘
    │
    ▼
┌──────────────────────┐
│ Calculate Confidence │
│ Formula:             │
│ 40% Setup Quality    │
│ 25% Risk-Reward      │
│ 35% Market Env       │
└──────────────────────┘
    │
    ▼
┌──────────────────────┐
│ Store in DB          │
│ analysis_results     │
└──────────────────────┘
    │
    ▼
┌──────────────────────┐
│ SignalValidator      │
│ Check:               │
│ - Confidence >= min  │
│ - No recent similar  │
│ - Risk score OK      │
└──────────────────────┘
    │
    ├─ INVALID ──────────────────┐
    │                             │
    │                        SKIP SIGNAL
    │                             │
    ▼                             │
┌──────────────────────┐         │
│ Recommender          │         │
│ Rank & Filter        │         │
│ Keep top N           │         │
└──────────────────────┘         │
    │                             │
    ▼                             │
┌──────────────────────┐         │
│ RiskManager          │         │
│ Calculate Size       │         │
│ Check Slots          │         │
└──────────────────────┘         │
    │                             │
    ▼                             │
┌──────────────────────┐         │
│ TelegramBot          │         │
│ Send for Approval    │         │
└──────────────────────┘         │
    │                             │
    ▼                             │
┌──────────────────────┐         │
│ TradeExecutor        │         │
│ Place Order on Bybit │         │
└──────────────────────┘         │
    │                             │
    ▼                             │
┌──────────────────────┐         │
│ Store Trade in DB    │         │
│ trades table         │         │
└──────────────────────┘         │
    │                             │
    ▼                             │
┌──────────────────────┐         │
│ Emit WebSocket       │         │
│ Update UI            │         │
└──────────────────────┘         │
    │                             │
    └─────────────────────────────┘
         │
         ▼
    TRADE ACTIVE
```

---

## 4. REAL-TIME POSITION MONITORING

```
Every 2 Minutes (Background Job)
    │
    ▼
┌──────────────────────────────────┐
│ PositionMonitor Job              │
│ (Bull Queue Processor)           │
└──────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────┐
│ Fetch Open Positions             │
│ From Bybit API                   │
└──────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────┐
│ For Each Position:               │
│ - Get current price              │
│ - Calculate unrealized P&L       │
│ - Calculate live R/R             │
└──────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────┐
│ Check if Profitable              │
│ (unrealized_pnl > 0)             │
└──────────────────────────────────┘
    │
    ├─ YES ──────────────────────┐
    │                             │
    │                    ┌────────▼──────────┐
    │                    │ Calculate Tighter │
    │                    │ Stop Loss         │
    │                    └────────┬──────────┘
    │                             │
    │                    ┌────────▼──────────┐
    │                    │ Update SL on      │
    │                    │ Bybit             │
    │                    └────────┬──────────┘
    │                             │
    │                    ┌────────▼──────────┐
    │                    │ Log Adjustment    │
    │                    └────────┬──────────┘
    │                             │
    ▼                             │
┌──────────────────────────────────┐│
│ Store Position Data in DB        ││
│ position_tracking table          ││
└──────────────────────────────────┘│
    │                               │
    ▼                               │
┌──────────────────────────────────┐│
│ Emit WebSocket Update            ││
│ position:updated event           ││
└──────────────────────────────────┘│
    │                               │
    └───────────────────────────────┘
         │
         ▼
    WAIT 2 MINUTES
    REPEAT
```

---

## 5. DATABASE RELATIONSHIPS

```
analysis_results
    │
    ├─ id (PK)
    ├─ symbol
    ├─ timeframe
    ├─ recommendation
    ├─ confidence
    ├─ entry_price
    ├─ stop_loss
    ├─ take_profit
    ├─ image_path
    ├─ timestamp
    └─ analysis_data (JSON)
         │
         │ (1:N)
         ▼
    trades
        │
        ├─ id (PK)
        ├─ recommendation_id (FK)
        ├─ symbol
        ├─ side
        ├─ quantity
        ├─ entry_price
        ├─ take_profit
        ├─ stop_loss
        ├─ order_id
        ├─ pnl
        ├─ status
        ├─ prompt_name
        ├─ created_at
        └─ closed_at
             │
             │ (1:N)
             ▼
        position_tracking
            │
            ├─ id (PK)
            ├─ trade_id (FK)
            ├─ symbol
            ├─ entry_price
            ├─ current_price
            ├─ live_rr
            ├─ unrealized_pnl
            └─ checked_at

trading_stats
    │
    ├─ id (PK)
    ├─ symbol
    ├─ timeframe
    ├─ total_trades
    ├─ winning_trades
    ├─ losing_trades
    ├─ total_pnl
    ├─ win_rate
    ├─ profit_factor
    └─ expected_value

trade_states
    │
    ├─ id (PK)
    ├─ trade_id
    ├─ symbol
    ├─ current_state
    ├─ main_order_id
    ├─ tp_order_id
    ├─ sl_order_id
    ├─ entry_price
    ├─ current_tp
    ├─ current_sl
    └─ exit_triggered_by
```

---

## 6. DEPLOYMENT ARCHITECTURE

```
┌─────────────────────────────────────────────────────────┐
│                    GitHub Repository                    │
│  (Code, Tests, CI/CD Workflows)                         │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
        ┌────────────────────────────┐
        │   GitHub Actions CI/CD     │
        │ - Run tests                │
        │ - Build Docker image       │
        │ - Push to registry         │
        └────────────────┬───────────┘
                         │
                         ▼
        ┌────────────────────────────┐
        │   Docker Registry          │
        │ (Docker Hub / ECR)         │
        └────────────────┬───────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                  Production Server                      │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Docker Compose                                   │  │
│  │                                                  │  │
│  │ ┌──────────────┐  ┌──────────────┐             │  │
│  │ │ Next.js App  │  │ PostgreSQL   │             │  │
│  │ │ Container    │  │ Container    │             │  │
│  │ │ Port: 3000   │  │ Port: 5432   │             │  │
│  │ └──────────────┘  └──────────────┘             │  │
│  │                                                  │  │
│  │ ┌──────────────┐  ┌──────────────┐             │  │
│  │ │ Redis        │  │ Nginx        │             │  │
│  │ │ Container    │  │ (Reverse     │             │  │
│  │ │ Port: 6379   │  │  Proxy)      │             │  │
│  │ └──────────────┘  └──────────────┘             │  │
│  │                                                  │  │
│  │ Volumes:                                         │  │
│  │ - postgres_data                                  │  │
│  │ - redis_data                                     │  │
│  │ - app_logs                                       │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
│  Environment Variables:                                │
│  - DATABASE_URL                                        │
│  - REDIS_URL                                           │
│  - BYBIT_API_KEY                                       │
│  - OPENAI_API_KEY                                      │
│  - TELEGRAM_BOT_TOKEN                                  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

**Document Version**: 1.0  
**Last Updated**: 2025-11-26

