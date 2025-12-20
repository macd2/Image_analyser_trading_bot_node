In summary:

dry_run classifies the trade as simulated vs. live.
status = 'paper_trade' marks a simulated trade that is awaiting fill by the paper‑trade simulator.
Example scenarios:

A paper trade just created: dry_run = 1, status = 'paper_trade'.
After the simulator fills it: dry_run = 1, status = 'filled'.
A live trade: dry_run = 0, status = 'submitted' (or 'filled', etc.).
This distinction allows the system to track the overall nature of a trade (dry_run) while also managing its progression through the simulation pipeline (status).
--------------

# General 
[ ] run production audit in terms of security, efficency and robustness (minal changes )

----

# Improvments 
[ ] is the the value from confidence calculation from analysis actually used in the bot for trading deccisions?
- Yes

----


# Advisor 
[ ] we need  a new service the job of this advisor is to inject extra context in to the prompt before seding it to the assitant. the bot loop must wait for this advisor to complete it must be fully tracable for the logtrail
[ ] it must also be plugged in after we got the reccomendation from the ai so we can ad extra info
[ ] the advisor must work with candle data only and should use import pandas_ta as ta 
[ ] advisor must be intergrated with global database layer. The job is to perform classic ta based on configurable strategies. the first strategy to integrate is:
docs/Strategies/trade_entry_strategies_E3lYZsy8nYE_HH_LL_alex_strat.md
[ ] instance needs a setting for which strategy to use for advisor. 
[ ] the architecture should be nodes based so we can combine strategies or individual functions the advisor needs its own page and the ui should show and make this node systhe editable. 
[ ] one streategy we need is: docs/Strategies/market regime_check.py

-----

# OpenAI Credit Exhaustion Error Handling

**Error Log:**
```
2025-12-07 11:34:45 | ERROR | trading_bot.core.timeframe_extractor | OpenAI API rate limit exceeded (429): Out of credits or too many requests. Skipping timeframe extraction.
```

catch this error pause the bot imidialy and display a banner with confirm button once confirm is clicked resume the bot. 
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
# for statstis this could mess up vlaues because we ae getting later the already filled but cancled trades in our pnl calculaiton need some thought 

In the first cancellation block (lines 424-437):

UPDATE trades SET
  exit_price = ?,
  exit_reason = 'max_bars_exceeded',
  closed_at = ?,
  pnl = 0,
  pnl_percent = 0,
  status = 'cancelled'
WHERE id = ?
The exit_price is set to currentPrice (the variable from line 416). So yes, exit price is set.

In the second cancellation block (lines 556-572):

UPDATE trades SET
  exit_price = ?,
  exit_reason = 'max_bars_exceeded',
  closed_at = ?,
  pnl = ?,
  pnl_percent = ?,
  status = 'cancelled'
WHERE id = ?
Again, exit_price is set to currentPrice (line 544). So indeed, the simulator sets exit price for cancelled trades.


------
[ ] each part of the trading cycle must be instance aware
[ ] each step of the trading cycle must check its own data iteegrety 
[ ] each part of the trading cylce must be timeframe and boundery aware
- example sources must check if there already images for the current timeframe and boundery
- cleaner must only clean images that are outside the crrent boundery based on tieframe 
[ ] analyzer must only analze images if there is no recomendation for current timeframe and boundery and instance than return results as if it analyzed them but with the note of chached results so later parts of the code can run 
[ ] execution must check in dry run of the given recomendation was already executed based on database status in live trading ofcause based on exchnage data
[ ] we need to define a set of error that pause the bot permantly until manually resumed

----

[ ] the cleaner step from trade cycle must be a microservice calle by rhe innstance and manage duplicated calles, since it can be used by multiple istance if that happens than the one that was launched second thors error becuase it cant find the imagease already  cleaned up by the first instance 

[ ] 2025-12-12 11:06:25 | ERROR | __main__ | Failed to check for OpenAI rate limit error: tuple index out of range
[ErrorLogger] ✅ Stored ERROR to DB: Failed to check for OpenAI rate limit error: tuple index out of range
2025-12-12 11:06:28 | INFO | __main__ | 

also the banner is blocking the ui it should be less highs yes promitnetn but not makingg the dashboard unusalble 

