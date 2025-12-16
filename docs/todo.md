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


-----------------

[Auto-Close] Trade ab8b1a36-4797-4b49-91f0-f2670e76e0cd_43a2e289 (AIOZUSDT): entry=0.114, SL=0.1168, TP=0.107, timeframe=2h, created=2025-12-16T10:07:47.540Z, candles_fetched=0
Cycle status GET error: Error: Connection terminated due to connection timeout
    at /home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/pg-pool@3.10.1_pg@8.16.3/node_modules/pg-pool/index.js:45:11
    at process.processTicksAndRejections (node:internal/process/task_queues:95:5)
    at async query (webpack://trading-bot-prototype/lib/db/client.ts?fdeb:84:20)
    at async GET (webpack://trading-bot-prototype/app/api/bot/cycle-status/route.ts?6322:47:18)
    at async <anonymous> (webpack://next/dist/esm/server/future/route-modules/app-route/module.js:195:37)
    at async eT.execute (webpack://next/dist/esm/server/future/route-modules/app-route/module.js:124:26)
    at async eT.handle (webpack://next/dist/esm/server/future/route-modules/app-route/module.js:270:30)
    at async doRender (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/next@14.2.33_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/src/server/base-server.ts:2251:30)
    at async cacheEntry.responseCache.get.routeKind (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/next@14.2.33_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/src/server/base-server.ts:2569:24)
    at async DevServer.renderToResponseWithComponentsImpl (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/next@14.2.33_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/src/server/base-server.ts:2432:24)
    at async DevServer.renderPageComponent (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/next@14.2.33_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/src/server/base-server.ts:3016:16)
    at async DevServer.renderToResponseImpl (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/next@14.2.33_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/src/server/base-server.ts:3078:24)
    at async DevServer.pipeImpl (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/next@14.2.33_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/src/server/base-server.ts:1537:21)
    at async DevServer.NextNodeServer.handleCatchallRenderRequest (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/next@14.2.33_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/src/server/next-server.ts:1020:7)
    at async DevServer.handleRequestImpl (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/next@14.2.33_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/src/server/base-server.ts:1318:9)
    at async <anonymous> (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/next@14.2.33_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/src/server/dev/next-dev-server.ts:461:14)
    at async Span.traceAsyncFn (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/next@14.2.33_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/src/trace/trace.ts:141:14)
    at async DevServer.handleRequest (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/next@14.2.33_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/src/server/dev/next-dev-server.ts:459:20)
    at async invokeRender (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/next@14.2.33_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/src/server/lib/router-server.ts:277:11)
    at async handleRequest (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/next@14.2.33_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/src/server/lib/router-server.ts:527:16)
    at async NextCustomServer.requestHandlerImpl (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/next@14.2.33_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/src/server/lib/router-server.ts:573:7)
    at async Server.<anonymous> (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/server.ts:160:7) {
  [cause]: Error: Connection terminated unexpectedly
      at Connection.<anonymous> (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/pg@8.16.3/node_modules/pg/lib/client.js:136:73)
      at Object.onceWrapper (node:events:638:28)
      at Connection.emit (node:events:524:28)
      at Socket.<anonymous> (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/pg@8.16.3/node_modules/pg/lib/connection.js:62:12)
      at Socket.emit (node:events:524:28)
      at TCP.<anonymous> (node:net:343:12)
      at TCP.callbackTrampoline (node:internal/async_hooks:130:17)
}
 GET /api/bot/cycle-status?instance_id=a3e1afd3-1b04-4aac-90bf-ccccd52dcfba 500 in 10122ms
[Middleware] DASHBOARD_PASSWORD not set - dashboard is unprotected!
[TradingDB] Connection error (undefined): Connection terminated due to connection timeout, retrying... (1/3)
[TradingDB] Connection error (undefined): Connection terminated due to connection timeout, retrying... (1/3)
 GET /api/bot/control?instance_id=a3e1afd3-1b04-4aac-90bf-ccccd52dcfba 200 in 29ms
[TradingDB] Connection error (undefined): Connection terminated due to connection timeout, retrying... (1/3)
[TradingDB] Connection error (undefined): Connection terminated due to connection timeout, retrying... (1/3)
[TradingDB] Query failed after 3 retries: Cannot use a pool after calling end on the pool
 GET /api/bot/trades?limit=20&instance_id=a3e1afd3-1b04-4aac-90bf-ccccd52dcfba 503 in 10219ms
[TradingDB] Query failed after 3 retries: Cannot use a pool after calling end on the pool
[Status API] Error: Error: Cannot use a pool after calling end on the pool
    at /home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/pg-pool@3.10.1_pg@8.16.3/node_modules/pg-pool/index.js:45:11
    at async pgQueryWithRetry (webpack://trading-bot-prototype/lib/db/trading-db.ts?7536:122:35)
    at async dbQuery (webpack://trading-bot-prototype/lib/db/trading-db.ts?7536:205:18)
    at async dbQueryOne (webpack://trading-bot-prototype/lib/db/trading-db.ts?7536:215:19)
    at async GET (webpack://trading-bot-prototype/app/api/bot/status/route.ts?bc64:53:22)
    at async <anonymous> (webpack://next/dist/esm/server/future/route-modules/app-route/module.js:195:37)
    at async eT.execute (webpack://next/dist/esm/server/future/route-modules/app-route/module.js:124:26)
    at async eT.handle (webpack://next/dist/esm/server/future/route-modules/app-route/module.js:270:30)
    at async doRender (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/next@14.2.33_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/src/server/base-server.ts:2251:30)
    at async cacheEntry.responseCache.get.routeKind (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/next@14.2.33_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/src/server/base-server.ts:2569:24)
    at async DevServer.renderToResponseWithComponentsImpl (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/next@14.2.33_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/src/server/base-server.ts:2432:24)
    at async DevServer.renderPageComponent (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/next@14.2.33_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/src/server/base-server.ts:3016:16)
    at async DevServer.renderToResponseImpl (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/next@14.2.33_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/src/server/base-server.ts:3078:24)
    at async DevServer.pipeImpl (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/next@14.2.33_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/src/server/base-server.ts:1537:21)
    at async DevServer.NextNodeServer.handleCatchallRenderRequest (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/next@14.2.33_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/src/server/next-server.ts:1020:7)
    at async DevServer.handleRequestImpl (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/next@14.2.33_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/src/server/base-server.ts:1318:9)
    at async <anonymous> (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/next@14.2.33_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/src/server/dev/next-dev-server.ts:461:14)
    at async Span.traceAsyncFn (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/next@14.2.33_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/src/trace/trace.ts:141:14)
    at async DevServer.handleRequest (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/next@14.2.33_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/src/server/dev/next-dev-server.ts:459:20)
    at async invokeRender (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/next@14.2.33_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/src/server/lib/router-server.ts:277:11)
    at async handleRequest (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/next@14.2.33_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/src/server/lib/router-server.ts:527:16)
    at async NextCustomServer.requestHandlerImpl (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/node_modules/.pnpm/next@14.2.33_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/src/server/lib/router-server.ts:573:7)
    at async Server.<anonymous> (/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/server.ts:160:7)
 GET /api/bot/status?instance_id=a3e1afd3-1b04-4aac-90bf-ccccd52dcfba 500 in 10239ms
[TradingDB] Query failed after 3 retries: Cannot use a pool after calling end on the pool
[Pause State API] Error: Cannot use a pool after calling end on the pool
 GET /api/bot/pause-state?instance_id=a3e1afd3-1b04-4aac-90bf-ccccd52dcfba 500 in 10140ms
[TradingDB] Query failed after 3 retries: Cannot use a pool after calling end on the pool
 GET /api/bot/instances 503 in 10139ms
Failed to get current price for AIOZUSD