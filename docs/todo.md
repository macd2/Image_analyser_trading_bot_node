

[ ] add the watchlist symbols from capture page somewhere fitting in the instance card

[ ] is the the value from confidence calculation from analysis actually used in the bot for trading deccisions?

------

[ ] run production audit in terms of security, efficency and robustness (minal changes )

----
[ ] the simulator is not running in the background for a fact or the ui is not updating when i visited the page the data for the alst check was 2 hure ago
[ ] the ui must also respect the filld time one card shows tp hit altough the trade is still pending fill.
----
[ ] explain waht exaclty is the dirrenferece between the marker in trades for status papertrade and dry-run 
----


[ ] we need  a new service the job of this advisor is to inject extra context in to the prompt before seding it to the assitant. the bot loop must wait for this advisor to complete it must be fully tracable for the logtrail
[ ] it must also be plugged in after we got the reccomendation from the ai so we can ad extra info
[ ] the advisor must work with candle data only and should use import pandas_ta as ta 
[ ] advisor must be intergrated with global database layer. The job is to perform classic ta based on configurable strategies. the first strategy to integrate is:
docs/Strategies/trade_entry_strategies_E3lYZsy8nYE_HH_LL_alex_strat.md
[ ] instance needs a setting for which strategy to use for advisor. 
[ ] the architecture should be nodes based so we can combine strategies or individual functions the advisor needs its own page and the ui should show and make this node systhe editable. 
[ ] one streategy we need is: docs/Strategies/market regime_check.py

-----

[ ] make sure all chart modals have the signal and entry marker
[ ] position tab in /instance should also show the dryrun positions 
[ ] the simulator should act a a kind of exchange for dry run trades im not sure waht the best architecture is but we want to simulate stoploss tigheting an also order replacement 
[ ] add a new card to overview tab that visually shows the current step of the cycle we are in. So getting charts, analyzing images, risk management, Order execution, waiting for next cycle (wait time)
[ ] also add a stats card  with  key information like which cycle we are on, for how long the bot was running
[ ] adjust the perfomance stats so it is by defualt per run but with a dropdown filter to change to 1 day 7 days 1 week and all time
[ ] the open position must also show dry run positions for this instance 

-----

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


-------


Confirmed Issue:

The BacktestStore class used by /api/tournament/history route:

Always uses SQLite - _connect() method at line 399-401 uses sqlite3.connect() directly
Does NOT respect DB_TYPE=postgres - No PostgreSQL support whatsoever
In production (Railway), DB_TYPE=postgres is set, but BacktestStore still tries to use local SQLite file data/backtests.db which:
Either doesn't exist on Railway
Or is empty (ephemeral filesystem)
Or times out trying to create/access it
This is why the "Recent Tournament Runs" section takes forever and shows no data in production - the Python BacktestStore is querying a non-existent or empty SQLite database instead of Supabase PostgreSQL.

The tournament data is likely stored in Supabase PostgreSQL (via other parts of the system), but the /api/tournament/history route uses BacktestStore which can't read from PostgreSQL.

Would you like me to fix this by updating BacktestStore to use the centralized database client (python/trading_bot/db/client.py) that properly handles SQLite/PostgreSQL switching?

---