---------
🔴 REMAINING HARDCODED VALUES (12 values across 4 categories)
These should be converted to configurable settings:

1. Position Sizer Confidence Thresholds (4 values)

low_conf_threshold = 0.70
high_conf_threshold = 0.85
low_conf_weight = 0.8
high_conf_weight = 1.2
Location:  python/trading_bot/engine/position_sizer.py (lines 35-38)
2. Signal Ranking Weights (4 values)

confidence_weight = 0.4
risk_reward_weight = 0.3
setup_quality_weight = 0.2
market_environment_weight = 0.1
Location:  python/trading_bot/engine/trading_cycle.py (lines 57-61)
3. ADX Tightening Parameters (3 values)

adx_threshold = 25
adx_moderate_threshold = 20
strong_trend_multiplier = 1.2
Location:  python/trading_bot/core/adx_stop_tightener.py (lines 116, 129, 327)
4. RR Normalization Cap (1 value)

rr_scoring_cap = 5
Location:  python/trading_bot/engine/trading_cycle.py (line 822)


convert these hardcoded values to configurable settings
-- 

[ ] the sumulator activity must be a shared component used in the simulator page and also the instanve overview page replace individual components with the sahred one

-----

# Logtrail
[ ] right now i have fast trader ad playboy 1 running but the   
[ ] logtrails only shows active for fastrader
[ ] it themes like i do not see older logs for some reason
[ ] for example the eader fir playboy shows trades 35 trades ut only 2 cycles? 


-----

[ ] start server with log filter:
cd /home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node && npm run dev 2>&1 | grep -E "\[Auto-Close\]|Bybit API request" | head -50

to adust the amount of logs to leoad per instance in logtrails than adjust this:
 // Get runs for this instance (cap at 5 to balance performance with showing historical data)
    const runsLimit = Math.min(limit, 5);

    in lib/db/trading-db.ts


    ----

------

old agent mories:
# Deployment
- For Railway deployments, use Railpack instead of Nixpacks (which is deprecated).

# Bybit API
- For wallet balance and all private Bybit API endpoints (including WebSocket connections), always fetch real data from Bybit API regardless of paper_trading or testnet mode switches - only trade execution should respect paper_trading mode.
- For Bybit real-time data (wallet balance, positions), use the existing centralized Bybit WebSocket connection instead of REST API calls to avoid latency and spawning processes.
- All candle/kline fetches from Bybit API should check if candles exist in database first, and if not, store them after fetching - candle data should be cached in the klines table on every fetch.
- When fetching candles, if cache has insufficient data, must fallback to API and fetch enough candles to meet minimum requirement; API limit parameter should be configurable or removed to allow fetching full available history.

# Database
- All database connections MUST go through the centralized database layer (python/trading_bot/db/client.py) - this is the single source of truth for database operations. No direct sqlite3 or psycopg2 imports should be used anywhere in the codebase.
- For database design: prioritize simplicity and query performance.
- For database design: prefer simplest schema with efficient joins over denormalization - avoid adding instance_id to tables if it can be joined through existing relationships (cycles→runs→instances). Prioritize query performance and schema simplicity.
- for testing ALWAYS use direct databde connection via terminal and the DATBASE_URL from env local
- Store strategy-specific metadata (beta, spread_mean, spread_std, z_score) in raw_response JSON field rather than adding new strategy-specific tables or columns - keeps schema generic and scalable for any strategy type.
- For database migrations: use Supabase CLI to pull clean remote state and sync locally to match remote state; ignore SQLite migrations for now and focus on PostgreSQL only.
- All migrations in lib/db/migrations/ are PostgreSQL-compatible - there should be no SQLite-specific migrations (no AUTOINCREMENT syntax). The codebase uses PostgreSQL exclusively for migrations.
- Always read the actual code implementation before writing tests. Create comprehensive production database integration tests that validate all calculated values (not mocks) are correctly stored to and retrieved from the actual database - this ensures data integrity end-to-end.

# Git
- Never push to git without explicitly asking for permission first, even if user says to commit and push.
- I NEVER push or commit without asking!
- I NEVER GIT RESTORE witout asking first!
- NEVER lose local changes - always preserve and commit all local modifications. When git issues occur, prioritize recovering/preserving local work over any other consideration.

