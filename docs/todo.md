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
[ ] make sure all chart modals have the signal and entry marker
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

------
# /instance page
[ ] position tab in /instance should also show the dryrun positions 
[ ] the simulator should act a a kind of exchange for dry run trades im not sure waht the best architecture is but we want to simulate stoploss tigheting an also order replacement 
[ ] add a new card to overview tab that visually shows the current step of the cycle we are in. So getting charts, analyzing images, risk management, Order execution, waiting for next cycle (wait time)
[ ] also add a stats card  with  key information like which cycle we are on, for how long the bot was running

[ ] the open position must also show dry run positions for this instance 


-----
# overview 
## insance page
[ ] Trading Cycle Status this should be based on the current run 
e the
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

[ErrorLogger] Failed to log error: connection pool exhausted
2025-12-11 03:40:32 | ERROR | trading_bot.core.slot_manager | Error querying database for pending orders count: connection pool exhausted
[ErrorLogger] Failed to log error: connection pool exhausted
2025-12-11 03:40:32 | ERROR | trading_bot.core.state_manager | Error querying database for open positions: connection pool exhausted


------
[ ] each part of the trading cycle must be instance aware
[ ] each step of the trading cycle must check its own data iteegrety 
[ ] each part of the trading cylce must be timeframe and boundery aware
- example sources must check if there already images for the current timeframe and boundery
- cleaner must only clean images that are outside the crrent boundery based on tieframe 
[ ] analyzer must only analze images if there is no recomendation for current timeframe and boundery and instance than return results as if it analyzed them but with the note of chached results so later parts of the code can run 
[ ] execution must check in dry run of the given recomendation was already executed based on database status in live trading ofcause based on exchnage data
[ ] we need to define a set of error that pause the bot permantly until manually resumed
