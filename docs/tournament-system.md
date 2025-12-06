# Tournament System - Find Best Prompt

## Purpose

The Tournament System efficiently identifies the best-performing trading prompt by using elimination-style rounds. Instead of exhaustively testing all prompts on all images (expensive), it uses a 3-phase tournament that eliminates underperformers early.

## How It Works

### Tournament Flow

```
Phase 1: Quick Elimination
├── Test ALL prompts on same 10 images
├── Calculate: win_rate, avg_pnl, trade_count  
├── Eliminate bottom 50%
└── ~N×10 API calls

Phase 2: Deeper Testing
├── Test remaining prompts on 25 images
├── Eliminate bottom 50% again
└── ~(N/2)×25 API calls

Phase 3: Final Showdown
├── Test top 2-3 prompts on 50 images
├── Same images for fair comparison
├── Declare winner with confidence
└── ~3×50 API calls
```

### Efficiency Gains

| Approach | 10 Prompts × 50 Images | API Calls |
|----------|------------------------|-----------|
| Brute Force | All prompts × all images | 500 |
| Tournament | 3-phase elimination | ~175 |

**Savings: ~65%**

## Database Schema

### Tables

#### `tournaments`
Main table tracking each tournament run.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| name | TEXT | Tournament name |
| status | TEXT | pending/running/completed/failed/cancelled |
| model | TEXT | AI model used |
| elimination_pct | INTEGER | % eliminated per phase |
| images_phase_1/2/3 | INTEGER | Images per phase |
| image_offset | INTEGER | Skip N recent images |
| selection_strategy | TEXT | random/sequential |
| symbols_json | TEXT | Symbols tested |
| winner_prompt_name | TEXT | Final winner |
| winner_win_rate | REAL | Winner's win rate |

#### `tournament_phases`
Each phase within a tournament.

| Column | Type | Description |
|--------|------|-------------|
| tournament_id | INTEGER | FK to tournaments |
| phase_number | INTEGER | 1, 2, or 3 |
| images_per_prompt | INTEGER | Images tested |
| prompts_entering | INTEGER | Prompts at start |
| prompts_eliminated | INTEGER | Prompts removed |

#### `tournament_prompts`
Track each prompt's journey.

| Column | Type | Description |
|--------|------|-------------|
| tournament_id | INTEGER | FK to tournaments |
| prompt_name | TEXT | Prompt identifier |
| status | TEXT | active/eliminated/winner |
| eliminated_in_phase | INTEGER | Phase where eliminated |
| final_rank | INTEGER | Final position |

#### `phase_results`
Per-prompt performance in each phase.

| Column | Type | Description |
|--------|------|-------------|
| phase_id | INTEGER | FK to phases |
| tournament_prompt_id | INTEGER | FK to prompts |
| wins/losses/holds | INTEGER | Trade outcomes |
| win_rate | REAL | Win percentage |
| avg_pnl | REAL | Average P&L % |

#### `tournament_analyses`
Individual analysis results.

| Column | Type | Description |
|--------|------|-------------|
| phase_id | INTEGER | FK to phases |
| tournament_prompt_id | INTEGER | FK to prompts |
| phase_image_id | INTEGER | FK to images |
| recommendation | TEXT | BUY/SELL/HOLD |
| outcome | TEXT | WIN/LOSS/EXPIRED |
| pnl_pct | REAL | Realized P&L |

## Configuration

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| model | gpt-4o | AI model for analysis |
| elimination_pct | 50 | % eliminated per phase |
| images_phase_1 | 10 | Quick filter images |
| images_phase_2 | 25 | Medium test images |
| images_phase_3 | 50 | Final comparison |
| image_offset | 100 | Skip recent images |
| selection_strategy | random | random or sequential |

### Ranking Criteria

Prompts are ranked by (in order):
1. **Win Rate** - Primary metric
2. **Average P&L** - Tie-breaker
3. **Trade Count** - Avoid prompts that never trade

## API Endpoints

### POST /api/tournament
Start a new tournament.

```json
{
  "prompts": ["prompt_v1", "prompt_v2"],
  "symbols": ["BTCUSDT", "ETHUSDT"],
  "timeframes": ["1h"],
  "model": "gpt-4o",
  "eliminationPct": 50,
  "imagesPhase1": 10,
  "imagesPhase2": 25,
  "imagesPhase3": 50
}
```

### GET /api/tournament?tournamentId=xxx
Get tournament status and live rankings.

### DELETE /api/tournament?tournamentId=xxx
Cancel a running tournament.

## Files

```
lib/db/
├── migrations/
│   └── 001_tournament_schema.sql  # Database schema
├── migrate.ts                      # Migration runner
└── tournament.ts                   # DB operations

python/prompt_performance/
└── tournament.py                   # Tournament engine

components/learning/
└── FindBestPromptPage.tsx          # UI component

app/api/tournament/
└── route.ts                        # API endpoint
```

