#!/usr/bin/env python3
"""
Diagnostic script to identify why 17 spread-based trades are still open.

Checks:
1. Trade status and required fields
2. Missing filled_at timestamps
3. Missing strategy_metadata
4. Missing pair data (pair_quantity, pair_fill_price)
5. Missing exit data
"""

import sys
sys.path.insert(0, 'python')

from trading_bot.db.client import get_connection, query
import json
from datetime import datetime

def diagnose_open_spread_trades():
    """Diagnose why spread trades are still open."""
    conn = get_connection()
    
    # Get all open/filled spread trades
    trades = query(conn, """
        SELECT 
            id,
            symbol,
            status,
            created_at,
            filled_at,
            closed_at,
            entry_price,
            stop_loss,
            take_profit,
            quantity,
            pair_quantity,
            fill_price,
            pair_fill_price,
            exit_price,
            pair_exit_price,
            exit_reason,
            pnl,
            strategy_metadata
        FROM trades
        WHERE strategy_type = 'spread_based'
        AND status IN ('paper_trade', 'filled', 'open')
        ORDER BY created_at DESC
    """)
    
    print(f"\n📊 DIAGNOSTIC REPORT: {len(trades)} Open Spread Trades\n")
    print("=" * 100)
    
    issues_by_type = {
        'missing_filled_at': [],
        'missing_pair_data': [],
        'missing_metadata': [],
        'missing_exit_data': [],
        'timestamp_issues': [],
    }
    
    for i, trade in enumerate(trades, 1):
        trade_id = trade[0]
        symbol = trade[1]
        status = trade[2]
        created_at = trade[3]
        filled_at = trade[4]
        closed_at = trade[5]
        entry_price = trade[6]
        stop_loss = trade[7]
        take_profit = trade[8]
        quantity = trade[9]
        pair_quantity = trade[10]
        fill_price = trade[11]
        pair_fill_price = trade[12]
        exit_price = trade[13]
        pair_exit_price = trade[14]
        exit_reason = trade[15]
        pnl = trade[16]
        strategy_metadata = trade[17]
        
        print(f"\n{i}. Trade {trade_id[:8]}... | {symbol} | Status: {status}")
        print(f"   Created: {created_at}")
        print(f"   Filled: {filled_at}")
        print(f"   Closed: {closed_at}")
        
        # Check for issues
        issues = []
        
        # Issue 1: Missing filled_at
        if not filled_at:
            issues.append("❌ MISSING filled_at - Cannot close unfilled trade")
            issues_by_type['missing_filled_at'].append(trade_id)
        
        # Issue 2: Missing pair data
        if not pair_quantity or not pair_fill_price:
            issues.append(f"❌ MISSING pair data - pair_qty={pair_quantity}, pair_fill={pair_fill_price}")
            issues_by_type['missing_pair_data'].append(trade_id)
        
        # Issue 3: Missing strategy metadata
        if not strategy_metadata:
            issues.append("❌ MISSING strategy_metadata - Cannot calculate z-score exit")
            issues_by_type['missing_metadata'].append(trade_id)
        else:
            try:
                metadata = json.loads(strategy_metadata) if isinstance(strategy_metadata, str) else strategy_metadata
                required_fields = ['beta', 'spread_mean', 'spread_std', 'z_exit_threshold', 'pair_symbol']
                missing_fields = [f for f in required_fields if f not in metadata]
                if missing_fields:
                    issues.append(f"❌ INCOMPLETE metadata - Missing: {missing_fields}")
                    issues_by_type['missing_metadata'].append(trade_id)
            except Exception as e:
                issues.append(f"❌ INVALID metadata JSON: {e}")
                issues_by_type['missing_metadata'].append(trade_id)
        
        # Issue 4: Missing exit data
        if not exit_price or not exit_reason:
            issues.append(f"❌ MISSING exit data - exit_price={exit_price}, reason={exit_reason}")
            issues_by_type['missing_exit_data'].append(trade_id)
        
        # Issue 5: Timestamp issues
        if filled_at and closed_at:
            if filled_at > closed_at:
                issues.append(f"❌ TIMESTAMP VIOLATION - filled_at > closed_at")
                issues_by_type['timestamp_issues'].append(trade_id)
        
        if issues:
            for issue in issues:
                print(f"   {issue}")
        else:
            print(f"   ✅ All data present - Trade should be closeable")
    
    # Summary
    print("\n" + "=" * 100)
    print("\n📋 SUMMARY BY ISSUE TYPE:\n")
    
    for issue_type, trade_ids in issues_by_type.items():
        if trade_ids:
            print(f"{issue_type.upper()}: {len(trade_ids)} trades")
            print(f"  Trade IDs: {', '.join([t[:8] for t in trade_ids])}")
    
    print(f"\n✅ TOTAL TRADES WITH NO ISSUES: {len(trades) - sum(len(v) for v in issues_by_type.values())}")
    print(f"❌ TOTAL TRADES WITH ISSUES: {sum(len(v) for v in issues_by_type.values())}")

if __name__ == '__main__':
    diagnose_open_spread_trades()