# Multi-Instance Trading
- Multi-instance trading audit complete: System is 90% ready but has 3 critical issues - (1) StateManager tracks by symbol only not (instance_id, symbol), (2) WebSocket single connection limit per API key, (3) PositionMonitor tracks by symbol only. Short-term solution: symbol isolation per instance. Long-term: instance-aware state tracking.
- Multi-instance trading cycle architecture: 1) Every part of trading cycle must be instance-aware (filter by instance_id), 2) Skip logic: check existing recommendations for current instance+boundary, only source/analyze missing symbols, then process all results, 3) Analyzer must return results for all symbols (including skipped) so downstream processing works.

# Symbol Handling
- The .P suffix for perpetual contracts should be handled by the sourcer layer, not in configuration templates - sourcer must ensure correct chart images are stored with correct symbol names (operation critical).
- Volume filtering added to pair screeners: fetch_tickers_for_volume() batches 50 symbols per API call to get 24h turnover, filters symbols >= $50M volume before fetching candles - saves massive API bandwidth by filtering low-volume assets early.
- Cointegration strategy pair trades must store the main symbol (not just the pair) in recommendation output for downstream compatibility with boundary checking and trade execution logic.

# Logging
- Live bot logs must be robust and persistent: (1) Store all errors/warnings to database, (2) Handle multiple instances running simultaneously, (3) Survive browser close/reopen, (4) Always display live output in OverviewTab - this is essential functionality.
- Bot logs must be instance-aware and delivered via WebSocket (Socket.IO) for real-time updates, not via API polling endpoints.
- Cointegration analysis logging should include a counter showing which analysis this is out of total (e.g., '1/10'). Screener should log a summary showing: number of pairs found, storage location for JSON output, or read location if cache was used.

# Strategy System
- Strategy system: sourcer → cleaner → [pluggable strategy] → rest of pipeline. All strategies must return same format as prompt analyzer. Strategies are Python files in strategies/ folder that can be selected/swapped at runtime.
- Strategy system: sourcer → cleaner → [pluggable strategy] → rest of pipeline. All strategies must return same format as prompt analyzer and store recommendations identically for 100% compatibility. Code after analyzer should remain unchanged.
- When implementing new features in strategies: create a proper task list first, then implement step by step. Only modify python/trading_bot/strategies - do not touch UI or trading cycle code.
- Strategy architecture: Each strategy is independent and self-contained (sourcer + analyzer combined). Create a prompt strategy that replicates current trading cycle (sourcer→cleaner→analyzer) functionality so different strategies can be tested interchangeably.
- Chart-based strategy reads symbols from TradingView charts (images). Candle-based strategy must read symbols from config/database and work with candle data. All strategies must return identical output format for downstream compatibility.
- Create separate TP/SL calculation modules that strategies can call - this promotes code reuse and separation of concerns across the strategy system.
- Each strategy execution must have a UUID for complete log trail traceability - trades must be reproducible later for testing and enhancement by linking back to the specific strategy execution that generated the recommendation.
- should_exit() method for spread-based strategies should: (1) return detailed exit_reason for logging in monitor/simulator, (2) allow strategy to specify data preference (live API vs cached), (3) allow strategy to define candle fetch limit parameter
- Cointegration strategy should return analysis as a dict, not a string - if it's returning a string, there's a bug in the strategy's result building logic that needs to be fixed at the source.
- Cointegration strategy: store all data needed to recalculate spread levels in strategy_metadata (beta, spread_mean, spread_std, z_score_at_entry, pair_symbol, z_exit_threshold) so levels can be recalculated at any time without needing original candle data.
- All strategies MUST implement a strict contract for trading engine compatibility - price levels must be in analysis dict, not top-level. Contract violations should be caught by tests/validation before reaching production. Need to investigate why cointegration strategy bypassed this contract.

