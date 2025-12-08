
Excellent idea! WebSocket is the right approach for real-time trading - it's faster, more efficient, and reduces API rate limit issues. Let me analyze what can be replaced and design the WebSocket architecture.

Let me also check the execution WebSocket and wallet WebSocket:

Now I have a complete picture. Let me update the implementation plan with WebSocket architecture:

---

# UPDATED IMPLEMENTATION PLAN WITH WEBSOCKET ARCHITECTURE

## WebSocket Integration Analysis

Based on Bybit's documentation, here's what can be replaced with WebSocket:

### REST API Calls → WebSocket Streams

| Current REST Call | WebSocket Stream | Benefit |
|------------------|------------------|---------|
| `get_positions()` (polled every 2 min) | `position` stream | **Real-time** position updates, no polling |
| `get_open_orders()` (polled frequently) | `order` stream | **Instant** order status changes |
| Order fill detection (polling) | `execution` stream | **Immediate** fill notifications with PnL |
| `get_wallet_balance()` | `wallet` stream | **Real-time** balance updates |

### What STAYS as REST API (cannot be WebSocket)

| Operation | Reason |
|-----------|--------|
| `place_order()` | Write operation - must be REST |
| `cancel_order()` | Write operation - must be REST |
| `set_trading_stop()` | Write operation - must be REST |
| `set_leverage()` | Write operation - must be REST |
| `get_kline()` | Historical data fetch |
| `get_instruments_info()` | Static instrument data |

---

## Complete Architecture with WebSocket

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        REAL-TIME TRADING SYSTEM                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    WEBSOCKET MANAGER                             │    │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐    │    │
│  │  │ Position  │  │  Order    │  │ Execution │  │  Wallet   │    │    │
│  │  │  Stream   │  │  Stream   │  │  Stream   │  │  Stream   │    │    │
│  │  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘    │    │
│  │        │              │              │              │           │    │
│  │        └──────────────┴──────────────┴──────────────┘           │    │
│  │                           │                                      │    │
│  │                    Event Handler                                 │    │
│  └───────────────────────────┼──────────────────────────────────────┘    │
│                              │                                           │
│                              ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    STATE MANAGER                                 │    │
│  │  - Maintains in-memory cache of positions/orders                │    │
│  │  - Syncs to database on state change                            │    │
│  │  - Triggers events for trade lifecycle                          │    │
│  └───────────────────────────┬──────────────────────────────────────┘    │
│                              │                                           │
│         ┌────────────────────┼────────────────────┐                     │
│         ▼                    ▼                    ▼                     │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐               │
│  │ Position    │     │ Trade       │     │ P&L         │               │
│  │ Monitor     │     │ Tracker     │     │ Calculator  │               │
│  │ (Tightening)│     │ (Lifecycle) │     │ (Realtime)  │               │
│  └─────────────┘     └─────────────┘     └─────────────┘               │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    TRADING ENGINE (Cycle-Based)                  │    │
│  │  - Chart capture & analysis                                      │    │
│  │  - Signal generation                                             │    │
│  │  - Order execution (REST API)                                    │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## New Module Structure

```
NextJsAppBot/V2/prototype/python/
├── trading_bot/
│   ├── __init__.py
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py          # Simplified config loader
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   │
│   │   │# 🆕 WEBSOCKET LAYER
│   │   ├── websocket_manager.py  # 🆕 WebSocket connection manager
│   │   ├── stream_handlers.py    # 🆕 Handlers for each stream type
│   │   ├── state_manager.py      # 🆕 In-memory state with DB sync
│   │   │
│   │   │# TRADING ENGINE
│   │   ├── engine.py             # 🆕 Clean trading cycle engine
│   │   ├── analyzer.py           # Keep - chart analysis
│   │   ├── trader.py             # Simplified - execution only (REST)
│   │   ├── slot_manager.py       # Simplified - uses state_manager
│   │   ├── risk_manager.py       # Simplified - position sizing
│   │   │
│   │   │# EXCHANGE API
│   │   ├── bybit_api_manager.py  # Simplified - REST only
│   │   │
│   │   │# MONITORING
│   │   ├── position_monitor.py   # 🆕 Uses WebSocket events
│   │   ├── trade_tracker.py      # 🆕 Real-time trade lifecycle
│   │   │
│   │   │# DATA
│   │   ├── data_agent.py         # Simplified - new schema
│   │   └── prompts/
│   │       └── analyzer_prompt.py
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── logging.py
│   │   └── helpers.py
│   │
│   └── data/
│       └── trading.db            # 🆕 Clean database
│
├── run_bot.py                    # 🆕 Clean entry point
└── config.yaml                   # Simplified
```

