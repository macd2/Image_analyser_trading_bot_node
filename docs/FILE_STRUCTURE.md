# Prototype File Structure

```
prototype/
│
├── 📄 Configuration Files
│   ├── package.json              # Dependencies & scripts
│   ├── tsconfig.json             # TypeScript config
│   ├── next.config.js            # Next.js config
│   ├── tailwind.config.js        # Tailwind theme
│   ├── postcss.config.js         # PostCSS plugins
│   └── .gitignore                # Git ignore rules
│
├── 📚 Documentation
│   ├── README.md                 # Full documentation
│   ├── QUICKSTART.md             # Quick start guide
│   ├── ARCHITECTURE.md           # Component hierarchy
│   └── FILE_STRUCTURE.md         # This file
│
├── 📁 app/ (Next.js App Router)
│   ├── layout.tsx                # Root layout
│   ├── page.tsx                  # Main page (tab navigation)
│   └── globals.css               # Global Tailwind styles
│
└── 📁 components/ (React Components)
    ├── Sidebar.tsx               # Navigation sidebar
    ├── Dashboard.tsx             # Dashboard view
    ├── PositionsView.tsx         # Positions page
    ├── TradesView.tsx            # Trades history page
    ├── PositionsTable.tsx        # Reusable positions table
    ├── RecentTrades.tsx          # Recent trades widget
    └── StatCard.tsx              # Reusable stat card
```

## File Descriptions

### Configuration Files

| File | Purpose |
|------|---------|
| `package.json` | npm dependencies and scripts |
| `tsconfig.json` | TypeScript compiler options |
| `next.config.js` | Next.js configuration |
| `tailwind.config.js` | Tailwind CSS theme customization |
| `postcss.config.js` | PostCSS plugin configuration |
| `.gitignore` | Git ignore patterns |

### App Layer (`app/`)

| File | Purpose | Lines |
|------|---------|-------|
| `layout.tsx` | Root layout with metadata | ~20 |
| `page.tsx` | Main page with tab state | ~25 |
| `globals.css` | Global Tailwind styles | ~40 |

### Components Layer (`components/`)

| File | Purpose | Lines |
|------|---------|-------|
| `Sidebar.tsx` | Navigation sidebar | ~45 |
| `Dashboard.tsx` | Dashboard view | ~50 |
| `PositionsView.tsx` | Positions page | ~40 |
| `TradesView.tsx` | Trades history page | ~60 |
| `PositionsTable.tsx` | Positions table | ~50 |
| `RecentTrades.tsx` | Recent trades widget | ~35 |
| `StatCard.tsx` | Stat card component | ~25 |

## Total Lines of Code

- **Configuration**: ~50 lines
- **App Layer**: ~85 lines
- **Components**: ~305 lines
- **Documentation**: ~400 lines
- **Total**: ~840 lines

## Component Dependencies

```
page.tsx
├── Sidebar
│   └── (navigation state)
├── Dashboard
│   ├── StatCard (x4)
│   ├── PositionsTable
│   └── RecentTrades
├── PositionsView
│   ├── StatCard (x4)
│   └── PositionsTable
└── TradesView
    ├── StatCard (x4)
    └── (inline trades table)
```

## Data Flow

```
Mock Data (hardcoded)
    ↓
Components render
    ↓
User interaction (click tab)
    ↓
State update (activeTab)
    ↓
Conditional rendering
    ↓
New view displayed
```

## Styling Layers

1. **Global** (`globals.css`) - Base styles, custom classes
2. **Tailwind** (`tailwind.config.js`) - Theme colors, spacing
3. **Component** (inline `className`) - Component-specific styles

## Ready to Extend

- ✅ Add more views (Settings, Analytics, etc.)
- ✅ Add charts (Recharts already in dependencies)
- ✅ Add forms (React Hook Form ready)
- ✅ Add API integration (React Query ready)
- ✅ Add real-time updates (socket.io ready)

