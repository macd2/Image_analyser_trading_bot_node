#!/usr/bin/env python3
"""
Update all trades with correct strategy_type and strategy_name.

Logic:
1. For trades with strategy_metadata: Extract strategy_type and strategy_name from metadata
2. For trades without strategy_metadata: 
   - Look up the recommendation to get strategy info
   - If recommendation has strategy info: use it
   - If not: default to price_based + PromptStrategy (old AI strategy)

Usage:
    python scripts/update_trades_strategy_info.py --dry-run  # Test first
    python scripts/update_trades_strategy_info.py --execute  # Actually update
"""

import os
import sys
import json
import argparse
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "python"))

from trading_bot.db.client import get_connection, query, execute

def get_stats(conn):
    """Get current stats on trades."""
    stats = query(conn, """
        SELECT 
            COUNT(*) as total_trades,
            COUNT(CASE WHEN strategy_type IS NULL THEN 1 END) as trades_without_strategy_type,
            COUNT(CASE WHEN strategy_metadata IS NOT NULL THEN 1 END) as trades_with_metadata,
            COUNT(CASE WHEN strategy_metadata IS NULL THEN 1 END) as trades_without_metadata
        FROM trades
    """)
    return stats[0] if stats else {}

def update_trades_with_metadata(conn, dry_run=True):
    """Update trades that have strategy_metadata."""
    # Get trades with metadata but no strategy_type
    trades = query(conn, """
        SELECT id, strategy_metadata 
        FROM trades 
        WHERE strategy_metadata IS NOT NULL 
        AND strategy_type IS NULL
    """)
    
    updated = 0
    for trade in trades:
        try:
            metadata = json.loads(trade['strategy_metadata']) if isinstance(trade['strategy_metadata'], str) else trade['strategy_metadata']
            strategy_type = metadata.get('strategy_type')
            strategy_name = metadata.get('strategy_name')
            
            if strategy_type and strategy_name:
                if not dry_run:
                    execute(conn, """
                        UPDATE trades 
                        SET strategy_type = ?, strategy_name = ?
                        WHERE id = ?
                    """, (strategy_type, strategy_name, trade['id']))
                updated += 1
                print(f"  ✓ {trade['id']}: {strategy_type} / {strategy_name}")
        except Exception as e:
            print(f"  ✗ {trade['id']}: Error - {e}")
    
    return updated

def update_trades_from_instances(conn, dry_run=True):
    """Update trades based on their instance's configured strategy."""
    # Map instance IDs to their correct strategy info
    instance_strategy_map = {
        '3b21e1be-15d0-4db7-bfe6-a65300db076d': ('price_based', 'PromptStrategy'),  # FastTrader
        'ab8b1a36-4797-4b49-91f0-f2670e76e0cd': ('price_based', 'PromptStrategy'),  # Playboy1
        'a3e1afd3-1b04-4aac-90bf-ccccd52dcfba': ('spread_based', 'CointegrationAnalysisModule'),  # TestingInstance
        '3660703e-f95a-4fca-a8e2-ec3844124186': ('spread_based', 'CointegrationAnalysisModule'),  # SpreadTrader
    }

    # Get trades with their instance info
    trades = query(conn, """
        SELECT t.id, r.instance_id
        FROM trades t
        LEFT JOIN runs r ON t.run_id = r.id
    """)

    updated = 0
    for trade in trades:
        instance_id = trade['instance_id']
        if instance_id in instance_strategy_map:
            strategy_type, strategy_name = instance_strategy_map[instance_id]

            if not dry_run:
                execute(conn, """
                    UPDATE trades
                    SET strategy_type = ?, strategy_name = ?
                    WHERE id = ?
                """, (strategy_type, strategy_name, trade['id']))
            updated += 1
            print(f"  ✓ {trade['id']}: {strategy_type} / {strategy_name}")
        else:
            print(f"  ⚠ {trade['id']}: Unknown instance {instance_id}")

    return updated

def main():
    parser = argparse.ArgumentParser(description='Update trades with strategy info')
    parser.add_argument('--dry-run', action='store_true', help='Test without making changes')
    parser.add_argument('--execute', action='store_true', help='Actually update the database')
    args = parser.parse_args()
    
    dry_run = not args.execute
    
    conn = get_connection()
    
    print("\n📊 Current Trade Statistics:")
    stats = get_stats(conn)
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print(f"\n{'[DRY RUN]' if dry_run else '[EXECUTING]'} Updating trades with metadata...")
    updated_metadata = update_trades_with_metadata(conn, dry_run)
    print(f"  Total updated: {updated_metadata}")

    print(f"\n{'[DRY RUN]' if dry_run else '[EXECUTING]'} Updating trades from instances...")
    updated_instances = update_trades_from_instances(conn, dry_run)
    print(f"  Total updated: {updated_instances}")
    
    print(f"\n📊 Final Statistics:")
    stats = get_stats(conn)
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    if dry_run:
        print("\n✅ Dry run complete. Run with --execute to apply changes.")
    else:
        print("\n✅ Update complete!")

if __name__ == '__main__':
    main()

