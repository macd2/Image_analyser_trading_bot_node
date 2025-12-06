"""Analytics utilities for trading bot performance tracking."""

import uuid
from datetime import datetime
from typing import Dict, Any, Optional


def calculate_holding_period_hours(created_at, closed_at) -> float:
    """Calculate holding period in hours between two timestamps."""
    if not created_at or not closed_at:
        return 0.0
    
    # Ensure both timestamps are datetime objects
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
    if isinstance(closed_at, str):
        closed_at = datetime.fromisoformat(closed_at.replace('Z', '+00:00'))
    
    # Calculate difference in hours
    time_diff = closed_at - created_at
    return time_diff.total_seconds() / 3600.0


def assign_to_holding_bucket(holding_hours: float) -> str:
    """Assign a holding period to the appropriate bucket with more granular buckets."""
    # More granular time buckets for better analysis
    # Ordered from shortest to longest duration for logical sorting
    TIME_BUCKETS = [
        ('0-1h', 0, 1),         # 0-1 hours
        ('1-2h', 1, 2),         # 1-2 hours
        ('2-5h', 2, 5),         # 2-5 hours
        ('5-8h', 5, 8),         # 5-8 hours
        ('8-12h', 8, 12),       # 8-12 hours
        ('12-24h', 12, 24),     # 12-24 hours  
        ('1-3d', 24, 72),       # 1-3 days
        ('3-7d', 72, 168),      # 3-7 days
        ('7d+', 168, float('inf'))  # 7+ days
    ]
    
    for bucket_name, min_hours, max_hours in TIME_BUCKETS:
        if min_hours <= holding_hours < max_hours:
            return bucket_name
    
    # Fallback for edge cases
    return '7d+' if holding_hours >= 168 else '0-1h'


def calculate_live_rr(entry_price: float, current_price: float, stop_loss: float, 
                     direction: str) -> float:
    """Calculate live risk/reward ratio for a position."""
    from trading_bot.core.utils import normalize_direction
    
    try:
        direction = normalize_direction(direction)
        
        if direction == 'LONG':
            # For long positions
            risk_per_unit = entry_price - stop_loss
            reward_per_unit = current_price - entry_price
        else:  # SHORT
            # For short positions
            risk_per_unit = stop_loss - entry_price
            reward_per_unit = entry_price - current_price
        
        if risk_per_unit <= 0:
            return 0.0
        
        return reward_per_unit / risk_per_unit
        
    except (ValueError, ZeroDivisionError):
        return 0.0


