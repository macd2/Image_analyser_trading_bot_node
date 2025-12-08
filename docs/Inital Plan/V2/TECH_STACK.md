# Tech Stack Decisions

## Guiding Principles

1. **Fewer dependencies = fewer problems**
2. **Proven over trendy**
3. **Developer experience matters**
4. **Always-on for trading** (no cold starts!)

---

## Final Stack (Railway Optimized)

| Layer | Choice | Why |
|-------|--------|-----|
| **Hosting** | Railway ($5/mo) | No cold starts, PostgreSQL included, simple |
| **Framework** | Next.js 14 (App Router) | SSR, API routes, one codebase |
| **Language** | TypeScript (strict) | Type safety prevents bugs |
| **UI Library** | shadcn/ui | Accessible, customizable, copy-paste |
| **Styling** | Tailwind CSS | Fast, consistent, works with shadcn |
| **Database** | PostgreSQL (Railway) | Reliable, JSONB, always available |
| **ORM** | Drizzle | Type-safe, lightweight, fast |
| **Background Jobs** | node-cron | Simple, in-process, no external service |
| **Real-time** | socket.io | WebSockets, proven, works everywhere |
| **Charts** | Lightweight Charts | TradingView's library, performant |
| **State** | React Query (TanStack) | Caching, refetching, optimistic updates |
| **Forms** | React Hook Form + Zod | Validation, performance |
| **Auth** | NextAuth.js (optional) | Simple, JWT, multiple providers |

---

## Why These Choices

### Why Railway for Trading Bots
- **No cold starts**: Critical for trade execution
- **Always running**: Background jobs work naturally
- **PostgreSQL included**: One platform, one bill
- **Simple**: `railway up` and done
- **Affordable**: $5/month is nothing for a trading bot

### Next.js 14 (App Router)
- **Server Components**: Less JavaScript shipped to client
- **API Routes**: No separate backend needed
- **Streaming**: Progressive loading for dashboards

### Drizzle over Prisma
- **Lighter**: ~10x smaller bundle
- **Faster**: Direct SQL, no query engine
- **Type-safe**: Full TypeScript inference
- **SQL-like**: Easier to understand queries

### node-cron over Inngest/BullMQ
- **In-process**: No external service needed
- **Simple**: Just schedule functions
- **Railway-friendly**: Works great with always-on hosting
- **No Redis**: One less thing to manage

---

## Package.json (Minimal)

```json
{
  "name": "trading-bot",
  "version": "0.1.0",
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "db:push": "drizzle-kit push",
    "db:studio": "drizzle-kit studio"
  },
  "dependencies": {
    "next": "^14.2.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",

    "drizzle-orm": "^0.30.0",
    "postgres": "^3.4.0",

    "@tanstack/react-query": "^5.32.0",
    "react-hook-form": "^7.51.0",
    "zod": "^3.23.0",
    "@hookform/resolvers": "^3.3.0",

    "node-cron": "^3.0.0",
    "socket.io": "^4.7.0",
    "openai": "^4.47.0",

    "lightweight-charts": "^4.1.0",
    "lucide-react": "^0.372.0",
    "date-fns": "^3.6.0",

    "class-variance-authority": "^0.7.0",
    "clsx": "^2.1.0",
    "tailwind-merge": "^2.3.0"
  },
  "devDependencies": {
    "typescript": "^5.4.0",
    "@types/node": "^20.12.0",
    "@types/react": "^18.3.0",
    "@types/node-cron": "^3.0.0",
    "drizzle-kit": "^0.20.0",
    "tailwindcss": "^3.4.0",
    "postcss": "^8.4.0",
    "autoprefixer": "^10.4.0"
  }
}
```

**Total: ~14 production dependencies** (vs 50+ in typical projects)

---

## Environment Variables

```bash
# Railway auto-injects DATABASE_URL
# Set these via: railway variables set KEY=value

# Database (auto-injected by Railway PostgreSQL plugin)
DATABASE_URL="postgresql://..."

# Bybit
BYBIT_API_KEY="..."
BYBIT_API_SECRET="..."
BYBIT_TESTNET="true"  # Start with testnet!

# OpenAI
OPENAI_API_KEY="sk-..."

# Optional: Telegram
TELEGRAM_BOT_TOKEN="..."
TELEGRAM_CHAT_ID="..."

# App
NODE_ENV="production"
```

---

## Deployment (Railway)

```bash
# One-time setup
npm i -g @railway/cli
railway login
railway init
railway add --plugin postgresql

# Set env vars
railway variables set BYBIT_API_KEY=xxx
railway variables set BYBIT_API_SECRET=xxx
railway variables set OPENAI_API_KEY=xxx
railway variables set BYBIT_TESTNET=true

# Deploy
railway up

# Open dashboard
railway open
```

**That's it.** No Vercel, no Supabase, no Inngest. One platform.

---

## Project Structure

```
trading-bot/
├── app/
│   ├── (dashboard)/          # Dashboard routes
│   │   ├── page.tsx
│   │   ├── positions/
│   │   ├── trades/
│   │   └── layout.tsx
│   ├── api/
│   │   ├── trades/route.ts
│   │   ├── positions/route.ts
│   │   ├── analyze/route.ts
│   │   └── socket/route.ts   # WebSocket endpoint
│   ├── layout.tsx
│   └── globals.css
├── components/
│   ├── ui/                   # shadcn components
│   └── trading/              # Trading components
├── lib/
│   ├── db/
│   │   ├── index.ts          # Drizzle client
│   │   └── schema.ts         # Schema definitions
│   ├── services/
│   │   ├── bybit.ts
│   │   ├── chart-analyzer.ts
│   │   ├── risk-manager.ts
│   │   ├── trading-engine.ts
│   │   └── scheduler.ts      # node-cron jobs
│   ├── websocket/
│   │   └── server.ts         # socket.io setup
│   └── utils/
│       └── index.ts
├── hooks/
│   ├── use-positions.ts
│   └── use-trades.ts
├── drizzle/
│   └── migrations/
├── drizzle.config.ts
├── tailwind.config.ts
├── tsconfig.json
└── package.json
```

---

## Best Practices

### 1. Type Everything
```typescript
// types/index.ts
export interface Trade {
  id: string;
  symbol: string;
  side: 'LONG' | 'SHORT';
  // ... all fields typed
}

// Use Drizzle's inferred types
import { trades } from '@/lib/db/schema';
type Trade = typeof trades.$inferSelect;
```

### 2. Error Boundaries
```tsx
// app/error.tsx
'use client';

export default function Error({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center h-screen">
      <h2>Something went wrong</h2>
      <button onClick={reset}>Try again</button>
    </div>
  );
}
```

### 3. Loading States
```tsx
// app/(dashboard)/loading.tsx
import { Skeleton } from '@/components/ui/skeleton';

export default function Loading() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-32 w-full" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}
```

### 4. Validate All Inputs
```typescript
import { z } from 'zod';

const TradeSignalSchema = z.object({
  symbol: z.string().min(1),
  side: z.enum(['LONG', 'SHORT']),
  confidence: z.number().min(0).max(1),
  entryPrice: z.number().positive(),
  stopLoss: z.number().positive(),
  takeProfit: z.number().positive(),
});

// In API route
const signal = TradeSignalSchema.parse(await req.json());
```

---

## Performance Tips

1. **Use Server Components** by default, Client Components only when needed
2. **Prefetch data** with `<Link prefetch>` and React Query
3. **Optimize images** with `next/image`
4. **Cache API responses** with React Query's staleTime
5. **Use database indexes** on frequently queried columns

