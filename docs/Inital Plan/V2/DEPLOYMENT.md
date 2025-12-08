# Railway Deployment Guide

## Why Railway?

For a **trading bot**, Railway is the clear winner:

| Feature | Railway | Vercel (Free) |
|---------|---------|---------------|
| Cold starts | ❌ None | ⚠️ 10+ seconds |
| Always running | ✅ Yes | ❌ Serverless |
| PostgreSQL | ✅ Included | ❌ Separate service |
| Background jobs | ✅ Native | ❌ Need Inngest |
| Cost | $5/mo | Free (limited) |

**For trading execution speed, cold starts are unacceptable.**

---

## Quick Start (5 minutes)

```bash
# 1. Install Railway CLI
npm install -g @railway/cli

# 2. Login
railway login

# 3. Initialize project (in your Next.js folder)
cd trading-bot
railway init

# 4. Add PostgreSQL database
railway add --plugin postgresql

# 5. Set environment variables
railway variables set BYBIT_API_KEY=your_key_here
railway variables set BYBIT_API_SECRET=your_secret_here
railway variables set OPENAI_API_KEY=sk-your_key_here
railway variables set BYBIT_TESTNET=true
railway variables set NODE_ENV=production

# 6. Deploy
railway up

# 7. Open your app
railway open
```

**That's it!** Your trading bot is now live.

---

## Project Configuration

### railway.json
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "pnpm start",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

### next.config.js
```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone', // Optimized for Railway
}

module.exports = nextConfig
```

### package.json scripts
```json
{
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "db:push": "drizzle-kit push",
    "db:studio": "drizzle-kit studio"
  }
}
```

---

## Environment Variables

Railway auto-injects `DATABASE_URL` when you add PostgreSQL plugin.

### Required
```bash
# Auto-injected by Railway
DATABASE_URL=postgresql://...

# Set manually
BYBIT_API_KEY=xxx
BYBIT_API_SECRET=xxx
OPENAI_API_KEY=sk-xxx
BYBIT_TESTNET=true  # Start with testnet!
```

### Optional
```bash
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx
```

### Setting Variables
```bash
# Via CLI
railway variables set KEY=value

# Or use Railway dashboard
railway open
# → Variables tab
```

---

## Database Setup

### 1. Add PostgreSQL Plugin
```bash
railway add --plugin postgresql
```

### 2. Run Migrations
```bash
# Connect to Railway's DB locally
railway run pnpm db:push
```

### 3. Verify Connection
```bash
railway run npx drizzle-kit studio
```

---

## Monitoring

### Logs
```bash
# Stream logs
railway logs

# Or in dashboard
railway open
# → Deployments → View Logs
```

### Metrics
Railway dashboard shows:
- CPU usage
- Memory usage
- Network traffic
- Request count

---

## Custom Domain

```bash
# Add custom domain
railway domain

# Or in dashboard:
# Settings → Domains → Add Custom Domain
```

---

## Costs

| Resource | Included | Overage |
|----------|----------|---------|
| Compute | $5 credit/mo | $0.000231/min |
| Memory | 512MB | $0.000231/GB/min |
| PostgreSQL | 1GB storage | $0.25/GB/mo |

**Typical trading bot**: ~$5-10/month

---

## Troubleshooting

### Build Fails
```bash
# Check build logs
railway logs --build

# Common fixes:
# - Ensure pnpm-lock.yaml is committed
# - Check Node version in package.json
```

### Database Connection Issues
```bash
# Verify DATABASE_URL is set
railway variables

# Test connection
railway run node -e "console.log(process.env.DATABASE_URL)"
```

### App Crashes on Start
```bash
# Check runtime logs
railway logs

# Common issues:
# - Missing env variables
# - Port binding (Railway auto-sets PORT)
```

---

## CI/CD (Optional)

### GitHub Integration
1. Connect repo in Railway dashboard
2. Auto-deploys on push to main

### Manual Deploy
```bash
railway up
```

---

## Environment Variables Checklist

```bash
# Required
DATABASE_URL=postgresql://...
BYBIT_API_KEY=...
BYBIT_API_SECRET=...
OPENAI_API_KEY=...

# Optional
BYBIT_TESTNET=true           # Start with testnet!
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
INNGEST_EVENT_KEY=...
INNGEST_SIGNING_KEY=...

# Next.js
NEXT_PUBLIC_APP_URL=https://your-domain.up.railway.app
```

---

## Post-Deployment Checklist

- [ ] Verify database connection
- [ ] Test Bybit API connectivity (testnet first!)
- [ ] Confirm OpenAI API working
- [ ] Run migration script
- [ ] Verify dashboard loads
- [ ] Test manual trade execution
- [ ] Set up monitoring/alerts
- [ ] Switch to mainnet when ready

