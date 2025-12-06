# V2 Configuration Guide

## Environment Variables

Create a `.env.local` file in the root directory to configure paths and settings.

### Database Paths

```bash
# V2 Dashboard Database (SQLite)
DATABASE_PATH=./data/backtests.db
ANALYSIS_DATABASE_PATH=./data/analysis_results.db
```

### Python Backtest Configuration

```bash
# Chart Images Directory (relative to V2 root)
PYTHON_CHARTS_PATH=../../../trading_bot/data/charts/.backup

# Python Database Path (for backtest results)
PYTHON_DATABASE_PATH=../../../trading_bot/data/analysis_results.db

# Python Config File
PYTHON_CONFIG_PATH=./python/config.yaml
```

## Default Paths

If environment variables are not set, the following defaults are used:

| Variable | Default |
|----------|---------|
| `DATABASE_PATH` | `./data/backtests.db` |
| `ANALYSIS_DATABASE_PATH` | `./data/analysis_results.db` |
| `PYTHON_CHARTS_PATH` | `../../../trading_bot/data/charts/.backup` |
| `PYTHON_DATABASE_PATH` | `../../../trading_bot/data/analysis_results.db` |

## Using Existing Data

To use existing chart images and database from the Python bot:

1. **Keep default paths** - V2 will automatically use the Python bot's data
2. **Or copy data to V2** - Copy charts and database to V2's data folder and update paths:

```bash
# Copy charts
cp -r trading_bot/data/charts/.backup NextJsAppBot/V2/prototype/data/charts

# Copy database
cp trading_bot/data/analysis_results.db NextJsAppBot/V2/prototype/data/

# Update .env.local
PYTHON_CHARTS_PATH=./data/charts
PYTHON_DATABASE_PATH=./data/analysis_results.db
```

## Railway Deployment

For Railway deployment, set environment variables in the Railway dashboard:

```bash
PYTHON_CHARTS_PATH=/app/data/charts
PYTHON_DATABASE_PATH=/app/data/analysis_results.db
```

Then mount a persistent volume at `/app/data` to preserve data across deployments.

## API Keys (Optional)

If using live features (not required for backtesting):

```bash
OPENAI_API_KEY=sk-...
BYBIT_API_KEY=...
BYBIT_API_SECRET=...
```

## Verification

To verify your configuration is working:

1. Start the dev server: `pnpm dev`
2. Navigate to Learning → Run Backtest
3. Check the logs for the resolved paths
4. If images are not found, verify `PYTHON_CHARTS_PATH` points to a directory with chart images