# UI/UX
- User prefers simplest/fastest implementation approach: display existing data with minimal changes, use tab-based navigation for steps that update in real-time as new data arrives, plus a summary tab. Avoid over-engineering.
- Instance card metrics (Signal Quality and Last Cycle) should display data from the absolute latest cycle ever recorded for that instance across all runs, regardless of whether the instance is currently running or stopped.
- Sidebar instances menu: Main 'Instances' button links to /instances page, with non-collapsible list of individual instances below it (|-- instancename 1, |-- instancename 2, etc) that link to /instances/[id] detail pages.
- Performance stats should have 2 sections: (1) Aggregate boxes showing values across all runs for an instance (optimized DB calls), (2) Filtered section respecting scope filters. Rename 'This Instance' to 'Latest Run' and 'This Cycle' to 'Latest Cycle'. Trader perspective: aggregate shows overall instance health, filtered section shows specific performance context.
- Merge redundant components into single consolidated components rather than maintaining separate related components - consolidate Bot Statistics into Performance Stats to avoid duplication and maintain single source of truth.
- UI preference: Display ALL raw log data without summarization or extraction, but improve readability through better formatting, visual hierarchy, and cleaner presentation.

# Simulator
- Simulator feature: Add max_open_bars_before_filled and max_open_bars_after_filled settings. Value of 0 means no auto-cancellation. Trades auto-cancel if they exceed the bar limit for their state (pending or filled).
- Fixed "Invalid time value" error in app/api/bot/simulator/auto-close/route.ts by adding normalizeTimestamp() helper function that safely converts ISO strings, Date objects, and numbers to milliseconds, with proper null/NaN validation before any new Date() constructor calls.

# Stop Loss Adjustment
- Stop loss adjustment mechanism: After recommendation generation, allow swappable adjustment layer to modify stop_loss by set % for longs/shorts separately. Must record adjustments in database for log training and trade reproducibility.
- User's strategy has consistently tight stop loss and needs a simple way to adjust stop loss price after recommendation generation - prefers simplest/fastest implementation approach.

# Risk Management
- When Kelly Criterion is disabled or invalid, always use the configured risk_percentage from TradingConfig, never hardcode fallback values - respect the user's configured risk settings.
- min_position_value_usd setting enforces a minimum position size (position should not be smaller than this value); a value of 0 is considered turned off/disabled.
- Position sizer should already calculate and store risk_amount_usd and position_size_usd to database during trade creation - verify what position sizer currently stores before adding new metrics.
- I NEVER USE ANY DEFUALT VALUES!!!

# Debugging
- When investigating issues, verify actual code and database state first - never assume; investigate the real root cause through code inspection and data verification before making fixes.
- When investigating issues: verify each piece of data is correct in isolation first, check for timezone issues systematically, explore all possible root causes through actual verification rather than guessing - only check, don't assume.

# Live Trading
- Live trading confirmation prompt is in Python backend (likely run_bot.py or trading engine), not in InstanceHeader.tsx - need to remove the input() call that waits for 'CONFIRM' in the Python code to allow bot to start automatically in live mode.
- When live trading warnings appear, don't wait for user confirmation - proceed automatically without blocking on confirmation prompts.

# Testing
- NEVER create documentation files unless explicitly requested.
- ALWAYS run actual tests to validate code changes - never assume anything works without verification.
- For cointegration strategy tests, display spread-based execution logic (entry/SL/TP levels in spread space) directly in the test output table alongside asset prices, not separately.
- User prefers contract/specification-based testing: validate each method returns expected values for known inputs. No coding yet - focus on understanding the most efficient testing approach before implementation. Already has strategy implementation tests.

# Trade Traceability
- Complete trade traceability system: Every trade is fully traceable from analysis through closure with strategy_uuid linking all phases (recommendations→trades→executions→position_monitor_logs→error_logs). Each trade stores: strategy_uuid, strategy_type, strategy_name, strategy_config, all settings, all actions, all errors, complete timestamps. Enables full reproducibility and testing.
- Complete traceability system: (1) Input snapshot - raw_prompt + market_data already stored in raw_response JSON; (2) Intermediate calculations - stored as raw_response from model; (3) Decision context - MISSING: setup_quality, market_environment in recommendations; ranking_score, ranking_position, total_signals_analyzed, total_signals_ranked, available_slots in trades; (4) Execution context - MISSING: wallet_balance_at_trade, kelly_fraction_used, kelly_metrics in trades; (5) Monitoring context - MISSING: new trade_monitoring_log table for all adjustments/exit_checks with action_type, original_value, adjusted_value, reason, monitoring_metadata, exit_condition_result. Store efficiently as JSON columns, use centralized DB layer with proper connection release.