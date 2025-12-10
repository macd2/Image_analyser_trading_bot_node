
# General 
[ ] run production audit in terms of security, efficency and robustness (minal changes )

----

# Improvments 
[ ] make sure all chart modals have the signal and entry marker
[ ] explain waht exaclty is the dirrenferece between the marker in trades for status papertrade and dry-run 
[ ] is the the value from confidence calculation from analysis actually used in the bot for trading deccisions?

----

**Bug / Enhancement Requests for Simulator & UI:**

1. **Simulator/Backend Sync Issue**  
   - Either the simulator is not running in the background, *or* the UI fails to refresh upon page load.  
   - Evidence: Data shown for the “last check” was stale — timestamp indicates 2 hours ago.

2. **UI Consistency — Fill Time Handling**  
   - The UI must respect the actual *fill time* of a trade.  
   - Current issue: A trade card shows “TP Hit” even though the trade is still *pending fill*. This is misleading and must be corrected.

3. **Simulator Settings: Max Open Bars & Cancellation Logic**  
   - Add a new simulator setting: **Max Open Bars**  
     - Definition: Maximum number of bars a a trade may remain open before being automatically *cancelled*.  
     - Requirement: Ensure internal tracking of elapsed bars per open trade and chec kwhich statuse we have per trade cancled must be one of them.  
   - Introduce a new UI section: **Cancelled Trades**  
     - Layout: Same card format as *Closed Trades*, but exclusively for trades cancelled due to timeout (e.g., max bars exceeded).  
     - Separation: These must *not* be grouped with closed (i.e., filled or manually exited) trades.
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

------
# /instance page
[ ] position tab in /instance should also show the dryrun positions 
[ ] the simulator should act a a kind of exchange for dry run trades im not sure waht the best architecture is but we want to simulate stoploss tigheting an also order replacement 
[ ] add a new card to overview tab that visually shows the current step of the cycle we are in. So getting charts, analyzing images, risk management, Order execution, waiting for next cycle (wait time)
[ ] also add a stats card  with  key information like which cycle we are on, for how long the bot was running
[ ] adjust the perfomance stats so it is by defualt per run but with a dropdown filter to change to 1 day 7 days 1 week and all time
[ ] the open position must also show dry run positions for this instance 
[ ] add the watchlist symbols from capture page somewhere fitting in the instance card

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