---

## WebSocket Manager Design

```python
# trading_bot/core/websocket_manager.py

class BybitWebSocketManager:
    """
    Manages WebSocket connections to Bybit.
    Provides real-time updates for:
    - Position changes
    - Order status updates
    - Execution (fill) notifications
    - Wallet balance changes
    """
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        self.ws = WebSocket(
            testnet=testnet,
            channel_type="private",
            api_key=api_key,
            api_secret=api_secret,
        )
        self._callbacks = {
            "position": [],
            "order": [],
            "execution": [],
            "wallet": []
        }
        self._state = StateManager()
        
    async def start(self):
        """Start all WebSocket streams."""
        # Subscribe to all private streams
        self.ws.order_stream(callback=self._handle_order)
        self.ws.position_stream(callback=self._handle_position)
        self.ws.execution_stream(callback=self._handle_execution)
        self.ws.wallet_stream(callback=self._handle_wallet)
        
    def _handle_order(self, message):
        """Handle order stream updates."""
        for order_data in message.get('data', []):
            order_id = order_data['orderId']
            status = order_data['orderStatus']
            symbol = order_data['symbol']
            
            # Update state
            self._state.update_order(order_id, order_data)
            
            # Trigger callbacks
            for callback in self._callbacks['order']:
                callback(order_id, status, order_data)
                
    def _handle_position(self, message):
        """Handle position stream updates."""
        for pos_data in message.get('data', []):
            symbol = pos_data['symbol']
            size = float(pos_data['size'])
            side = pos_data['side']
            
            # Update state
            self._state.update_position(symbol, pos_data)
            
            # Trigger callbacks (e.g., for SL tightening)
            for callback in self._callbacks['position']:
                callback(symbol, pos_data)
                
    def _handle_execution(self, message):
        """Handle execution (fill) stream updates."""
        for exec_data in message.get('data', []):
            order_id = exec_data['orderId']
            exec_type = exec_data['execType']
            exec_pnl = float(exec_data.get('execPnl', 0))
            
            # Update state
            self._state.record_execution(order_id, exec_data)
            
            # Trigger callbacks (e.g., trade tracking, P&L recording)
            for callback in self._callbacks['execution']:
                callback(order_id, exec_data)
                
    def on_order_update(self, callback):
        """Register callback for order updates."""
        self._callbacks['order'].append(callback)
        
    def on_position_update(self, callback):
        """Register callback for position updates."""
        self._callbacks['position'].append(callback)
        
    def on_execution(self, callback):
        """Register callback for executions/fills."""
        self._callbacks['execution'].append(callback)
```

---

## State Manager Design

```python
# trading_bot/core/state_manager.py

class StateManager:
    """
    Maintains real-time state from WebSocket updates.
    Replaces polling-based state management.
    """
    
    def __init__(self, data_agent: DataAgent):
        self.data_agent = data_agent
        
        # In-memory state (updated by WebSocket)
        self._positions: Dict[str, dict] = {}     # symbol -> position data
        self._orders: Dict[str, dict] = {}         # order_id -> order data
        self._wallet: Optional[dict] = None
        
        # Locks for thread safety
        self._position_lock = threading.Lock()
        self._order_lock = threading.Lock()
        
    def update_position(self, symbol: str, data: dict):
        """Update position state from WebSocket."""
        with self._position_lock:
            size = float(data.get('size', 0))
            if size == 0:
                # Position closed
                if symbol in self._positions:
                    del self._positions[symbol]
            else:
                self._positions[symbol] = {
                    'symbol': symbol,
                    'side': data['side'],
                    'size': size,
                    'entry_price': float(data['entryPrice']),
                    'mark_price': float(data['markPrice']),
                    'unrealised_pnl': float(data['unrealisedPnl']),
                    'leverage': data['leverage'],
                    'take_profit': float(data.get('takeProfit', 0)),
                    'stop_loss': float(data.get('stopLoss', 0)),
                    'updated_at': datetime.now(timezone.utc)
                }
                
            # Sync to database
            self._sync_position_to_db(symbol)
            
    def update_order(self, order_id: str, data: dict):
        """Update order state from WebSocket."""
        with self._order_lock:
            status = data['orderStatus']
            
            if status in ['Filled', 'Cancelled', 'Rejected']:
                # Order no longer active
                if order_id in self._orders:
                    del self._orders[order_id]
            else:
                self._orders[order_id] = {
                    'order_id': order_id,
                    'symbol': data['symbol'],
                    'side': data['side'],
                    'price': float(data['price']),
                    'qty': float(data['qty']),
                    'status': status,
                    'order_type': data['orderType'],
                    'updated_at': datetime.now(timezone.utc)
                }
                
            # Sync to database
            self._sync_order_to_db(order_id, data)
            
    def record_execution(self, order_id: str, data: dict):
        """Record execution and update trade in database."""
        exec_pnl = float(data.get('execPnl', 0))
        exec_price = float(data['execPrice'])
        exec_qty = float(data['execQty'])
        closed_size = float(data.get('closedSize', 0))
        
        # Update trade record in database with fill info
        self.data_agent.update_trade_execution(
            order_id=order_id,
            fill_price=exec_price,
            fill_quantity=exec_qty,
            pnl=exec_pnl if closed_size > 0 else None,
            status='filled' if closed_size > 0 else 'partial'
        )
        
    # Slot counting methods (replaces REST polling)
    def get_open_positions_count(self) -> int:
        """Get count of open positions from cache."""
        with self._position_lock:
            return len(self._positions)
            
    def get_open_entry_orders_count(self) -> int:
        """Get count of open entry orders from cache."""
        with self._order_lock:
            return sum(1 for o in self._orders.values() 
                      if o['status'] in ['New', 'PartiallyFilled'])
                      
    def has_position_for_symbol(self, symbol: str) -> bool:
        """Check if symbol has open position."""
        with self._position_lock:
            return symbol in self._positions
```

