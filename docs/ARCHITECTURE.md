# Prototype Architecture

## Component Hierarchy

```
app/page.tsx (Main Page)
├── Sidebar
│   └── Navigation tabs (Dashboard, Positions, Trades)
└── Main Content (conditional rendering)
    ├── Dashboard (when activeTab === 'dashboard')
    │   ├── StatCard (x4)
    │   ├── PositionsTable
    │   └── RecentTrades
    ├── PositionsView (when activeTab === 'positions')
    │   ├── StatCard (x4)
    │   └── PositionsTable
    └── TradesView (when activeTab === 'trades')
        ├── StatCard (x4)
        └── Trades Table
```

## Data Flow

```
Mock Data (hardcoded in components)
    ↓
Components render with mock data
    ↓
User clicks tab in Sidebar
    ↓
activeTab state changes
    ↓
Conditional rendering shows new view
```

## File Organization

### App Layer (`app/`)
- `layout.tsx` - Root layout with metadata
- `page.tsx` - Main page with tab state management
- `globals.css` - Global Tailwind styles

### Components Layer (`components/`)
- `Sidebar.tsx` - Navigation sidebar
- `Dashboard.tsx` - Dashboard view (main stats + tables)
- `PositionsView.tsx` - Positions page
- `TradesView.tsx` - Trades history page
- `PositionsTable.tsx` - Reusable positions table
- `RecentTrades.tsx` - Recent trades widget
- `StatCard.tsx` - Reusable stat card

### Config Layer
- `package.json` - Dependencies
- `tsconfig.json` - TypeScript config
- `tailwind.config.js` - Tailwind theme
- `postcss.config.js` - PostCSS plugins
- `next.config.js` - Next.js config

## State Management

Currently using React `useState` for tab navigation:

```typescript
const [activeTab, setActiveTab] = useState('dashboard')
```

**Future**: Replace with React Query for API data fetching.

## Styling Strategy

### Tailwind Classes
- `card` - Reusable card component
- `badge-long` - Long position badge
- `badge-short` - Short position badge
- `badge-hold` - Hold position badge
- `text-positive` - Green text for profits
- `text-negative` - Red text for losses

### Color Scheme
- Background: `slate-950` (dark)
- Cards: `slate-800` with `slate-700` borders
- Text: `slate-100` (light)
- Accents: Green (`#10b981`) and Red (`#ef4444`)

## Mock Data Structure

### Position Object
```typescript
{
  id: number
  symbol: string
  side: 'LONG' | 'SHORT'
  entry: number
  current: number
  quantity: number
  pnl: number
  pnlPercent: number
  confidence: number
}
```

### Trade Object
```typescript
{
  id: number
  symbol: string
  side: 'LONG' | 'SHORT'
  entry: number
  exit: number
  pnl: number
  date: string
}
```

## Responsive Design

- **Mobile**: Single column layout
- **Tablet**: 2-column grid
- **Desktop**: 3-4 column grid

Uses Tailwind's responsive prefixes:
- `md:` - Medium screens (768px+)
- `lg:` - Large screens (1024px+)

## Performance Optimizations

- ✅ Server-side rendering (Next.js default)
- ✅ Minimal dependencies
- ✅ CSS-in-JS with Tailwind (no runtime overhead)
- ✅ Component code splitting (automatic with Next.js)

## Ready for Backend Integration

Replace mock data with API calls:

```typescript
// Before (mock)
const mockPositions = [...]

// After (API)
const { data: positions } = useQuery({
  queryKey: ['positions'],
  queryFn: () => fetch('/api/positions').then(r => r.json())
})
```

See `../TECH_STACK.md` for full integration guide.