def get_timeframe_from_trade_data(trade_data: Dict[str, Any], data_agent) -> str:
    """Extract timeframe from trade data using recommendation_id."""
    try:
        recommendation_id = trade_data.get('recommendation_id')
        if not recommendation_id:
            return 'unknown'
        
        # Query the analysis_results table for the timeframe
        conn = data_agent.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT timeframe FROM analysis_results WHERE id = ?
        ''', (recommendation_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else 'unknown'
        
    except Exception:
        return 'unknown'


def format_analytics_summary(stats: Dict[str, Any]) -> str:
    """Format analytics data for display."""
    if not stats or stats.get('error'):
        return "❌ No analytics data available"
    
    total_trades = stats.get('total_trades', 0)
    if total_trades == 0:
        return "📊 No completed trades for analytics"
    
    win_rate = stats.get('portfolio_win_rate', 0) * 100
    profit_factor = stats.get('portfolio_profit_factor', 0)
    expected_value = stats.get('avg_expected_value', 0)
    total_pnl = stats.get('total_pnl', 0)
    
    # Determine performance indicators
    pf_indicator = "🟢" if profit_factor > 1.5 else "🟡" if profit_factor > 1.0 else "🔴"
    wr_indicator = "🟢" if win_rate > 60 else "🟡" if win_rate > 45 else "🔴"
    ev_indicator = "🟢" if expected_value > 0 else "🔴"
    
    summary_lines = [
        "📊 PORTFOLIO ANALYTICS SUMMARY",
        "=" * 50,
        f"Total Trades: {total_trades}",
        f"Win Rate: {wr_indicator} {win_rate:.1f}%",
        f"Profit Factor: {pf_indicator} {profit_factor:.2f}",
        f"Expected Value: {ev_indicator} {expected_value:.2f}",
        f"Total PnL: {total_pnl:.2f}",
        "=" * 50
    ]
    
    return "\n".join(summary_lines)


def create_position_tracking_data(position_info, recommendation_id: Optional[str] = None,
                                trade_id: Optional[str] = None, timeframe: str = "unknown") -> Dict[str, Any]:
    """Create position tracking data structure for database storage."""
    from trading_bot.core.utils import normalize_direction, convert_side_to_direction
    
    direction = normalize_direction(convert_side_to_direction(position_info.side))
    
    # Calculate live R/R
    live_rr = calculate_live_rr(
        position_info.entry_price,
        position_info.current_price,
        position_info.current_stop_loss or 0,
        direction
    )
    
    return {
        'recommendation_id': recommendation_id,
        'trade_id': trade_id,
        'symbol': position_info.symbol,
        'timeframe': timeframe,
        'direction': direction,
        'entry_price': position_info.entry_price,
        'current_price': position_info.current_price,
        'stop_loss': position_info.current_stop_loss,
        'take_profit': position_info.current_take_profit,
        'live_rr': live_rr,
        'unrealized_pnl': position_info.unrealized_pnl,
        'risk_amount': position_info.risk_amount,
        'position_size': position_info.size,
        'checked_at': datetime.utcnow().isoformat()
    }


def update_comprehensive_trading_stats(data_agent) -> Dict[str, Any]:
    """
    Update comprehensive trading statistics for all symbol/timeframe combinations once per cycle.
    
    This function provides a complete refresh of trading statistics, ensuring all data is current
    and synchronized with the latest trade information.
    
    Args:
        data_agent: DataAgent instance for database operations
        
    Returns:
        Dict with update results including success status and statistics
    """
    try:
        # Get database connection
        conn = data_agent.get_connection()
        cursor = conn.cursor()
        
        # Get only closed trades to calculate comprehensive statistics
        cursor.execute('''
            SELECT id, symbol, status, pnl, created_at, updated_at, recommendation_id
            FROM trades 
            WHERE status = 'closed'
            ORDER BY symbol, created_at
        ''')
        
        trades = cursor.fetchall()
        
        if not trades:
            conn.close()
            return {
                "status": "success",
                "message": "No trades found for statistics update",
                "updated_records": 0,
                "symbol_timeframe_stats": {},
                "holding_period_stats": {}
            }
        
        # Group trades by symbol and timeframe
        symbol_timeframe_data = {}
        # Group trades by symbol, timeframe, and holding period bucket
        holding_period_data = {}
        
        # Import the symbol normalization function
        from trading_bot.core.utils import normalize_symbol_for_bybit
        
        for trade in trades:
            trade_id = trade[0]
            raw_symbol = trade[1]
            status = trade[2]
            pnl = trade[3] or 0
            created_at = trade[4]
            updated_at = trade[5]
            recommendation_id = trade[6]
            
            # Normalize the symbol to ensure consistency
            symbol = normalize_symbol_for_bybit(raw_symbol)
            
            # Get timeframe from recommendation_id
            timeframe = 'unknown'
            if recommendation_id:
                cursor.execute('''
                    SELECT timeframe FROM analysis_results WHERE id = ?
                ''', (recommendation_id,))
                timeframe_result = cursor.fetchone()
                if timeframe_result:
                    timeframe = timeframe_result[0]
            
            # Create symbol-timeframe key
            key = f"{symbol}_{timeframe}"
            
            if key not in symbol_timeframe_data:
                symbol_timeframe_data[key] = {
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'total_trades': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'total_pnl': 0.0,
                    'total_win_pnl': 0.0,
                    'total_loss_pnl': 0.0,
                    'wins': [],
                    'losses': []
                }
            
            # Update statistics
            stats = symbol_timeframe_data[key]
            stats['total_trades'] += 1
            
            if pnl > 0:
                stats['winning_trades'] += 1
                stats['total_win_pnl'] += pnl
                stats['wins'].append(pnl)
            elif pnl < 0:
                stats['losing_trades'] += 1
                stats['total_loss_pnl'] += abs(pnl)
                stats['losses'].append(abs(pnl))
            
            stats['total_pnl'] += pnl

            # Calculate holding period stats for closed trades
            if status == 'closed':
                holding_hours = calculate_holding_period_hours(created_at, updated_at)
                holding_bucket = assign_to_holding_bucket(holding_hours)
                
                holding_key = f"{symbol}_{timeframe}_{holding_bucket}"
                
                if holding_key not in holding_period_data:
                    holding_period_data[holding_key] = {
                        'symbol': symbol,
                        'timeframe': timeframe,
                        'holding_period_bucket': holding_bucket,
                        'total_trades': 0,
                        'winning_trades': 0,
                        'losing_trades': 0,
                        'total_pnl': 0.0,
                        'total_win_pnl': 0.0,
                        'total_loss_pnl': 0.0,
                        'wins': [],
                        'losses': [],
                        'total_holding_hours': 0.0
                    }
                
                holding_stats = holding_period_data[holding_key]
                holding_stats['total_trades'] += 1
                holding_stats['total_holding_hours'] += holding_hours
                
                if pnl > 0:
                    holding_stats['winning_trades'] += 1
                    holding_stats['total_win_pnl'] += pnl
                    holding_stats['wins'].append(pnl)
                elif pnl < 0:
                    holding_stats['losing_trades'] += 1
                    holding_stats['total_loss_pnl'] += abs(pnl)
                    holding_stats['losses'].append(abs(pnl))
                
                holding_stats['total_pnl'] += pnl
        
        # Calculate derived metrics for each symbol/timeframe combination
        updated_records = 0
        symbol_timeframe_stats = {}
        
        for key, stats in symbol_timeframe_data.items():
            # Calculate win rate
            win_rate = stats['winning_trades'] / stats['total_trades'] if stats['total_trades'] > 0 else 0
            
            # Calculate average win/loss
            avg_win = stats['total_win_pnl'] / stats['winning_trades'] if stats['winning_trades'] > 0 else 0
            avg_loss = stats['total_loss_pnl'] / stats['losing_trades'] if stats['losing_trades'] > 0 else 0
            
            # Calculate profit factor
            profit_factor = stats['total_win_pnl'] / stats['total_loss_pnl'] if stats['total_loss_pnl'] > 0 else 0
            
            # Calculate expected value
            loss_rate = 1 - win_rate if stats['total_trades'] > 0 else 0
            expected_value = (win_rate * avg_win) - (loss_rate * avg_loss) if avg_win > 0 and avg_loss > 0 else 0
            
            # Calculate max win/loss
            max_win = max(stats['wins']) if stats['wins'] else 0
            max_loss = max(stats['losses']) if stats['losses'] else 0
            
            # Prepare data for database update
            stats_data = {
                'total_trades': stats['total_trades'],
                'winning_trades': stats['winning_trades'],
                'losing_trades': stats['losing_trades'],
                'total_pnl': stats['total_pnl'],
                'total_win_pnl': stats['total_win_pnl'],
                'total_loss_pnl': stats['total_loss_pnl'],
                'win_rate': win_rate,
                'profit_factor': profit_factor,
                'expected_value': expected_value,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'max_win': max_win,
                'max_loss': max_loss,
                'last_updated': datetime.utcnow().isoformat()
            }
            
            symbol_timeframe_stats[key] = stats_data
            
            # Update or insert trading_stats record
            cursor.execute('''
                SELECT id FROM trading_stats 
                WHERE symbol = ? AND timeframe = ?
            ''', (stats['symbol'], stats['timeframe']))
            
            existing_record = cursor.fetchone()
            
            if existing_record:
                # Update existing record
                stats_id = existing_record[0]
                cursor.execute('''
                    UPDATE trading_stats SET
                        total_trades = ?,
                        winning_trades = ?,
                        losing_trades = ?,
                        total_pnl = ?,
                        total_win_pnl = ?,
                        total_loss_pnl = ?,
                        win_rate = ?,
                        profit_factor = ?,
                        expected_value = ?,
                        avg_win = ?,
                        avg_loss = ?,
                        max_win = ?,
                        max_loss = ?,
                        last_updated = ?
                    WHERE id = ?
                ''', (
                    stats_data['total_trades'],
                    stats_data['winning_trades'],
                    stats_data['losing_trades'],
                    stats_data['total_pnl'],
                    stats_data['total_win_pnl'],
                    stats_data['total_loss_pnl'],
                    stats_data['win_rate'],
                    stats_data['profit_factor'],
                    stats_data['expected_value'],
                    stats_data['avg_win'],
                    stats_data['avg_loss'],
                    stats_data['max_win'],
                    stats_data['max_loss'],
                    stats_data['last_updated'],
                    stats_id
                ))
            else:
                # Insert new record
                stats_id = str(uuid.uuid4())
                cursor.execute('''
                    INSERT INTO trading_stats (
                        id, symbol, timeframe, total_trades, winning_trades, losing_trades,
                        total_pnl, total_win_pnl, total_loss_pnl, win_rate, profit_factor,
                        expected_value, avg_win, avg_loss, max_win, max_loss, last_updated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    stats_id,
                    stats['symbol'],
                    stats['timeframe'],
                    stats_data['total_trades'],
                    stats_data['winning_trades'],
                    stats_data['losing_trades'],
                    stats_data['total_pnl'],
                    stats_data['total_win_pnl'],
                    stats_data['total_loss_pnl'],
                    stats_data['win_rate'],
                    stats_data['profit_factor'],
                    stats_data['expected_value'],
                    stats_data['avg_win'],
                    stats_data['avg_loss'],
                    stats_data['max_win'],
                    stats_data['max_loss'],
                    stats_data['last_updated']
                ))
            
            updated_records += 1

        # Calculate derived metrics for each holding period bucket
        holding_period_updated_records = 0
        holding_period_stats_summary = {}

        for holding_key, stats in holding_period_data.items():
            # Calculate win rate
            win_rate = stats['winning_trades'] / stats['total_trades'] if stats['total_trades'] > 0 else 0
            
            # Calculate average win/loss
            avg_win = stats['total_win_pnl'] / stats['winning_trades'] if stats['winning_trades'] > 0 else 0
            avg_loss = stats['total_loss_pnl'] / stats['losing_trades'] if stats['losing_trades'] > 0 else 0
            
            # Calculate profit factor
            profit_factor = stats['total_win_pnl'] / stats['total_loss_pnl'] if stats['total_loss_pnl'] > 0 else 0
            
            # Calculate average PnL
            avg_pnl = stats['total_pnl'] / stats['total_trades'] if stats['total_trades'] > 0 else 0

            # Calculate average holding hours
            avg_holding_hours = stats['total_holding_hours'] / stats['total_trades'] if stats['total_trades'] > 0 else 0
            
            # Calculate max win/loss
            max_win = max(stats['wins']) if stats['wins'] else 0
            max_loss = max(stats['losses']) if stats['losses'] else 0
            
            # Prepare data for database update
            stats_data = {
                'total_trades': stats['total_trades'],
                'winning_trades': stats['winning_trades'],
                'losing_trades': stats['losing_trades'],
                'total_pnl': stats['total_pnl'],
                'total_win_pnl': stats['total_win_pnl'],
                'total_loss_pnl': stats['total_loss_pnl'],
                'win_rate': win_rate,
                'profit_factor': profit_factor,
                'avg_pnl': avg_pnl,
                'avg_win_pnl': avg_win,
                'avg_loss_pnl': avg_loss,
                'max_win': max_win,
                'max_loss': max_loss,
                'avg_holding_hours': avg_holding_hours,
                'last_updated': datetime.utcnow().isoformat()
            }
            
            holding_period_stats_summary[holding_key] = stats_data
            
            # Update or insert holding_period_stats record
            cursor.execute('''
                SELECT id FROM holding_period_stats 
                WHERE symbol = ? AND timeframe = ? AND holding_period_bucket = ?
            ''', (stats['symbol'], stats['timeframe'], stats['holding_period_bucket']))
            
            existing_record = cursor.fetchone()
            
            if existing_record:
                # Update existing record
                stats_id = existing_record[0]
                cursor.execute('''
                    UPDATE holding_period_stats SET
                        total_trades = ?,
                        winning_trades = ?,
                        losing_trades = ?,
                        total_pnl = ?,
                        total_win_pnl = ?,
                        total_loss_pnl = ?,
                        win_rate = ?,
                        profit_factor = ?,
                        avg_pnl = ?,
                        avg_win_pnl = ?,
                        avg_loss_pnl = ?,
                        max_win = ?,
                        max_loss = ?,
                        avg_holding_hours = ?,
                        last_updated = ?
                    WHERE id = ?
                ''', (
                    stats_data['total_trades'],
                    stats_data['winning_trades'],
                    stats_data['losing_trades'],
                    stats_data['total_pnl'],
                    stats_data['total_win_pnl'],
                    stats_data['total_loss_pnl'],
                    stats_data['win_rate'],
                    stats_data['profit_factor'],
                    stats_data['avg_pnl'],
                    stats_data['avg_win_pnl'],
                    stats_data['avg_loss_pnl'],
                    stats_data['max_win'],
                    stats_data['max_loss'],
                    stats_data['avg_holding_hours'],
                    stats_data['last_updated'],
                    stats_id
                ))
            else:
                # Insert new record
                stats_id = str(uuid.uuid4())
                cursor.execute('''
                    INSERT INTO holding_period_stats (
                        id, symbol, timeframe, holding_period_bucket, total_trades, winning_trades, losing_trades,
                        total_pnl, total_win_pnl, total_loss_pnl, win_rate, profit_factor,
                        avg_pnl, avg_win_pnl, avg_loss_pnl, max_win, max_loss, avg_holding_hours, last_updated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    stats_id,
                    stats['symbol'],
                    stats['timeframe'],
                    stats['holding_period_bucket'],
                    stats_data['total_trades'],
                    stats_data['winning_trades'],
                    stats_data['losing_trades'],
                    stats_data['total_pnl'],
                    stats_data['total_win_pnl'],
                    stats_data['total_loss_pnl'],
                    stats_data['win_rate'],
                    stats_data['profit_factor'],
                    stats_data['avg_pnl'],
                    stats_data['avg_win_pnl'],
                    stats_data['avg_loss_pnl'],
                    stats_data['max_win'],
                    stats_data['max_loss'],
                    stats_data['avg_holding_hours'],
                    stats_data['last_updated']
                ))
            
            holding_period_updated_records += 1
        
        conn.commit()
        conn.close()
        
        return {
            "status": "success",
            "message": f"Updated trading statistics for {updated_records} symbol/timeframe combinations and {holding_period_updated_records} holding period records",
            "updated_records": updated_records,
            "symbol_timeframe_stats": symbol_timeframe_stats,
            "holding_period_stats": holding_period_stats_summary
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": f"Failed to update comprehensive trading statistics: {str(e)}"
        }


def get_portfolio_analytics_summary(data_agent) -> Dict[str, Any]:
    """
    Get comprehensive portfolio analytics summary including all trading statistics.
    
    Args:
        data_agent: DataAgent instance for database operations
        
    Returns:
        Dict with comprehensive portfolio analytics
    """
    try:
        # Use existing portfolio summary method from data_agent
        portfolio_summary = data_agent.get_portfolio_ev_summary()
        
        # Get detailed trading stats
        detailed_stats = data_agent.get_trading_stats()
        
        return {
            "status": "success",
            "portfolio_summary": portfolio_summary,
            "detailed_stats": detailed_stats,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": f"Failed to get portfolio analytics summary: {str(e)}"
        }