---

## Updated Database Schema

```sql
-- trading.db - Clean schema with WebSocket support

-- 1. Recommendations (analysis results)
CREATE TABLE recommendations (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    recommendation TEXT NOT NULL CHECK (recommendation IN ('LONG', 'SHORT', 'HOLD')),
    confidence REAL NOT NULL,
    entry_price REAL,
    stop_loss REAL,
    take_profit REAL,
    risk_reward REAL,
    reasoning TEXT,
    
    -- Audit
    chart_path TEXT,
    prompt_name TEXT NOT NULL,
    prompt_version TEXT,
    model_name TEXT DEFAULT 'gpt-4-vision-preview',
    raw_response TEXT,
    
    -- Timestamps
    analyzed_at TEXT NOT NULL,
    cycle_boundary TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_rec_symbol ON recommendations(symbol);
CREATE INDEX idx_rec_boundary ON recommendations(cycle_boundary);

-- 2. Trades (execution records with WebSocket-sourced data)
CREATE TABLE trades (
    id TEXT PRIMARY KEY,
    recommendation_id TEXT REFERENCES recommendations(id),
    
    -- Trade details
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('Buy', 'Sell')),
    entry_price REAL NOT NULL,
    quantity REAL NOT NULL,
    stop_loss REAL NOT NULL,
    take_profit REAL NOT NULL,
    leverage INTEGER DEFAULT 1,
    
    -- Exchange data (from WebSocket)
    order_id TEXT,
    order_link_id TEXT,
    
    -- Status (updated by WebSocket order stream)
    status TEXT DEFAULT 'pending' CHECK (status IN (
        'pending', 'submitted', 'new', 'partially_filled', 
        'filled', 'cancelled', 'rejected', 'closed', 'error'
    )),
    
    -- Fill data (from WebSocket execution stream)
    fill_price REAL,
    fill_quantity REAL,
    fill_time TEXT,
    
    -- Exit data (from WebSocket execution stream on close)
    exit_price REAL,
    exit_reason TEXT,
    pnl REAL,
    pnl_percent REAL,
    
    -- Audit
    timeframe TEXT,
    prompt_name TEXT,
    confidence REAL,
    dry_run INTEGER DEFAULT 0,
    
    -- Timestamps
    submitted_at TEXT,
    filled_at TEXT,
    closed_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_trades_symbol ON trades(symbol);
CREATE INDEX idx_trades_status ON trades(status);
CREATE INDEX idx_trades_order ON trades(order_id);

-- 3. Cycles (trading cycle audit trail)
CREATE TABLE cycles (
    id TEXT PRIMARY KEY,
    timeframe TEXT NOT NULL,
    cycle_number INTEGER NOT NULL,
    boundary_time TEXT NOT NULL,
    
    status TEXT DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed', 'skipped')),
    skip_reason TEXT,
    
    -- Metrics
    charts_captured INTEGER DEFAULT 0,
    analyses_completed INTEGER DEFAULT 0,
    recommendations_generated INTEGER DEFAULT 0,
    trades_executed INTEGER DEFAULT 0,
    
    -- State at cycle start
    available_slots INTEGER,
    open_positions INTEGER,
    
    -- Timestamps
    started_at TEXT NOT NULL,
    completed_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_cycles_boundary ON cycles(boundary_time);

-- 4. Config (dashboard-editable settings)
CREATE TABLE config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('string', 'number', 'boolean', 'json')),
    category TEXT NOT NULL,
    description TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

-- 5. Executions (WebSocket execution log for audit)
CREATE TABLE executions (
    id TEXT PRIMARY KEY,
    trade_id TEXT REFERENCES trades(id),
    order_id TEXT NOT NULL,
    
    -- Execution details (from WebSocket)
    exec_id TEXT NOT NULL,
    exec_price REAL NOT NULL,
    exec_qty REAL NOT NULL,
    exec_value REAL,
    exec_fee REAL,
    exec_pnl REAL,
    exec_type TEXT,  -- Trade, Funding, etc.
    is_maker INTEGER,
    
    -- Timestamp
    exec_time TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_exec_order ON executions(order_id);
CREATE INDEX idx_exec_trade ON executions(trade_id);

-- 6. Position snapshots (for historical tracking)
CREATE TABLE position_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    side TEXT,
    size REAL,
    entry_price REAL,
    mark_price REAL,
    unrealised_pnl REAL,
    take_profit REAL,
    stop_loss REAL,
    
    -- Snapshot metadata
    snapshot_reason TEXT,  -- 'tightening', 'periodic', 'close'
    snapshot_time TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_snapshot_symbol ON position_snapshots(symbol);
```

