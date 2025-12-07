

[ ] add the watchlist symbols from capture page somewhere fitting in the instance card

[ ] is the the value from Confidence Calculation from analysis actually used in the bot for trading deccisions?

------

[ ] run production audit in terms of security, efficency and robustness (minal changes )

[ ] 

[ ] add the watchlist symbols from capture page somewhere fitting in the instance card

[ ] is the the value from Confidence Calculation from analysis actually used in the bot for trading deccisions?

------

[ ] run production audit in terms of security, efficency and robustness (minal changes )

----

[ ] we need  a new service the job of this advisor is to inject extra context in to the popmt before seding it to tha ssitant the bot loop must wait for this advisor to complete it must be fully tracable for the logtrail
[ ] the advisor must work with candle data only ad should use import pandas_ta as ta
and must be intergrated with global database layer. The job is to perform classic ta based on configurable strategies. the first strategy to integrate is:
docs/Strategies/trade_entry_strategies_E3lYZsy8nYE_HH_LL_alex_strat.md
[ ] this advisor needs a ui and must beable to store end retrieve settings find a flexible format for how to standrdize strategies so we can load and store different strategies 
[ ] instance needs a setting for which strategy to use for advisor. 


[ ]
## 🔍 Investigation Complete: OpenAI Credit Exhaustion Error Handling

### **Current Situation:**

**Error Log:**
```
2025-12-07 11:34:45 | ERROR | trading_bot.core.timeframe_extractor | OpenAI API rate limit exceeded (429): Out of credits or too many requests. Skipping timeframe extraction.
```

### **Where OpenAI API Calls Occur:**

1. **`timeframe_extractor.py`** (Lines 83-107)
   - ✅ **HAS 429 handling** - catches HTTPError 429
   - ❌ **Current behavior**: Returns `None` and logs error
   - **Impact**: Chart analysis is skipped with `skip_reason: "missing_timeframe"`

2. **`timestamp_extractor.py`** (Lines 138-154, 266-282)
   - ❌ **NO 429 handling** - only catches generic `RequestException`
   - **Current behavior**: Returns error message string
   - **Impact**: Analysis may fail or use incorrect timestamp

3. **`simple_openai_handler.py`** (Assistant API)
   - ❌ **NO 429 handling** - no specific rate limit error handling
   - **Current behavior**: Generic exception handling
   - **Impact**: Analysis fails with generic error

4. **`analyzer.py`** (Vision API - Lines 851-920)
   - ❌ **NO 429 handling** - no specific rate limit error handling
   - **Current behavior**: Generic exception handling
   - **Impact**: Analysis fails

### **What Happens When 429 Occurs:**

**Current Flow:**
```
1. TimeframeExtractor.extract_timeframe_from_image() catches 429
2. Returns None
3. Analyzer checks if timeframe is None (line 346)
4. Returns {"recommendation": "hold", "skipped": True, "skip_reason": "missing_timeframe"}
5. Bot continues to next symbol - NO HALT
```

**Problem:** The bot silently skips the chart and continues running. User has no visibility that credits are exhausted.

### **Existing Pause/Resume Pattern (Login State Manager):**

The codebase already has a **proven pattern** for pausing the bot and waiting for user action:

**Pattern Components:**
1. **State File**: `python/trading_bot/data/login_state.json`
2. **Python Manager**: `python/trading_bot/core/login_state_manager.py`
3. **API Endpoint**: `app/api/bot/login/route.ts` (GET state, POST actions)
4. **UI Banner**: Shows when `state === 'waiting_for_login'`
5. **Bot Polling**: Sourcer polls `is_login_confirmed()` every 2 seconds
6. **Resume**: When user clicks button, state changes to `login_confirmed`, bot continues

### **Proposed Solution Design:**

**1. Create Credit State Manager** (mirror login_state_manager.py)
   - File: `python/trading_bot/core/credit_state_manager.py`
   - State file: `python/trading_bot/data/credit_exhaustion_state.json`
   - States: `ok`, `exhausted`
   - Functions:
     - `set_credit_exhausted(service: str, message: str)`
     - `is_credit_exhausted() -> bool`
     - `clear_credit_exhaustion()`
     - `get_credit_state() -> dict`

**2. Modify OpenAI API Call Sites**
   - `timeframe_extractor.py` (line 98): Call `set_credit_exhausted("openai", "...")`
   - `timestamp_extractor.py`: Add 429 handling
   - `simple_openai_handler.py`: Add 429 handling
   - `analyzer.py`: Add 429 handling

**3. Add Bot Pause Logic**
   - In `run_bot.py` main loop (line 356): Check `is_credit_exhausted()` every iteration
   - When detected, enter pause loop (similar to login wait loop in sourcer.py line 3401)
   - Poll every 2 seconds for credit state to be cleared
   - Log: "⏸️ Bot paused: OpenAI credits exhausted. Waiting for user to recharge..."

**4. Create API Endpoint**
   - `app/api/bot/credit-state/route.ts`
   - GET: Return current credit state
   - POST: Action `resume` - clears credit exhaustion state

**5. Create UI Banner Component**
   - `components/CreditExhaustionBanner.tsx`
   - Polls `/api/bot/credit-state` every 3 seconds
   - Shows when `state === 'exhausted'`
   - Message: "⚠️ OpenAI credits exhausted. Recharge your credits and click Resume."
   - Button: "Resume Bot" (always active)
   - On click: POST to `/api/bot/credit-state` with `action: 'resume'`

**6. Add Banner to Layout**
   - Import in instance layout
   - Render at top of page (similar to login banner)

### **Key Design Decisions:**

✅ **Reuse proven pattern** - Login state manager works perfectly, replicate it
✅ **File-based state** - Simple, works across Python/Node.js boundary
✅ **Pause in main loop** - Bot stays "running" but paused, can resume instantly
✅ **Always-active button** - User can click anytime after recharging
✅ **Service-agnostic** - Can extend to other API credit issues (Anthropic, etc.)

### **Files That Need Changes:**

**New Files (5):**
- `python/trading_bot/core/credit_state_manager.py`
- `app/api/bot/credit-state/route.ts`
- `components/CreditExhaustionBanner.tsx`

**Modified Files (5):**
- `python/trading_bot/core/timeframe_extractor.py` (add state manager call)
- `python/trading_bot/core/timestamp_extractor.py` (add 429 handling)
- `python/trading_bot/core/simple_openai_handler.py` (add 429 handling)
- `python/run_bot.py` (add pause loop in main cycle)
- Instance layout (add banner component)

Would you like me to proceed with implementing this solution, or do you have any questions/changes to the design?

--------

