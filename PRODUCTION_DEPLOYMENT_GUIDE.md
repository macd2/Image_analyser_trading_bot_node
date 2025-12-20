# Production Deployment Guide

## Pre-Deployment Checklist

### 1. Code Quality
```bash
# Run all tests
pytest python/tests/ -v
pytest python/trading_bot/strategies/tests/ -v
pytest python/trading_bot/engine/tests/ -v

# Check for type errors
mypy python/trading_bot/ --ignore-missing-imports

# Check code style
flake8 python/trading_bot/ --max-line-length=120
```

### 2. Database Setup
```bash
# Initialize database
python python/trading_bot/db/init_trading_db.py

# Run migrations (PostgreSQL)
supabase migration up

# Verify tables exist
python -c "from trading_bot.db.client import get_connection; conn = get_connection(); print('✓ Database connected')"
```

### 3. Configuration Verification
```bash
# Check env vars
echo "DATABASE_URL: $DATABASE_URL"
echo "BYBIT_API_KEY: ${BYBIT_API_KEY:0:10}..."
echo "OPENAI_API_KEY: ${OPENAI_API_KEY:0:10}..."

# Verify instance exists
python -c "
from trading_bot.db.client import get_connection, query_one
conn = get_connection()
instance = query_one(conn, 'SELECT * FROM instances WHERE id = ?', ('your_instance_id',))
print(f'✓ Instance found: {instance}')
"
```

### 4. Strategy Validation
```bash
# Test strategy loading
python -c "
from trading_bot.strategies.factory import StrategyFactory
from trading_bot.config.settings_v2 import Config

config = Config.load()
strategy = StrategyFactory.create_strategy(
    'CointegrationSpreadTrader',
    config=config,
    instance_id='your_instance_id'
)
print(f'✓ Strategy loaded: {strategy.STRATEGY_NAME}')
"
```

---

## Deployment Steps

### Step 1: Deploy Code
```bash
# Pull latest code
git pull origin main

# Install dependencies
pip install -r requirements.txt

# Verify imports
python -c "import trading_bot; print('✓ Imports OK')"
```

### Step 2: Start Bot
```bash
# Paper trading (safe)
python python/run_bot.py --instance your_instance_id

# Testnet (safer than live)
python python/run_bot.py --instance your_instance_id --testnet

# Live trading (PRODUCTION)
python python/run_bot.py --instance your_instance_id --live
```

### Step 3: Monitor Logs
```bash
# Watch logs in real-time
tail -f logs/trading_bot.log

# Check for errors
grep ERROR logs/trading_bot.log

# Check cycle progress
grep "CYCLE #" logs/trading_bot.log
```

### Step 4: Verify Execution
```bash
# Check database for trades
python -c "
from trading_bot.db.client import get_connection, query
conn = get_connection()
trades = query(conn, 'SELECT * FROM trades ORDER BY created_at DESC LIMIT 5')
for trade in trades:
    print(f'{trade[\"symbol\"]}: {trade[\"status\"]}')
"
```

---

## Production Monitoring

### Key Metrics to Monitor
1. **Cycle Execution**: Check logs for "CYCLE #" every timeframe
2. **Signal Generation**: Verify recommendations in database
3. **Trade Execution**: Monitor trades table for new entries
4. **Position Monitoring**: Check position_monitor_logs for updates
5. **Error Rate**: Monitor error_logs table

### Alert Conditions
- No cycle executed in 2x timeframe
- Error rate > 5% of cycles
- Database connection failures
- API rate limit errors
- WebSocket disconnections

### Health Check Script
```bash
#!/bin/bash
# Check if bot is running
ps aux | grep "run_bot.py" | grep -v grep

# Check latest cycle
sqlite3 trading.db "SELECT created_at FROM runs ORDER BY created_at DESC LIMIT 1"

# Check error count
sqlite3 trading.db "SELECT COUNT(*) FROM error_logs WHERE created_at > datetime('now', '-1 hour')"
```

---

## Rollback Plan

If issues occur:

### 1. Stop Bot
```bash
# Kill process
pkill -f "run_bot.py"

# Verify stopped
ps aux | grep run_bot.py
```

### 2. Check Logs
```bash
# Find error
tail -100 logs/trading_bot.log | grep ERROR

# Check database
sqlite3 trading.db "SELECT * FROM error_logs ORDER BY created_at DESC LIMIT 5"
```

### 3. Rollback Code
```bash
# Revert to previous version
git revert HEAD

# Or checkout specific commit
git checkout <commit_hash>
```

### 4. Restart
```bash
python python/run_bot.py --instance your_instance_id
```

---

## Performance Optimization

### Database
- Index frequently queried columns
- Archive old trades (> 6 months)
- Vacuum database regularly

### API Calls
- Cache candle data locally
- Batch API requests
- Implement rate limiting

### Memory
- Monitor memory usage
- Clear old logs
- Limit WebSocket buffer size

---

## Security Checklist

- [ ] No API keys in code
- [ ] All secrets in env vars
- [ ] Database password strong
- [ ] HTTPS for all API calls
- [ ] Row-level security enabled
- [ ] Audit logs enabled
- [ ] Regular backups scheduled
- [ ] Access logs monitored