---

## Benefits of WebSocket Architecture

| Aspect | Polling (Current) | WebSocket (New) |
|--------|------------------|-----------------|
| **Latency** | 2+ seconds (API delay + poll interval) | <100ms (real-time push) |
| **API Calls** | ~30/min for position monitoring | 0 (stream-based) |
| **Rate Limits** | Risk of hitting limits | No impact on rate limits |
| **Fill Detection** | Can miss fills between polls | Guaranteed instant notification |
| **P&L Tracking** | Calculated manually | Exact P&L from exchange |
| **Position Close** | Detected on next poll | Instant notification with exit price |

---

## Dashboard-Configurable Settings (16 Settings)

These remain the same as before but are now also used by the WebSocket-based components:

| Category | Setting | Type | Default |
|----------|---------|------|---------|
| **Trading** | paper_trading | boolean | false |
| | auto_approve_trades | boolean | true |
| | min_confidence_threshold | number | 0.75 |
| | min_rr | number | 1.5 |
| | risk_percentage | number | 0.01 |
| | max_loss_usd | number | 10.0 |
| | leverage | number | 2 |
| | max_concurrent_trades | number | 3 |
| **Tightening** | enable_position_tightening | boolean | true |
| | enable_sl_tightening | boolean | true |
| | rr_tightening_steps | json | {...} |
| **Sizing** | use_enhanced_position_sizing | boolean | true |
| | min_position_value_usd | number | 50.0 |
| **Replacement** | enable_intelligent_replacement | boolean | true |
| | min_score_improvement | number | 0.15 |
| **Exchange** | use_testnet | boolean | false |

---

## Implementation Order

1. **Phase 1: Database & Config** (Day 1)
   - Create new `trading.db` with clean schema
   - Implement config table with dashboard defaults
   - Create simplified settings loader

2. **Phase 2: WebSocket Layer** (Day 1-2)
   - Implement `BybitWebSocketManager`
   - Implement `StateManager` with in-memory cache
   - Implement stream handlers for order/position/execution/wallet

3. **Phase 3: Trading Engine** (Day 2-3)
   - Create clean `engine.py` with cycle-based workflow
   - Integrate with WebSocket state (no polling)
   - Implement clean `slot_manager.py` using StateManager

4. **Phase 4: Monitoring** (Day 3)
   - Create event-driven `position_monitor.py`
   - Implement `trade_tracker.py` for lifecycle management
   - Connect tightening logic to position stream

5. **Phase 5: Integration & Testing** (Day 4)
   - Full integration testing
   - Dry-run validation
   - Dashboard API endpoints

---

Ready to proceed with implementation? I'll start with Phase 1 (Database & Config) if you confirm.
