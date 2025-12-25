#!/usr/bin/env python3
"""
Backfill historical entry stats for all spread-based trades.

This script updates all existing spread-based trades to include:
- spread_mean_at_entry: The mean at signal time (frozen)
- spread_std_at_entry: The std at signal time (frozen)

This ensures the chart displays entry lines frozen at signal time.
"""

import json
import logging
import sys
import os
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from trading_bot.db.client import get_connection, release_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def backfill_spread_trade_stats(dry_run: bool = False):
    """Backfill historical entry stats for all spread-based trades."""
    from trading_bot.db.client import query, execute, DB_TYPE

    conn = get_connection()

    try:
        # Get all spread-based trades
        # Use different SQL syntax for PostgreSQL vs SQLite
        if DB_TYPE == 'postgres':
            sql = """
                SELECT id, strategy_metadata
                FROM trades
                WHERE strategy_metadata IS NOT NULL
                  AND (strategy_metadata::jsonb)->>'pair_symbol' IS NOT NULL
            """
        else:
            sql = """
                SELECT id, strategy_metadata
                FROM trades
                WHERE strategy_metadata IS NOT NULL
                  AND json_extract(strategy_metadata, '$.pair_symbol') IS NOT NULL
            """

        trades = query(conn, sql)

        logger.info(f"Found {len(trades)} spread-based trades to backfill")

        updated_count = 0
        skipped_count = 0

        for trade in trades:
            try:
                trade_id = trade['id']
                metadata_str = trade['strategy_metadata']
                metadata = json.loads(metadata_str) if isinstance(metadata_str, str) else metadata_str

                # Check if already has entry stats
                if 'spread_mean_at_entry' in metadata and 'spread_std_at_entry' in metadata:
                    skipped_count += 1
                    continue

                # Backfill from current stats
                if 'spread_mean' in metadata:
                    metadata['spread_mean_at_entry'] = metadata['spread_mean']
                if 'spread_std' in metadata:
                    metadata['spread_std_at_entry'] = metadata['spread_std']

                if not dry_run:
                    # Update database
                    execute(conn,
                        "UPDATE trades SET strategy_metadata = ? WHERE id = ?",
                        (json.dumps(metadata), trade_id)
                    )

                updated_count += 1

                if updated_count % 100 == 0:
                    logger.info(f"Would update {updated_count} trades..." if dry_run else f"Updated {updated_count} trades...")

            except Exception as e:
                logger.error(f"Error processing trade {trade_id}: {e}")
                continue

        logger.info(f"{'[DRY RUN] ' if dry_run else ''}✅ Backfill complete: {updated_count} trades to update, {skipped_count} already have entry stats")

        # Verify
        if DB_TYPE == 'postgres':
            verify_sql = """
                SELECT
                  COUNT(*) as total,
                  COUNT(CASE WHEN (strategy_metadata::jsonb)->'spread_mean_at_entry' IS NOT NULL THEN 1 END) as with_mean,
                  COUNT(CASE WHEN (strategy_metadata::jsonb)->'spread_std_at_entry' IS NOT NULL THEN 1 END) as with_std
                FROM trades
                WHERE strategy_metadata IS NOT NULL
                  AND (strategy_metadata::jsonb)->>'pair_symbol' IS NOT NULL
            """
        else:
            verify_sql = """
                SELECT
                  COUNT(*) as total,
                  COUNT(CASE WHEN json_extract(strategy_metadata, '$.spread_mean_at_entry') IS NOT NULL THEN 1 END) as with_mean,
                  COUNT(CASE WHEN json_extract(strategy_metadata, '$.spread_std_at_entry') IS NOT NULL THEN 1 END) as with_std
                FROM trades
                WHERE strategy_metadata IS NOT NULL
                  AND json_extract(strategy_metadata, '$.pair_symbol') IS NOT NULL
            """

        verify = query(conn, verify_sql)

        if verify:
            result = verify[0]
            logger.info(f"Verification: {result['total']} total spread trades, {result['with_mean']} with mean_at_entry, {result['with_std']} with std_at_entry")

    finally:
        release_connection(conn)


if __name__ == '__main__':
    import sys

    dry_run = '--dry-run' in sys.argv or '-n' in sys.argv

    if dry_run:
        logger.info("🔍 Running in DRY RUN mode - no changes will be made")

    backfill_spread_trade_stats(dry_run=dry_run)

    if dry_run:
        logger.info("To apply changes, run: python python/scripts/backfill_spread_trade_stats.py")

