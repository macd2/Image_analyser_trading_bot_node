"""Utility functions for trading bot operations."""
import logging
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Set, Optional

# Global variables for server time synchronization
_server_time_offset = 0  # Offset in milliseconds
_last_sync_time = 0
_sync_interval = 3  # Default sync every 1 second (more aggressive)
# The following variables are no longer needed due to simplified sync logic
# _timestamp_error_count = 0 # Track consecutive timestamp errors
# _last_timestamp_error_time = 0 # Time of the last timestamp error
# _aggressive_sync_interval = 2 # Sync every 2 seconds during aggressive mode
# _normal_sync_interval = 5 # Normal sync interval
# _error_threshold_for_aggressive_sync = 3 # Number of consecutive errors to trigger aggressive sync
# _aggressive_sync_duration = 60 # Duration in seconds for aggressive sync mode


def calculate_risk_reward_ratio(entry_price: float, take_profit: float, stop_loss: float, direction: str) -> float:
    """
    Calculate risk-reward ratio for a trade.

    Args:
        entry_price: Entry price for the trade
        take_profit: Take profit price
        stop_loss: Stop loss price
        direction: Trade direction ('LONG', 'BUY', 'SHORT', 'SELL')

    Returns:
        Risk-reward ratio (profit distance / loss distance)
    """
    if entry_price <= 0 or take_profit <= 0 or stop_loss <= 0:
        return 0.0

    direction_upper = direction.upper()

    if direction_upper in ['LONG', 'BUY']:
        profit_distance = abs(take_profit - entry_price)
        loss_distance = abs(entry_price - stop_loss)
    else:  # SHORT/SELL
        profit_distance = abs(entry_price - take_profit)
        loss_distance = abs(stop_loss - entry_price)  # Fixed: was using take_profit instead of stop_loss
    
    if loss_distance <= 0:
        return 0.0
    
    return profit_distance / loss_distance


def format_trade_details(symbol: str, recommendation: Dict[str, Any], include_rr: bool = True, position_size: Optional[float] = None) -> str:
    """
    Format trade details string with optional RR ratio and position size.
    
    Args:
        symbol: Trading symbol
        recommendation: Trade recommendation data
        include_rr: Whether to include RR ratio in output
        position_size: Optional position size to include in output
        
    Returns:
        Formatted trade details string
    """
    direction = recommendation.get("direction", "").upper()
    entry_price = recommendation.get("entry_price", 0)
    
    base_details = f"{direction} {symbol} @ {entry_price}"
    
    # Add position size if provided
    if position_size is not None:
        base_details += f" (Size: {position_size})"
    
    if not include_rr:
        return base_details
    
    take_profit = recommendation.get("take_profit", 0)
    stop_loss = recommendation.get("stop_loss", 0)
    
    rr_ratio = calculate_risk_reward_ratio(entry_price, take_profit, stop_loss, direction)
    
    # Format with RR ratio
    if position_size is not None:
        return f"{direction} {symbol} @ {entry_price} (Size: {position_size}, RR: {rr_ratio:.2f})"
    else:
        return f"{base_details} (RR: {rr_ratio:.2f})"


def get_supported_image_extensions() -> Set[str]:
    """
    Get set of supported image file extensions.

    Returns:
        Set of supported image extensions (lowercase with dots)
    """
    return {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp'}


def clean_filename_for_parsing(filename: str) -> str:
    """
    Clean filename by removing all extensions including .backup.

    This function handles both regular image files and .backup files by removing
    all extensions to get the base filename for parsing.

    Args:
        filename: Filename that may have multiple extensions

    Returns:
        Cleaned filename without extensions
    """
    from pathlib import Path

    # Handle .backup files by removing both .backup and image extension
    if filename.endswith('.backup'):
        # Remove .backup first
        name_without_backup = Path(filename).stem
        # Then remove the image extension
        return Path(name_without_backup).stem

    # For regular files, just remove the single extension
    return Path(filename).stem


def find_image_files(directory: Path) -> List[Path]:
    """
    Find all image files in a directory.
    
    Args:
        directory: Directory path to search
        
    Returns:
        List of image file paths
    """
    if not directory.exists():
        return []
    
    image_extensions = get_supported_image_extensions()
    return [f for f in directory.iterdir()
            if f.suffix.lower() in image_extensions and f.is_file()]


def calculate_time_to_boundary(current_time: datetime, next_boundary: datetime) -> Dict[str, float]:
    """
    Calculate time remaining until next boundary.
    
    Args:
        current_time: Current timestamp
        next_boundary: Next boundary timestamp
        
    Returns:
        Dict with time calculations in seconds and minutes
    """
    time_to_boundary = (next_boundary - current_time).total_seconds()
    return {
        "time_to_boundary_seconds": time_to_boundary,
        "time_to_boundary_minutes": time_to_boundary / 60
    }


def create_signal_data(recommendation: Dict[str, Any], timeframe: str = "") -> Dict[str, Any]:
    """
    Convert recommendation data to signal format for intelligent replacement system.
    
    Args:
        recommendation: Recommendation dictionary
        timeframe: Trading timeframe
        
    Returns:
        Signal data dictionary
    """
    return {
        'symbol': recommendation.get('symbol', ''),
        'recommendation': recommendation.get('recommendation', ''),
        'entry_price': recommendation.get('entry_price', 0),
        'take_profit': recommendation.get('take_profit', 0),
        'stop_loss': recommendation.get('stop_loss', 0),
        'direction': recommendation.get('direction', ''),
        'confidence': recommendation.get('confidence', 0),
        'timeframe': timeframe or recommendation.get('timeframe', ''),
        'recommendation_id': recommendation.get('id', ''),
        'timestamp': recommendation.get('timestamp', datetime.now(timezone.utc).isoformat())
    }


def create_trade_data(signal: Dict[str, Any], timeframe: str) -> Dict[str, Any]:
    """
    Convert signal data to trade format for execution.
    
    Args:
        signal: Signal dictionary
        timeframe: Trading timeframe
        
    Returns:
        Trade data dictionary
    """
    symbol = signal.get('symbol', '')
    return {
        "symbol": symbol,
        "direction": signal.get("direction", "").upper(),
        "timeframe": timeframe,
        "entry_price": signal.get("entry_price", 0),
        "stop_loss": signal.get("stop_loss", 0),
        "take_profits": [signal.get("take_profit", 0)],
        "trade_id": f"{symbol}_{int(time.time())}"
    }


def create_success_response(message: str, **kwargs) -> Dict[str, Any]:
    """
    Create standardized success response.
    
    Args:
        message: Success message
        **kwargs: Additional response data
        
    Returns:
        Standardized success response dictionary
    """
    response = {
        "status": "success",
        "message": message
    }
    response.update(kwargs)
    return response


def create_error_response(message: str, **kwargs) -> Dict[str, Any]:
    """
    Create standardized error response.
    
    Args:
        message: Error message
        **kwargs: Additional response data
        
    Returns:
        Standardized error response dictionary
    """
    response = {
        "status": "error",
        "message": message
    }
    response.update(kwargs)
    return response


def create_warning_response(message: str, **kwargs) -> Dict[str, Any]:
    """
    Create standardized warning response.
    
    Args:
        message: Warning message
        **kwargs: Additional response data
        
    Returns:
        Standardized warning response dictionary
    """
    response = {
        "status": "warning",
        "message": message
    }
    response.update(kwargs)
    return response


def check_component_health(component, component_name: str) -> Dict[str, Any]:
    """
    Check health status of a component.
    
    Args:
        component: Component to check (can be None)
        component_name: Name of the component for logging
        
    Returns:
        Health status dictionary
    """
    if component:
        return {"status": "healthy"}
    else:
        return {"status": "warning", "message": "Not available"}


def create_health_status_template() -> Dict[str, Any]:
    """
    Create template for system health status.
    
    Returns:
        Health status template dictionary
    """
    return {
        "status": "success",
        "components": {},
        "overall_health": True
    }


def check_mid_cycle_conditions(timestamp_validator, recommender, timeframe: str,
                             current_time: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Check if we're mid-cycle and if there are fresh recommendations for current boundary.
    
    This function integrates with existing TimestampValidator and Recommender components
    to detect mid-cycle conditions and check for fresh recommendations.
    
    Args:
        timestamp_validator: TimestampValidator instance for boundary calculations
        recommender: Recommender instance for fresh recommendation checking
        timeframe: Trading timeframe (e.g., "15m", "1h", "4h")
        current_time: Current time for validation (default: now in UTC)
        
    Returns:
        Dict containing:
        - is_mid_cycle: bool - Whether we're currently mid-cycle
        - has_fresh_recommendations: bool - Whether fresh recommendations exist
        - next_boundary: datetime - Next timeframe boundary
        - time_to_boundary_minutes: float - Minutes until next boundary
        - recommendations: List - Fresh recommendations if any
        - error: str - Error message if any
    """
    logger = logging.getLogger(__name__)
    
    try:
        if current_time is None:
            current_time = datetime.now(timezone.utc)
        elif current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        
        # Calculate current boundary using existing TimestampValidator
        timeframe_info = timestamp_validator.normalize_timeframe(timeframe)
        
        # Calculate previous boundary to determine if we're mid-cycle
        # We're mid-cycle if current time is significantly past the last boundary
        minutes = timeframe_info.minutes
        
        # Calculate the last boundary that occurred
        if timeframe_info.normalized == "1w":
            # Weekly boundary: last Monday at 00:00 UTC
            days_since_monday = current_time.weekday()
            last_boundary = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
            last_boundary -= timedelta(days=days_since_monday)
        elif timeframe_info.normalized == "1d":
            # Daily boundary: today at 00:00 UTC
            last_boundary = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        elif minutes >= 60:
            # Hourly boundaries
            hours = minutes // 60
            current_hour = current_time.hour
            last_hour = (current_hour // hours) * hours
            last_boundary = current_time.replace(hour=last_hour, minute=0, second=0, microsecond=0)
        else:
            # Minute boundaries
            current_minute = current_time.hour * 60 + current_time.minute
            last_minute = (current_minute // minutes) * minutes
            hour = last_minute // 60
            minute = last_minute % 60
            last_boundary = current_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # Calculate next boundary
        next_boundary = timestamp_validator.calculate_next_boundary(current_time, timeframe_info.normalized)
        
        # Determine if we're mid-cycle (more than 1% through the timeframe)
        total_timeframe_seconds = timeframe_info.timedelta.total_seconds()
        elapsed_seconds = (current_time - last_boundary).total_seconds()
        cycle_progress = elapsed_seconds / total_timeframe_seconds
        is_mid_cycle = cycle_progress > 0.01  # More than 1% through the cycle
        
        # Calculate time to boundary
        time_to_boundary = calculate_time_to_boundary(current_time, next_boundary)
        
        # Check for fresh recommendations using the new get_fresh_recommendations_for_boundary method
        fresh_recommendations = []
        has_fresh_recommendations = False
        
        if recommender and hasattr(recommender, 'get_fresh_recommendations_for_boundary'):
            try:
                # Get fresh recommendations for current boundary (timestamp validation only, no risk filtering)
                fresh_recommendations = recommender.get_fresh_recommendations_for_boundary("all", timeframe)
                has_fresh_recommendations = len(fresh_recommendations) > 0
                
                logger.info(f"Found {len(fresh_recommendations)} fresh recommendations for current boundary (no risk filtering)")
                
            except Exception as e:
                logger.warning(f"Could not check for fresh recommendations using new method: {e}")
                # Fallback to old method if new method fails
                try:
                    # Get recent recommendations from the database
                    recent_recs = recommender.db_queue.data_agent.get_all_latest_analysis()
                    
                    # Filter for the specific timeframe
                    timeframe_recs = [rec for rec in recent_recs
                                    if rec.get('timeframe') == timeframe]
                    
                    # Filter for recommendations that are still valid for current boundary
                    for rec in timeframe_recs:
                        if recommender.is_recommendation_valid(rec):
                            # Check if recommendation timestamp is for current boundary
                            rec_timestamp = timestamp_validator.parse_timestamp(rec.get('timestamp', ''))
                            if rec_timestamp >= last_boundary:
                                fresh_recommendations.append(rec)
                                has_fresh_recommendations = True
                    
                except Exception as fallback_error:
                    logger.warning(f"Could not check for fresh recommendations using fallback method: {fallback_error}")
        
        logger.info(f"Mid-cycle check: timeframe={timeframe}, is_mid_cycle={is_mid_cycle}, "
                   f"progress={cycle_progress:.1%}, fresh_recs={len(fresh_recommendations)}")
        
        return create_success_response(
            "Mid-cycle conditions checked successfully",
            is_mid_cycle=is_mid_cycle,
            has_fresh_recommendations=has_fresh_recommendations,
            next_boundary=next_boundary,
            time_to_boundary_minutes=time_to_boundary["time_to_boundary_minutes"],
            cycle_progress=cycle_progress,
            recommendations=fresh_recommendations,
            boundary_info={
                "last_boundary": last_boundary,
                "next_boundary": next_boundary,
                "timeframe": timeframe_info.normalized
            }
        )
        
    except Exception as e:
        logger.error(f"Error checking mid-cycle conditions: {e}")
        return create_error_response(
            f"Failed to check mid-cycle conditions: {str(e)}",
            is_mid_cycle=False,
            has_fresh_recommendations=False
        )


def calculate_position_sizes_for_batch(risk_manager, trade_signals: List[Dict[str, Any]], positions_data=None, orders_data=None) -> Dict[str, Any]:
    """
    Calculate position sizes for a batch of trades using existing RiskManager.
    
    This function leverages the existing RiskManager's slot-based position sizing
    to calculate appropriate position sizes for multiple trades simultaneously.
    
    Args:
        risk_manager: RiskManager instance with slot-based position sizing
        trade_signals: List of trade signal dictionaries containing:
            - symbol: Trading symbol
            - entry_price: Entry price
            - stop_loss: Stop loss price
            - take_profit: Take profit price
            - direction: Trade direction
            - confidence: Signal confidence (optional)
            
    Returns:
        Dict containing:
        - success: bool - Whether batch sizing was successful
        - position_sizes: List[Dict] - Position size results for each trade
        - total_risk_allocated: float - Total risk percentage allocated
        - available_slots: int - Number of available slots
        - error: str - Error message if any
    """
    logger = logging.getLogger(__name__)
    
    try:
        if not trade_signals:
            return create_error_response("No trade signals provided for batch sizing")
        
        # Get available slots for reporting, but don't limit processing
        # Global slot optimization in STEP 3 has already handled slot management
        # Use batch data if provided to avoid individual API calls
        available_slots = risk_manager.get_available_slots(positions_data, orders_data)
        
        # Process all signals sent to position sizing (no filtering by slots)
        signals_to_process = trade_signals
        batch_size = len(signals_to_process)
        
        logger.info(f"Processing batch of {batch_size} trades (available slots: {available_slots}) - no slot filtering applied")
        
        position_sizes = []
        total_risk_allocated = 0.0
        successful_calculations = 0
        
        for i, signal in enumerate(signals_to_process):
            try:
                # Validate required fields
                required_fields = ['symbol', 'entry_price', 'stop_loss']
                missing_fields = [field for field in required_fields if field not in signal]
                
                if missing_fields:
                    position_result = create_error_response(
                        f"Missing required fields: {missing_fields}",
                        signal_index=i,
                        symbol=signal.get('symbol', 'Unknown')
                    )
                else:
                    # Use existing RiskManager slot-based position sizing
                    position_result = risk_manager.calculate_slot_based_position_size(
                        entry_price=float(signal['entry_price']),
                        stop_loss=float(signal['stop_loss']),
                        symbol=signal['symbol'],
                        signal=signal
                    )
                    
                    # Track successful calculations and risk allocation
                    if position_result.get("success"):
                        successful_calculations += 1
                        slot_info = position_result.get("slot_info", {})
                        slot_risk = slot_info.get("risk_per_slot", 0)
                        total_risk_allocated += slot_risk
                
                # Add signal metadata to result
                position_result.update({
                    "signal_index": i,
                    "symbol": signal.get('symbol', 'Unknown'),
                    "original_signal": signal
                })
                
                position_sizes.append(position_result)
                
            except Exception as e:
                logger.error(f"Error calculating position size for signal {i} ({signal.get('symbol', 'Unknown')}): {e}")
                position_sizes.append(create_error_response(
                    f"Position sizing failed: {str(e)}",
                    signal_index=i,
                    symbol=signal.get('symbol', 'Unknown')
                ))
        
        # Calculate batch statistics
        batch_success_rate = successful_calculations / len(signals_to_process) if signals_to_process else 0
        
        logger.info(f"Batch position sizing completed: {successful_calculations}/{len(signals_to_process)} successful, "
                   f"total risk allocated: ${total_risk_allocated:.2f} USD")

        return create_success_response(
            f"Batch position sizing completed for {len(signals_to_process)} signals",
            position_sizes=position_sizes,
            total_risk_allocated=total_risk_allocated,
            available_slots=available_slots,
            batch_stats={
                "total_signals": len(trade_signals),
                "processed_signals": len(signals_to_process),
                "successful_calculations": successful_calculations,
                "success_rate": batch_success_rate,
                "skipped_signals": len(trade_signals) - batch_size if len(trade_signals) > batch_size else 0
            }
        )
        
    except Exception as e:
        logger.error(f"Error in batch position sizing: {e}")
        return create_error_response(
            f"Batch position sizing failed: {str(e)}",
            available_slots=0
        )


def create_workflow_state(timeframe: str, current_time: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Create initial workflow state using existing response helper patterns.
    
    This function creates a standardized workflow state dictionary that follows
    existing code patterns for state management and response formatting.
    
    Args:
        timeframe: Trading timeframe for the workflow
        current_time: Current time for state initialization (default: now in UTC)
        
    Returns:
        Dict containing initial workflow state:
        - workflow_id: str - Unique workflow identifier
        - timeframe: str - Trading timeframe
        - created_at: str - ISO timestamp of creation
        - status: str - Current workflow status
        - step: str - Current workflow step
        - components: Dict - Component health status
        - data: Dict - Workflow data storage
        - metrics: Dict - Workflow metrics
    """
    logger = logging.getLogger(__name__)
    
    try:
        if current_time is None:
            current_time = datetime.now(timezone.utc)
        elif current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        
        # Generate unique workflow ID using timestamp
        workflow_id = f"workflow_{int(current_time.timestamp())}_{timeframe}"
        
        # Create initial state using existing response patterns
        workflow_state = create_success_response(
            "Workflow state initialized successfully",
            workflow_id=workflow_id,
            timeframe=timeframe,
            created_at=current_time.isoformat(),
            updated_at=current_time.isoformat(),
            status="initialized",
            step="mid_cycle_check",
            components={
                "timestamp_validator": {"status": "pending"},
                "recommender": {"status": "pending"},
                "risk_manager": {"status": "pending"},
                "trader": {"status": "pending"},
                "telegram_bot": {"status": "pending"}
            },
            data={
                "mid_cycle_result": None,
                "recommendations": [],
                "position_sizes": [],
                "trade_signals": [],
                "execution_results": []
            },
            metrics={
                "total_recommendations": 0,
                "valid_recommendations": 0,
                "successful_position_sizes": 0,
                "executed_trades": 0,
                "total_risk_allocated": 0.0,
                "workflow_duration_seconds": 0.0
            },
            config={
                "max_retries": 3,
                "timeout_seconds": 300,
                "enable_telegram_notifications": True,
                "enable_intelligent_replacement": True
            }
        )
        
        logger.info(f"Created workflow state: {workflow_id} for timeframe {timeframe}")
        
        return workflow_state
        
    except Exception as e:
        logger.error(f"Error creating workflow state: {e}")
        return create_error_response(
            f"Failed to create workflow state: {str(e)}",
            workflow_id=None,
            timeframe=timeframe
        )


def update_workflow_state(workflow_state: Dict[str, Any], step: str,
                         data_updates: Optional[Dict[str, Any]] = None,
                         component_updates: Optional[Dict[str, Any]] = None,
                         metrics_updates: Optional[Dict[str, Any]] = None,
                         status: Optional[str] = None) -> Dict[str, Any]:
    """
    Update workflow state with new step, data, and component status using existing patterns.
    
    This function provides centralized state management following existing response
    helper patterns for consistent state updates throughout the workflow.
    
    Args:
        workflow_state: Current workflow state dictionary
        step: New workflow step name
        data_updates: Optional data updates to merge into workflow data
        component_updates: Optional component status updates
        metrics_updates: Optional metrics updates
        status: Optional new workflow status
        
    Returns:
        Updated workflow state dictionary
    """
    logger = logging.getLogger(__name__)
    
    try:
        if not workflow_state or workflow_state.get("status") == "error":
            return create_error_response("Invalid workflow state provided for update")
        
        current_time = datetime.now(timezone.utc)
        workflow_id = workflow_state.get("workflow_id", "unknown")
        
        # Update basic workflow properties
        workflow_state["step"] = step
        workflow_state["updated_at"] = current_time.isoformat()
        
        if status:
            workflow_state["status"] = status
        
        # Calculate workflow duration
        created_at_str = workflow_state.get("created_at")
        if created_at_str:
            try:
                created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                duration = (current_time - created_at).total_seconds()
                if "metrics" not in workflow_state:
                    workflow_state["metrics"] = {}
                workflow_state["metrics"]["workflow_duration_seconds"] = duration
            except Exception as e:
                logger.warning(f"Could not calculate workflow duration: {e}")
        
        # Update data section
        if data_updates:
            if "data" not in workflow_state:
                workflow_state["data"] = {}
            workflow_state["data"].update(data_updates)
        
        # Update component status
        if component_updates:
            if "components" not in workflow_state:
                workflow_state["components"] = {}
            workflow_state["components"].update(component_updates)
        
        # Update metrics
        if metrics_updates:
            if "metrics" not in workflow_state:
                workflow_state["metrics"] = {}
            workflow_state["metrics"].update(metrics_updates)
        
        # Update overall health based on component status
        if "components" in workflow_state:
            healthy_components = sum(1 for comp in workflow_state["components"].values()
                                   if comp.get("status") == "healthy")
            total_components = len(workflow_state["components"])
            workflow_state["overall_health"] = healthy_components == total_components
        
        logger.debug(f"Updated workflow state {workflow_id}: step={step}, status={workflow_state.get('status')}")
        
        return workflow_state
        
    except Exception as e:
        logger.error(f"Error updating workflow state: {e}")
        # Return error response but preserve original workflow_id if available
        return create_error_response(
            f"Failed to update workflow state: {str(e)}",
            workflow_id=workflow_state.get("workflow_id") if workflow_state else None,
            original_step=workflow_state.get("step") if workflow_state else None
        )


def align_timestamp_to_boundary(timestamp: datetime, timeframe: str) -> datetime:
    """
    Align timestamp to timeframe boundary for consistent chart naming.
    
    Examples:
    - 1h timeframe: 13:34 -> 13:00
    - 15m timeframe: 13:34 -> 13:30
    - 4h timeframe: 13:34 -> 12:00
    
    Args:
        timestamp: UTC datetime to align
        timeframe: Timeframe string (e.g., "1h", "15m", "4h", "1d")
        
    Returns:
        Aligned datetime at the boundary
    """
    try:
        # Parse timeframe to minutes
        timeframe_lower = timeframe.lower()
        if timeframe_lower.endswith('m'):
            minutes = int(timeframe_lower[:-1])
        elif timeframe_lower.endswith('h'):
            minutes = int(timeframe_lower[:-1]) * 60
        elif timeframe_lower.endswith('d'):
            minutes = int(timeframe_lower[:-1]) * 1440
        elif timeframe_lower.endswith('w'):
            minutes = int(timeframe_lower[:-1]) * 10080  # 7 days * 24 hours * 60 minutes
        else:
            # Default to current time if can't parse
            return timestamp
        
        # Align to boundary
        if minutes >= 1440:  # Daily or larger
            # Align to start of day
            return timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
        elif minutes >= 60:  # Hourly
            hours = minutes // 60
            aligned_hour = (timestamp.hour // hours) * hours
            return timestamp.replace(hour=aligned_hour, minute=0, second=0, microsecond=0)
        elif timeframe_lower == '1w':
            # Weekly boundary: align to Monday 00:00 UTC of the current week
            days_since_monday = timestamp.weekday()  # 0=Monday, 6=Sunday
            monday_of_week = timestamp - timedelta(days=days_since_monday)
            return monday_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        else:  # Minutes
            total_minutes = timestamp.hour * 60 + timestamp.minute
            # Align to the start of the current period
            aligned_minutes = (total_minutes // minutes) * minutes
            aligned_hour = aligned_minutes // 60
            aligned_minute = aligned_minutes % 60
            return timestamp.replace(hour=aligned_hour, minute=aligned_minute, second=0, microsecond=0)

    except Exception as e:
        print(f"⚠️ Warning: Could not align timestamp to boundary: {e}")
        return timestamp


def get_current_cycle_boundary(timeframe: str) -> datetime:
    """
    Get the current cycle boundary for a given timeframe.

    Args:
        timeframe: Timeframe string (e.g., "1h", "15m", "4h")

    Returns:
        Current boundary as UTC datetime
    """
    now = datetime.now(timezone.utc)
    return align_timestamp_to_boundary(now, timeframe)


def get_next_cycle_boundary(timeframe: str) -> datetime:
    """
    Get the next cycle boundary for a given timeframe.

    Args:
        timeframe: Timeframe string (e.g., "1h", "15m", "4h")

    Returns:
        Next boundary as UTC datetime
    """
    current = get_current_cycle_boundary(timeframe)

    # Parse timeframe to get duration
    timeframe_lower = timeframe.lower()
    if timeframe_lower.endswith('m'):
        minutes = int(timeframe_lower[:-1])
    elif timeframe_lower.endswith('h'):
        minutes = int(timeframe_lower[:-1]) * 60
    elif timeframe_lower.endswith('d'):
        minutes = int(timeframe_lower[:-1]) * 1440
    elif timeframe_lower.endswith('w'):
        minutes = int(timeframe_lower[:-1]) * 10080
    else:
        minutes = 60  # Default to 1 hour

    return current + timedelta(minutes=minutes)


def seconds_until_next_boundary(timeframe: str) -> float:
    """
    Calculate seconds until the next cycle boundary.

    Args:
        timeframe: Timeframe string (e.g., "1h", "15m", "4h")

    Returns:
        Seconds until next boundary (can be negative if past boundary)
    """
    now = datetime.now(timezone.utc)
    next_boundary = get_next_cycle_boundary(timeframe)
    delta = next_boundary - now
    return delta.total_seconds()


def extract_timestamp_from_filename(filename: str) -> Optional[str]:
    """
    Extract timestamp from chart filename for autotrader use.

    Supports both formats:
    - New: SYMBOL_TIMEFRAME_YYYYMMDD_HHMMSS.png (e.g., XRPUSDT.P_1h_20250721_130000.png)
    - Old: SYMBOL_YYYYMMDD_HHMMSS.png (e.g., 1000PEPEUSDT.P_20250721_112607.png)

    Also handles .backup files by cleaning the filename first.

    Args:
        filename: Chart filename (can include .backup extension)

    Returns:
        Timestamp string in format "YYYY-MM-DD HH:MM:SS" or None if parsing fails
    """
    try:
        # Clean filename by removing all extensions including .backup
        cleaned_name = clean_filename_for_parsing(filename)
        name_parts = cleaned_name.split('_')

        # Try new format first: [SYMBOL, TIMEFRAME, YYYYMMDD, HHMMSS]
        if len(name_parts) >= 4:
            date_part = name_parts[-2]  # YYYYMMDD
            time_part = name_parts[-1]  # HHMMSS

            # Parse date: YYYYMMDD
            if len(date_part) == 8 and len(time_part) == 6:
                year = date_part[:4]
                month = date_part[4:6]
                day = date_part[6:8]
                hour = time_part[:2]
                minute = time_part[2:4]
                second = time_part[4:6]

                return f"{year}-{month}-{day} {hour}:{minute}:{second}"

        # Try old format: [SYMBOL, YYYYMMDD, HHMMSS]
        elif len(name_parts) >= 3:
            date_part = name_parts[-2]  # YYYYMMDD
            time_part = name_parts[-1]  # HHMMSS

            # Parse date: YYYYMMDD
            if len(date_part) == 8 and len(time_part) == 6:
                year = date_part[:4]
                month = date_part[4:6]
                day = date_part[6:8]
                hour = time_part[:2]
                minute = time_part[2:4]
                second = time_part[4:6]

                return f"{year}-{month}-{day} {hour}:{minute}:{second}"

        return None

    except Exception as e:
        print(f"⚠️ Warning: Could not extract timestamp from filename {filename}: {e}")
        return None


def extract_timeframe_from_filename(filename: str) -> Optional[str]:
    """
    Extract timeframe from chart filename.
    
    Supports format: SYMBOL_TIMEFRAME_YYYYMMDD_HHMMSS.png
    Example: XRPUSDT.P_1h_20250721_130000.png
    
    Args:
        filename: Chart filename
        
    Returns:
        Timeframe string (e.g., "1h", "4h", "1d") or None if parsing fails
    """
    try:
        from pathlib import Path
        
        # Remove extension and split by underscore
        name_parts = Path(filename).stem.split('_')
        
        # Try new format first: [SYMBOL, TIMEFRAME, YYYYMMDD, HHMMSS]
        if len(name_parts) >= 4:
            timeframe = name_parts[1]  # TIMEFRAME is at index 1
            return timeframe
        
        return None
        
    except Exception as e:
        print(f"⚠️ Warning: Could not extract timeframe from filename {filename}: {e}")
def validate_file_timestamp_against_current_boundary(filename: str, timeframe: str, current_time: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Validate if a file timestamp falls within the current boundary for the given timeframe.
    
    This function ensures that only images from the current boundary are analyzed,
    preventing analysis of outdated or future chart images.
    
    Args:
        filename: Chart filename containing timestamp
        timeframe: Trading timeframe (e.g., "15m", "1h", "4h", "1d")
        current_time: Current UTC time (default: now)
        
    Returns:
        Dict containing:
        - is_valid: bool - Whether file is within current boundary
        - file_boundary: datetime - File timestamp aligned to boundary
        - current_boundary: datetime - Current time aligned to boundary
        - reason: str - Reason for validation result
    """
    try:
        # Extract timestamp from filename
        file_timestamp_str = extract_timestamp_from_filename(filename)
        if not file_timestamp_str:
            return {
                "is_valid": False,
                "file_boundary": None,
                "current_boundary": None,
                "reason": "Could not extract timestamp from filename"
            }
        
        # Parse file timestamp
        try:
            file_timestamp = datetime.strptime(file_timestamp_str, "%Y-%m-%d %H:%M:%S")
            file_timestamp = file_timestamp.replace(tzinfo=timezone.utc)
        except ValueError as e:
            return {
                "is_valid": False,
                "file_boundary": None,
                "current_boundary": None,
                "reason": f"Invalid timestamp format: {e}"
            }
        
        # Use current time or get UTC now
        if current_time is None:
            current_time = get_utc_now()
        elif current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        
        # Align both timestamps to their respective boundaries
        file_boundary = align_timestamp_to_boundary(file_timestamp, timeframe)
        current_boundary = align_timestamp_to_boundary(current_time, timeframe)
        
        # Check if they match (file is from current boundary)
        is_valid = file_boundary == current_boundary

        reason = "File timestamp matches current boundary" if is_valid else f"File boundary {file_boundary} does not match current boundary {current_boundary}"

        # Add debug logging
        logger = logging.getLogger(__name__)
        logger.info(f"🔍 BOUNDARY VALIDATION DEBUG for {Path(filename).name}:")
        logger.info(f"   File timestamp: {file_timestamp_str}")
        logger.info(f"   File boundary: {file_boundary}")
        logger.info(f"   Current boundary: {current_boundary}")
        logger.info(f"   Timeframe: {timeframe}")
        logger.info(f"   Is valid: {is_valid}")
        logger.info(f"   Reason: {reason}")

        return {
            "is_valid": is_valid,
            "file_boundary": file_boundary,
            "current_boundary": current_boundary,
            "reason": reason
        }
        
    except Exception as e:
        return {
            "is_valid": False,
            "file_boundary": None,
            "current_boundary": None,
            "reason": f"Validation failed: {e}"
        }


def get_bybit_server_time(session) -> Optional[int]:
    """
    Get current server time from Bybit using existing session.

    Args:
        session: Bybit HTTP session instance

    Returns:
        Server timestamp in milliseconds, or None if failed
    """
    logger = logging.getLogger(__name__)
    try:
        response = session.get_server_time()
        if isinstance(response, dict) and response.get("retCode") == 0:
            result = response.get("result", {})
            time_second = result.get("timeSecond")
            time_nano = result.get("timeNano")

            if time_second:
                # Use timeSecond as primary source
                server_time_ms = int(time_second) * 1000
                logger.debug(f"Server time from timeSecond: {server_time_ms}")
                return server_time_ms
            elif time_nano:
                # Fallback to timeNano if timeSecond not available
                server_time_ms = int(time_nano) // 1000000
                logger.debug(f"Server time from timeNano: {server_time_ms}")
                return server_time_ms
        else:
            # Don't log error for 403 (rate limit/geo restriction) - it's expected
            ret_code = response.get('retCode')
            if ret_code == 403 or '403' in str(response.get('retMsg', '')):
                logger.debug(f"Server time API blocked (403) - using fallback offset")
            else:
                logger.error(f"Server time API error: retCode={ret_code}, retMsg={response.get('retMsg')}")
    except Exception as e:
        # Check if it's a 403 error
        error_msg = str(e)
        if '403' in error_msg or 'rate limit' in error_msg.lower() or 'usa' in error_msg.lower():
            logger.debug(f"Server time API blocked - using fallback offset")
        else:
            logger.error(f"Failed to get Bybit server time: {e}")
    return None


def sync_server_time(session) -> bool:
    """
    Synchronize local time offset with Bybit server time.
    
    Args:
        session: Bybit HTTP session instance
        
    Returns:
        True if synchronization was successful
    """
    global _server_time_offset, _last_sync_time

    logger = logging.getLogger(__name__)
    current_time = time.time()

    # Always attempt to synchronize if called, as this function is now triggered on demand
    logger.debug("🕐 Synchronizing with Bybit server time...")

    local_time_ms = int(current_time * 1000)
    server_time_ms = None

    # Try only once to get server time (don't spam the API if it's blocked)
    try:
        server_time_ms = get_bybit_server_time(session)
    except Exception as e:
        logger.debug(f"Server time sync failed: {e}")

    if server_time_ms is not None:
        # Calculate offset (server_time - local_time)
        _server_time_offset = server_time_ms - local_time_ms
        _last_sync_time = current_time

        logger.info(f"✅ Server time sync successful. Offset: {_server_time_offset}ms")
        return True
    else:
        # If offset is still 0 (never successfully synced), use conservative fallback
        if _server_time_offset == 0:
            _server_time_offset = 0  # Use 0ms offset (assume local time is accurate)
            logger.info(f"ℹ️ Using fallback time offset: {_server_time_offset}ms (server time sync unavailable)")
        else:
            logger.debug(f"Using current offset: {_server_time_offset}ms (server time sync unavailable)")

        # Update last sync time to prevent constant retries if sync repeatedly fails
        _last_sync_time = current_time
        return False


def get_server_synchronized_timestamp(session) -> int:
    """
    Get current timestamp synchronized with Bybit server time.

    Args:
        session: Bybit HTTP session instance

    Returns:
        Server-synchronized timestamp in milliseconds
    """
    global _server_time_offset, _last_sync_time, _sync_interval

    # Generate timestamp immediately to avoid timing gaps
    local_time_ms = int(time.time() * 1000)

    # Check if sync is needed and start it in background if required
    if time.time() - _last_sync_time > _sync_interval:
        # Start sync in background thread to avoid blocking timestamp generation
        import threading
        sync_thread = threading.Thread(
            target=sync_server_time,
            args=(session,),
            daemon=True,
            name="timestamp-sync"
        )
        sync_thread.start()

    # If we have never synced and offset is 0, try a one-time sync (blocking for first time only)
    if _server_time_offset == 0 and _last_sync_time == 0:
        sync_server_time(session)

    # Apply the offset (could be 0 if sync failed, or fallback value)
    synchronized_time = local_time_ms + _server_time_offset

    # Ensure timestamp is not too far in the future or past relative to local time
    # Bybit's recv_window is typically 5000-10000ms. We should ensure our timestamp
    # is within this window, and not too far in the future or past.
    # A 1-second buffer is reasonable for future, and 5 seconds for past to account for network.
    min_allowed_time = local_time_ms - 5000 # 5 seconds in the past
    max_allowed_time = local_time_ms + 1000 # 1 second in the future

    if synchronized_time > max_allowed_time:
        # If synchronized time is too far in future, use local time with a small positive offset
        synchronized_time = local_time_ms + 100 # 100ms conservative offset
        logging.warning(f"Adjusted future synchronized time to {synchronized_time}ms (local: {local_time_ms}ms)")
    elif synchronized_time < min_allowed_time:
        # If synchronized time is too far in past, use local time with a small negative offset
        synchronized_time = local_time_ms - 100 # 100ms conservative offset
        logging.warning(f"Adjusted past synchronized time to {synchronized_time}ms (local: {local_time_ms}ms)")

    return synchronized_time # Return in milliseconds


def get_server_time_sync_status() -> Dict[str, Any]:
    """
    Get current server time synchronization status.
    
    Returns:
        Dictionary with sync status information
    """
    current_time = time.time()
    return {
        "is_synced": _last_sync_time > 0,
        "offset_ms": _server_time_offset,
        "last_sync_ago_seconds": current_time - _last_sync_time,
        "next_sync_in_seconds": max(0, _sync_interval - (current_time - _last_sync_time))
    }


def get_utc_now() -> datetime:
    """
    Get current UTC time as timezone-aware datetime.
    
    Returns:
        datetime: Current UTC time with timezone info
    """
    return datetime.now(timezone.utc)


def ensure_utc_timezone(dt: datetime) -> datetime:
    """
    Ensure datetime object has UTC timezone.
    
    Args:
        dt: datetime object (timezone-aware or naive)
        
    Returns:
        datetime: UTC timezone-aware datetime
    """
    if dt.tzinfo is None:
        # If timezone-naive, assume UTC
        return dt.replace(tzinfo=timezone.utc)
    elif dt.tzinfo != timezone.utc:
        # Convert to UTC if different timezone
        return dt.astimezone(timezone.utc)
    else:
        # Already UTC
        return dt


def calculate_sleep_until_boundary(current_time: datetime, next_boundary: datetime) -> float:
    """
    Calculate sleep duration in seconds until next boundary.
    Ensures both timestamps are UTC timezone-aware.

    Args:
        current_time: Current timestamp
        next_boundary: Next boundary timestamp

    Returns:
        float: Sleep duration in seconds (always positive, calculates to next boundary if current has passed)
    """
    # Ensure both times are UTC timezone-aware
    current_utc = ensure_utc_timezone(current_time)
    boundary_utc = ensure_utc_timezone(next_boundary)

    # Calculate sleep duration
    sleep_duration = (boundary_utc - current_utc).total_seconds()

    # If boundary has already passed, return 0 to run immediately
    # This allows mid-cycle starts to process the current cycle
    return max(0, sleep_duration)


def format_utc_time_for_display(dt: datetime, format_str: str = "%H:%M:%S") -> str:
    """
    Format UTC datetime for display.
    
    Args:
        dt: datetime object
        format_str: strftime format string
        
    Returns:
        str: Formatted time string
    """
    utc_dt = ensure_utc_timezone(dt)
    return utc_dt.strftime(format_str)


def convert_side_to_direction(side: str) -> str:
    """
    Convert exchange side format to internal direction format.
    
    Args:
        side: Exchange side ('Buy', 'Sell')
        
    Returns:
        str: Internal direction ('LONG', 'SHORT')
    """
    side_upper = side.upper()
    if side_upper in ['BUY', 'B']:
        return 'LONG'
    elif side_upper in ['SELL', 'S']:
        return 'SHORT'
    else:
        return 'NEUTRAL'


def convert_direction_to_side(direction: str) -> str:
    """
    Convert internal direction format to exchange side format.
    
    Args:
        direction: Internal direction ('LONG', 'SHORT', 'BUY', 'SELL')
        
    Returns:
        str: Exchange side ('Buy', 'Sell')
    """
    direction_upper = direction.upper()
    if direction_upper in ['LONG', 'BUY']:
        return 'Buy'
    elif direction_upper in ['SHORT', 'SELL']:
        return 'Sell'
    else:
        return 'Buy'  # Default fallback


def normalize_direction(direction: str) -> str:
    """
    Normalize direction to standard LONG/SHORT format.
    
    Args:
        direction: Direction in any format ('BUY', 'SELL', 'LONG', 'SHORT', 'Buy', 'Sell')
        
    Returns:
        str: Normalized direction ('LONG', 'SHORT')
    """
    direction_upper = direction.upper()
    if direction_upper in ['LONG', 'BUY', 'B']:
        return 'LONG'
    elif direction_upper in ['SHORT', 'SELL', 'S']:
        return 'SHORT'
    else:
        return 'NEUTRAL'


def normalize_symbol_for_bybit(symbol: str) -> str:
    """
    Normalize symbol names to Bybit's expected format.
    Moved from trader.py to utils.py for reuse across modules.

    Handles:
    - Exchange prefixes (BINANCE:BTCUSDT -> BTCUSDT)
    - Perpetual suffixes (.P, -PERP, etc.)
    - Quote currency addition (BTC -> BTCUSDT)
    - Special tokens requiring 1000 prefix (PEPE -> 1000PEPEUSDT)
    """
    if not symbol:
        return symbol

    # Convert to uppercase
    normalized = symbol.upper()

    # Remove exchange prefix if present (e.g., BINANCE:BTCUSDT -> BTCUSDT, BYBIT:SOLUSDT.P -> SOLUSDT.P)
    if ':' in normalized:
        normalized = normalized.split(':')[-1]

    # Remove common suffixes that aren't used in Bybit
    suffixes_to_remove = ['-PERP', '_PERP', 'PERP', '.D', '.P']
    suffix_removed = False
    for suffix in suffixes_to_remove:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)]
            suffix_removed = True
            break

    # After removing suffix (if any), check if it already ends with a quote currency
    quote_currencies = ['USDT', 'USDC', 'BTC', 'ETH']
    has_quote = any(normalized.endswith(quote) for quote in quote_currencies)

    # Only add USDT if no quote currency is present
    if not has_quote:
        normalized += 'USDT'

    # Handle tokens that require numeric prefixes on Bybit
    # These are low-priced tokens where Bybit uses multipliers (1000, 10000, 1000000) as the base
    # List fetched from Bybit API on 2025-12-07

    # Tokens requiring 1000000 prefix (ultra low-priced)
    tokens_needing_1000000_prefix = [
        'BABYDOGEUSDT',
        'CHEEMSUSDT',
        'MOGUSDT',
    ]

    # Tokens requiring 10000 prefix (very low-priced)
    tokens_needing_10000_prefix = [
        'ELONUSDT',
        'QUBICUSDT',
        'SATSUSDT',
    ]

    # Tokens requiring 1000 prefix (low-priced)
    tokens_needing_1000_prefix = [
        'BONKUSDT',
        'BTTUSDT',
        'CATUSDT',
        'FLOKIUSDT',
        'LUNCUSDT',
        'NEIROCTOUSDT',
        'PEPEUSDT',
        'RATSUSDT',
        'TAGUSDT',
        'TOSHIUSDT',
        'TURBOUSDT',
        'XECUSDT',
        'XUSDT',
    ]

    # Apply prefixes in order (check largest first to avoid conflicts)
    if normalized in tokens_needing_1000000_prefix and not normalized.startswith('1000000'):
        normalized = '1000000' + normalized
    elif normalized in tokens_needing_10000_prefix and not normalized.startswith('10000'):
        normalized = '10000' + normalized
    elif normalized in tokens_needing_1000_prefix and not normalized.startswith('1000'):
        normalized = '1000' + normalized

    # Remove redundant 'USD' if it appears before 'USDT' or 'USDC'
    if normalized.endswith('USDT') and normalized.endswith('USDUSDT'):
        normalized = normalized.replace('USDUSDT', 'USDT')
    elif normalized.endswith('USDC') and normalized.endswith('USDUSDC'):
        normalized = normalized.replace('USDUSDC', 'USDC')

    return normalized


def smart_format_price(value, fallback="N/A"):
    """Smart price formatting that handles both large and small decimal values.
    
    Args:
        value: The price value to format (float, int, or string)
        fallback: The fallback string to return if value is invalid
        
    Returns:
        Formatted price string with appropriate decimal precision
    """
    if value is None or value == 0:
        return fallback
    
    try:
        val = float(value)
        if val == 0:
            return fallback
        
        # For very small values (< 0.001), use 8 decimal places for precision
        if abs(val) < 0.001:
            # For values like PEPE (0.00001366), show 8 decimal places, retaining sign
            return f"{val:.8f}"
        elif abs(val) < 1:
            # For values between 0.001 and 1, show 4 decimal places, retaining sign
            return f"{val:.4f}"
        elif abs(val) < 100:
            # For values between 1 and 100, show 2 decimal places, retaining sign
            return f"{val:.2f}"
        else:
            # For large values (like BTC), show 2 decimal places, retaining sign
            return f"{val:.2f}"
    except (ValueError, TypeError):
        return fallback


def smart_format_percentage(value, fallback="N/A"):
    """Smart percentage formatting.
    
    Args:
        value: The percentage value to format (float, int, or string)
        fallback: The fallback string to return if value is invalid
        
    Returns:
        Formatted percentage string with appropriate decimal precision
    """
    if value is None:
        return fallback
    
    try:
        val = float(value)
        return f"{val:.2f}"
    except (ValueError, TypeError):
        return fallback


def normalize_symbol_for_database(symbol: str) -> str:
    """
    Normalize symbol for database storage (now uses Bybit native format).
    """
    if not symbol:
        return symbol
    
    # Use Bybit normalization as the standard (no .P suffix)
    normalized = normalize_symbol_for_bybit(symbol)
    
    # REMOVED: .P suffix addition - now uses Bybit native format
    # if not normalized.endswith('.P'):
    #     normalized += '.P'
    
    return normalized


def extract_symbol_from_filename(filename: str) -> str:
    """
    Extract symbol from filename.
    
    Consolidated function from run_bot_clean.py and cleaner.py
    
    Args:
        filename: Chart filename
        
    Returns:
        Symbol extracted from filename, or "UNKNOWN" if extraction fails
    """
    from pathlib import Path
    
    name = Path(filename).stem
    
    # Try to extract from format like "ETHUSD_2025-07-15_22-31-32"
    parts = name.split('_')
    if len(parts) >= 1:
        return parts[0].upper()
    
    return "UNKNOWN"


def parse_timeframe_to_minutes(timeframe: str) -> int:
    """
    Convert timeframe string to minutes.
    
    Consolidated function from run_bot_clean.py and recommender.py
    
    Args:
        timeframe: Timeframe string (e.g., "1h", "15m", "1d")
        
    Returns:
        Number of minutes for the timeframe
    """
    timeframe = str(timeframe).lower().strip()
    
    # Handle common formats
    if timeframe.endswith('m'):
        return int(timeframe[:-1])
    elif timeframe.endswith('min'):
        return int(timeframe[:-3])
    elif timeframe.endswith('h'):
        return int(timeframe[:-1]) * 60
    elif timeframe.endswith('hr'):
        return int(timeframe[:-2]) * 60
    elif timeframe.endswith('hour'):
        return int(timeframe[:-4]) * 60
    elif timeframe.endswith('d'):
        return int(timeframe[:-1]) * 1440
    elif timeframe.endswith('day'):
        return int(timeframe[:-3]) * 1440
    
    # Default fallback
    return 60


def calculate_openai_pricing(prompt_tokens: int, completion_tokens: int, model: str = "gpt-4o") -> dict:
    """
    Calculate OpenAI pricing based on token usage using accurate model costs.
    
    Moved from run_bot_clean.py for reuse across modules.
    Updated to use model_costs.json for accurate pricing with fallback to hardcoded values.
    
    Args:
        prompt_tokens: Number of input tokens
        completion_tokens: Number of output tokens
        model: Model name for pricing calculation
        
    Returns:
        Dictionary with cost breakdown and token usage
    """
    import json
    from pathlib import Path
    
    # Try to load model costs from JSON file
    try:
        # Get the config directory path relative to this file
        current_dir = Path(__file__).parent.parent  # trading_bot/core -> trading_bot
        model_costs_path = current_dir / "config" / "model_costs.json"
        
        if model_costs_path.exists():
            with open(model_costs_path, 'r') as f:
                model_costs = json.load(f)
            
            # Look up pricing for the specific model
            openai_costs = model_costs.get("openai", {})
            model_pricing = openai_costs.get(model, {})
            
            if model_pricing:
                # Use accurate pricing from JSON file (prices are per 1M tokens, convert to per 1K)
                INPUT_PRICE_PER_1K = model_pricing.get("input_per_1m", 2.5) / 1000  # Convert from per 1M to per 1K
                OUTPUT_PRICE_PER_1K = model_pricing.get("output_per_1m", 10.0) / 1000  # Convert from per 1M to per 1K
                pricing_source = "model_costs.json"
            else:
                # Model not found in JSON, use fallback
                raise KeyError(f"Model {model} not found in model_costs.json")
        else:
            # File doesn't exist, use fallback
            raise FileNotFoundError("model_costs.json not found")
            
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        # Fallback to hardcoded pricing (old GPT-4o pricing)
        if model == "gpt-4o":
            INPUT_PRICE_PER_1K = 0.005  # $0.005 per 1K input tokens (old pricing)
            OUTPUT_PRICE_PER_1K = 0.015  # $0.015 per 1K output tokens (old pricing)
        else:
            # Default to GPT-4o pricing for unknown models
            INPUT_PRICE_PER_1K = 0.005
            OUTPUT_PRICE_PER_1K = 0.015
        pricing_source = "fallback_hardcoded"
    
    # Calculate costs
    input_cost = (prompt_tokens / 1000) * INPUT_PRICE_PER_1K
    output_cost = (completion_tokens / 1000) * OUTPUT_PRICE_PER_1K
    total_cost = input_cost + output_cost
    
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "input_cost_usd": round(input_cost, 6),  # Increased precision for accurate costs
        "output_cost_usd": round(output_cost, 6),
        "total_cost_usd": round(total_cost, 6),
        "model": model,
        "pricing_source": pricing_source,
        "input_price_per_1k": round(INPUT_PRICE_PER_1K, 6),
        "output_price_per_1k": round(OUTPUT_PRICE_PER_1K, 6)
    }


def get_file_modification_timestamp(file_path: str) -> datetime:
    """
    Get the file modification time as datetime.
    
    Moved from run_bot_clean.py for reuse across modules.
    
    Args:
        file_path: Path to the file
        
    Returns:
        File modification time as datetime
    """
    import os
    return datetime.fromtimestamp(os.path.getmtime(file_path))


def check_system_resources() -> bool:
    """
    Check if system has sufficient resources for trading operations.
    
    Returns:
        bool: True if system has sufficient resources, False otherwise
    """
    try:
        import psutil
        import gc
        
        # Get system memory info
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        
        # Get CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Check resource thresholds
        if memory_percent > 85:
            print(f"⚠️ High memory usage detected: {memory_percent:.1f}% - attempting cleanup")
            gc.collect()
            return False
        
        if cpu_percent > 90:
            print(f"⚠️ High CPU usage detected: {cpu_percent:.1f}%")
            return False
        
        return True
        
    except ImportError:
        # psutil not available, proceed with caution
        return True
    except Exception as e:
        print(f"⚠️ Error checking system resources: {str(e)}")
        return True

# Analytics and Holding Period Utilities

def calculate_holding_period_hours(created_at, closed_at) -> float:
    """Calculate holding period in hours between two timestamps."""
    from datetime import datetime
    
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
    """Assign a holding period to the appropriate bucket."""
    TIME_BUCKETS = {
        '0-4h': (0, 4),
        '4-12h': (4, 12),
        '12-24h': (12, 24),
        '1-3d': (24, 72),
        '3-7d': (72, 168),
        '7d+': (168, float('inf'))
    }
    
    for bucket_name, (min_hours, max_hours) in TIME_BUCKETS.items():
        if min_hours <= holding_hours < max_hours:
            return bucket_name
    
    # Fallback for edge cases
    return '7d+' if holding_hours >= 168 else '0-4h'


def calculate_live_rr(entry_price: float, current_price: float, stop_loss: float, 
                     direction: str) -> float:
    """Calculate live risk/reward ratio for a position."""
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
def extract_base_coin_from_symbol(symbol: str) -> str:
    """
    Extract the base coin from a trading symbol for Bybit API calls.
    
    This function handles various symbol formats including:
    - CETUSUSDT -> CETUS
    - CETUS.PUSDT -> CETUS
    - BTCUSDT -> BTC
    - ETHUSDT -> ETH
    
    Args:
        symbol: The trading symbol (e.g., "CETUSUSDT", "CETUS.PUSDT")
        
    Returns:
        The base coin name (e.g., "CETUS", "BTC")
    """
    if not symbol:
        return ""
    
    # Convert to uppercase for consistency
    symbol = symbol.upper()
    
    # Remove common quote currencies
    quote_currencies = ["USDT", "USDC", "USD", "BTC", "ETH"]
    
    # First, try to split by dot to handle formats like "CETUS.PUSDT"
    if "." in symbol:
        base_part = symbol.split(".")[0]
    else:
        base_part = symbol
    
    # Remove quote currency suffixes
    for quote in quote_currencies:
        if base_part.endswith(quote):
            base_part = base_part[:-len(quote)]
            break
    
    return base_part


def extract_base_coin_for_historical_volatility(symbol: str) -> str:
    """
    Extract base coin specifically for historical volatility API calls.
    
    This is a specialized version that handles the specific requirements
    for Bybit's historical volatility endpoint.
    
    Args:
        symbol: The trading symbol
        
    Returns:
        Clean base coin name for historical volatility API
    """
    base = extract_base_coin_from_symbol(symbol)
    
    # Additional cleanup for historical volatility
    # Remove any remaining dots or special characters
    base = base.replace(".", "").replace("-", "")
    
    return base




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
        
    except Exception as e:
        # If recommendation_id lookup fails, try to infer from symbol
        symbol = trade_data.get('symbol')
        if symbol:
            # Attempt to extract timeframe from symbol string (e.g., "BTCUSDT_1h")
            symbol_parts = symbol.split('_')
            if len(symbol_parts) > 1:
                # Check if the last part looks like a timeframe (e.g., "1h", "4h")
                potential_timeframe = symbol_parts[-1]
                if any(tf_suffix in potential_timeframe for tf_suffix in ['m', 'h', 'd', 'w']):
                    return potential_timeframe
        
        # Fallback to a more specific unknown if symbol is available
        return f"unknown_{symbol}" if symbol else 'unknown'


def filter_recommendations_by_cycle_trades(
    recommendations: List[Dict[str, Any]],
    timeframe: str,
    current_time: datetime,
    data_agent: Any
) -> List[Dict[str, Any]]:
    """
    Filter out recommendations for symbols that already have trades placed this cycle.
    
    Args:
        recommendations: List of recommendation dictionaries.
        timeframe: The current trading timeframe (e.g., "1h", "4h").
        current_time: The current UTC time.
        data_agent: An instance of DataAgent to query for existing trades.
        
    Returns:
        A new list of recommendations with symbols that already have trades this cycle filtered out.
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Get all trades placed in the current cycle
        cycle_trades = data_agent.get_trades_for_current_cycle(timeframe, current_time)
        
        # Extract the symbols from those trades
        traded_symbols_this_cycle = {trade.get('symbol') for trade in cycle_trades if trade.get('symbol')}
        
        if not traded_symbols_this_cycle:
            logger.info("No trades found in the current cycle. All recommendations will be processed.")
            return recommendations
        
        filtered_recommendations = []
        skipped_count = 0
        
        for rec in recommendations:
            symbol = rec.get('symbol')
            if symbol and symbol in traded_symbols_this_cycle:
                logger.info(f"Skipping recommendation for {symbol} as a trade for this symbol was already placed this cycle.")
                skipped_count += 1
            else:
                filtered_recommendations.append(rec)
        
        if skipped_count > 0:
            logger.info(f"Filtered {skipped_count} recommendations due to existing trades in the current cycle.")
        
        return filtered_recommendations

    except Exception as e:
        logger.error(f"Error filtering recommendations by cycle trades: {e}")
        # In case of error, return original recommendations to avoid blocking the bot
        return recommendations


def count_open_positions_and_orders(orders: Optional[List[Dict[str, Any]]] = None, positions: Optional[List[Dict[str, Any]]] = None, trader=None) -> Dict[str, Any]:
    """
    Count open positions and entry orders with precise logic.

    This utility function implements the exact counting logic from the test suite
    to provide consistent position analysis across the entire codebase.

    Args:
        orders: Optional list of order dictionaries from get_open_orders()
        positions: Optional list of position dictionaries from get_positions()
        trader: Optional trader instance to fetch data automatically

    Returns:
        Dict containing precise counts and raw order data:
        - total_positions: Total number of positions
        - active_positions: Dict of active positions by symbol {symbol: count}
        - open_entry_orders: Dict of open entry orders by symbol {symbol: count}
        - take_profit_orders: Count of take profit orders
        - stop_loss_orders: Count of stop loss orders
        - total_size: Total size of all active positions
        - total_value: Total value of all active positions
        - active_positions_count: Total count of active positions
        - open_entry_orders_count: Total count of open entry orders
        - raw_orders: List of raw order dictionaries for cancellation
        - raw_positions: List of raw position dictionaries
    """
    logger = logging.getLogger(__name__)

    try:
        # If trader is provided and data is not, fetch it automatically
        if trader and (orders is None or positions is None):
            if positions is None:
                positions_response = trader.get_positions()
                if positions_response.get("retCode") == 0:
                    positions = positions_response.get("result", {}).get("list", [])
                else:
                    # Enhanced error logging with full response details
                    ret_code = positions_response.get('retCode', 'N/A')
                    error_msg = positions_response.get('retMsg', 'Unknown API error')
                    error_detail = positions_response.get('error', '')

                    # Log full response for debugging
                    logger.error(f"Failed to fetch positions - retCode: {ret_code}, retMsg: {error_msg}, error: {error_detail}")
                    logger.debug(f"Full API response: {positions_response}")

                    # Raise exception to trigger RiskManager fallback
                    raise Exception(f"Failed to fetch positions from API: retCode={ret_code}, retMsg={error_msg}")

        if orders is None:
            # Check if trader is available
            if trader is None:
                logger.warning("No trader instance provided and no orders data available")
                orders = []
            else:
                # Use get_open_orders() with working parameters to get active orders
                orders_response = trader.get_open_orders(
                    openOnly=0,  # Get active orders only (New, PartiallyFilled)
                    limit=50
                )
                if orders_response.get("retCode") == 0:
                    orders_data = orders_response.get("result", {})
                    orders = orders_data.get("list", [])
                else:
                    # Enhanced error logging with full response details
                    ret_code = orders_response.get('retCode', 'N/A')
                    error_msg = orders_response.get('retMsg', 'Unknown API error')
                    error_detail = orders_response.get('error', '')

                    # Log full response for debugging
                    logger.error(f"Failed to fetch orders - retCode: {ret_code}, retMsg: {error_msg}, error: {error_detail}")
                    logger.debug(f"Full API response: {orders_response}")

                    # Raise exception to trigger RiskManager fallback
                    raise Exception(f"Failed to fetch orders from API: retCode={ret_code}, retMsg={error_msg}")

        # Ensure we have data to work with
        if orders is None:
            orders = []
        if positions is None:
            positions = []

        # Initialize counters
        result = {
            "total_positions": len(positions),
            "active_positions": {},
            "open_entry_orders": {},
            "take_profit_orders": 0,
            "stop_loss_orders": 0,
            "total_size": 0.0,
            "total_value": 0.0,
            "active_positions_count": 0,
            "open_entry_orders_count": 0,
            "raw_orders": orders,  # Include raw order data for cancellation
            "raw_positions": positions  # Include raw position data
        }

        # Count active positions by symbol
        for position in positions:
            size = float(position.get("size", 0))
            if size > 0:  # Only count active positions
                symbol = position.get("symbol", "Unknown")
                result["active_positions"][symbol] = result["active_positions"].get(symbol, 0) + 1
                result["active_positions_count"] += 1

                # Calculate total size and value
                result["total_size"] += size

                # Try to calculate position value (approximate)
                try:
                    entry_price = float(position.get("avgPrice", 0))
                    if entry_price > 0:
                        result["total_value"] += size * entry_price
                except (ValueError, TypeError):
                    pass

        # Count different types of orders
        for order in orders:
            status = order.get("orderStatus", "")
            symbol = order.get("symbol", "Unknown")
            order_type = order.get("orderType", "").lower()
            stop_order_type = order.get("stopOrderType", "")

            # DEBUG: Log order details for troubleshooting
            logger.debug(f"Order analysis - Symbol: {symbol}, Status: {status}, OrderType: {order_type}, StopOrderType: {stop_order_type}")

            # Check if this is a TP/SL order (conditional orders)
            is_tp_sl_order = (
                stop_order_type or  # Has stopOrderType field
                "take" in order_type or "profit" in order_type or  # TP order
                "stop" in order_type or "loss" in order_type  # SL order
            )

            # Open entry orders - only count market/limit orders that are not TP/SL
            if (status in ["New", "PartiallyFilled", "Pending", "Active"] and
                not is_tp_sl_order and
                order_type in ["limit", "market", ""]):  # Empty orderType is typically market/limit
                result["open_entry_orders"][symbol] = result["open_entry_orders"].get(symbol, 0) + 1
                result["open_entry_orders_count"] += 1
                logger.debug(f"✅ Counted as ENTRY ORDER: {symbol} ({status}, {order_type})")

            # Count TP/SL orders separately
            elif status in ["New", "PartiallyFilled", "Untriggered"]:
                if "take" in order_type or "profit" in order_type or stop_order_type == "TakeProfit":
                    result["take_profit_orders"] += 1
                    logger.debug(f"📈 Counted as TP ORDER: {symbol} ({status}, {order_type}, {stop_order_type})")
                elif "stop" in order_type or "loss" in order_type or stop_order_type == "StopLoss":
                    result["stop_loss_orders"] += 1
                    logger.debug(f"📉 Counted as SL ORDER: {symbol} ({status}, {order_type}, {stop_order_type})")
                else:
                    logger.debug(f"❓ Unclassified order: {symbol} ({status}, {order_type}, {stop_order_type})")

        logger.info(f"Position analysis: {result['active_positions_count']} active positions, "
                   f"{result['open_entry_orders_count']} open entry orders")
        
        return result

    except Exception as e:
        logger.error(f"Error in count_open_positions_and_orders: {e}")
        # Re-raise the exception to trigger RiskManager fallback
        raise Exception(f"Failed to count positions and orders: {str(e)}")


def _is_tp_sl_order(order_details: Dict[str, Any]) -> bool:
    """
    Check if an order is a Take Profit or Stop Loss order.

    Args:
        order_details: Order details from Bybit API

    Returns:
        True if this is a TP/SL order, False if it's an entry order
    """
    stop_order_type = order_details.get("stopOrderType", "")
    order_type = order_details.get("orderType", "").lower()

    # Check for TP/SL indicators
    is_tp_sl = (
        stop_order_type in ["TakeProfit", "StopLoss"] or  # Has stopOrderType field
        "take" in order_type or "profit" in order_type or  # TP order
        "stop" in order_type or "loss" in order_type  # SL order
    )

    return is_tp_sl


def _get_order_details(trader, symbol: str, order_id: Optional[str] = None,
                      order_link_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Get order details from Bybit API to validate order type before cancellation.

    Args:
        trader: TradeExecutor instance
        symbol: Trading symbol
        order_id: Bybit order ID
        order_link_id: Client order link ID

    Returns:
        Order details dict or None if not found
    """
    try:
        # Get open orders to find our specific order
        orders_response = trader.get_open_orders(symbol=symbol, openOnly=0, limit=50)

        if orders_response.get("retCode") != 0:
            return None

        orders = orders_response.get("result", {}).get("list", [])

        # Find our specific order
        for order in orders:
            order_order_id = order.get("orderId", "")
            order_link_id_in_order = order.get("orderLinkId", "")

            # Check if this is our order
            id_match = False
            if order_id and order_order_id == order_id:
                id_match = True
            elif order_link_id and order_link_id_in_order == order_link_id:
                id_match = True

            if id_match and order.get("symbol") == symbol:
                return order

        return None

    except Exception as e:
        logging.getLogger(__name__).error(f"Error getting order details: {e}")
        return None


def cancel_order_with_verification(trader, symbol: str, order_id: Optional[str] = None,
                                 order_link_id: Optional[str] = None,
                                 max_retries: int = 3, retry_delay: float = 0.5) -> Dict[str, Any]:
    """
    Unified order cancellation function with robust verification.

    This is the SINGLE SOURCE OF TRUTH for all order cancellation in the codebase.
    It provides:
    - Validation to prevent TP/SL order cancellation
    - Attempt to cancel the order via API
    - Verify the order is actually gone by re-querying
    - Handle retries for failed cancellations
    - Handle race conditions (order filled between detection and cancellation)
    - Provide detailed logging for debugging
    - Return standardized results for consistent error handling

    Args:
        trader: TradeExecutor instance with API access
        symbol: Trading symbol (e.g., "BTCUSDT")
        order_id: Bybit order ID (optional if order_link_id provided)
        order_link_id: Client-generated order link ID (optional if order_id provided)
        max_retries: Maximum number of cancellation attempts (default: 3)
        retry_delay: Delay between retries in seconds (default: 0.5)

    Returns:
        Dict with standardized cancellation result:
        {
            "success": bool,  # True if order was successfully cancelled and verified
            "status": str,    # "cancelled", "already_processed", "failed", "error"
            "order_id": str,  # The order ID that was cancelled
            "order_link_id": str,  # The order link ID that was cancelled
            "attempts": int,  # Number of attempts made
            "verification_success": bool,  # Whether verification was successful
            "error": str,    # Error message if any
            "message": str   # Human-readable status message
        }
    """
    logger = logging.getLogger(__name__)

    # Validate input parameters
    if not symbol:
        return {
            "success": False,
            "status": "error",
            "error": "Symbol is required",
            "message": "Cannot cancel order: symbol is required"
        }

    if not order_id and not order_link_id:
        return {
            "success": False,
            "status": "error",
            "error": "Either order_id or order_link_id must be provided",
            "message": "Cannot cancel order: order identifier is required"
        }

    logger.info(f"🗑️ Starting unified order cancellation for {symbol} (ID: {order_id or order_link_id})")

    # STEP 1: Get order details to validate it's not a TP/SL order
    order_details = _get_order_details(trader, symbol, order_id, order_link_id)

    if order_details is None:
        logger.warning(f"⚠️ Order {order_id or order_link_id} not found in open orders for {symbol}")
        return {
            "success": False,
            "status": "error",
            "error": "Order not found in open orders",
            "message": f"Order {order_id or order_link_id} not found for {symbol}"
        }

    # STEP 2: Validate that this is NOT a TP/SL order
    if _is_tp_sl_order(order_details):
        stop_order_type = order_details.get("stopOrderType", "")
        order_type = order_details.get("orderType", "")
        logger.error(f"🚫 BLOCKED: Attempted to cancel TP/SL order for {symbol} (ID: {order_id or order_link_id})")
        logger.error(f"   Order details: stopOrderType={stop_order_type}, orderType={order_type}")
        return {
            "success": False,
            "status": "error",
            "error": "Cannot cancel TP/SL orders through this function",
            "order_type": "tp_sl",
            "stop_order_type": stop_order_type,
            "message": f"Blocked cancellation of TP/SL order for {symbol} (stopOrderType: {stop_order_type}, orderType: {order_type})"
        }

    # STEP 3: Log that we're cancelling an entry order
    logger.info(f"✅ VALIDATED: Cancelling ENTRY order for {symbol} (ID: {order_id or order_link_id})")
    logger.info(f"   Order details: stopOrderType={order_details.get('stopOrderType', 'N/A')}, orderType={order_details.get('orderType', 'N/A')}")

    # STEP 4: Attempt to cancel the order directly via API (single source of truth)
    try:
        logger.info(f"🔄 Attempting to cancel order for {symbol}")

        # Call Bybit API directly to avoid circular dependency
        normalized_symbol = normalize_symbol_for_bybit(symbol)

        params = {
            "category": "linear",
            "symbol": normalized_symbol
        }

        # Add order identifier
        if order_id:
            params["orderId"] = order_id
        elif order_link_id:
            params["orderLinkId"] = order_link_id

        # Call the API directly through trader's api_manager
        cancel_result = trader.api_manager.cancel_order(**params)

        # Check if cancellation API call was successful
        if cancel_result.get("retCode") == 0:
            logger.info(f"✅ API cancellation successful for {symbol}")

            # Verify the order is actually gone (with timeout)
            verification_result = _verify_order_cancelled(trader, symbol, order_id, order_link_id)

            if verification_result["verified"]:
                logger.info(f"✅ VERIFICATION SUCCESSFUL: Order {symbol} (ID: {order_id or order_link_id}) is confirmed cancelled")
                return {
                    "success": True,
                    "status": "cancelled",
                    "order_id": order_id,
                    "order_link_id": order_link_id,
                    "attempts": 1,
                    "verification_success": True,
                    "message": "Order successfully cancelled and verified"
                }
            else:
                # Order still exists - this could be a race condition
                logger.warning(f"⚠️ VERIFICATION FAILED: Order {symbol} still exists after cancellation")
                logger.warning(f"   Verification details: {verification_result['reason']}")

                # Check if this is a "too late to cancel" scenario
                if verification_result.get("order_status") in ["Filled", "Cancelled"]:
                    logger.info(f"ℹ️ Order was already processed: {symbol} status={verification_result['order_status']}")
                    return {
                        "success": True,
                        "status": "already_processed",
                        "order_id": order_id,
                        "order_link_id": order_link_id,
                        "attempts": 1,
                        "verification_success": True,
                        "message": f"Order was already {verification_result['order_status'].lower()}"
                    }
                else:
                    # Order still exists but not filled/cancelled - this is unusual
                    return {
                        "success": False,
                        "status": "failed",
                        "order_id": order_id,
                        "order_link_id": order_link_id,
                        "attempts": 1,
                        "verification_success": False,
                        "error": f"Order still exists after cancellation: {verification_result['reason']}",
                        "message": "Cancellation appeared successful but order still exists"
                    }

        else:
            # API cancellation failed
            error_msg = cancel_result.get("retMsg", "Unknown API error")
            logger.warning(f"❌ API cancellation failed for {symbol}: {error_msg}")

            # Check if this is a "too late to cancel" error
            if "too late to cancel" in error_msg.lower() or "order not exists" in error_msg.lower():
                logger.info(f"ℹ️ Order was already processed: {symbol} (API error: {error_msg})")
                return {
                    "success": True,
                    "status": "already_processed",
                    "order_id": order_id,
                    "order_link_id": order_link_id,
                    "attempts": 1,
                    "verification_success": True,
                    "message": f"Order was already processed (API error: {error_msg})"
                }
            else:
                return {
                    "success": False,
                    "status": "failed",
                    "order_id": order_id,
                    "order_link_id": order_link_id,
                    "attempts": 1,
                    "verification_success": False,
                    "error": error_msg,
                    "message": f"API cancellation failed: {error_msg}"
                }

    except Exception as e:
        logger.error(f"❌ Exception during cancellation for {symbol}: {e}")
        return {
            "success": False,
            "status": "error",
            "order_id": order_id,
            "order_link_id": order_link_id,
            "attempts": 1,
            "verification_success": False,
            "error": str(e),
            "message": f"Cancellation failed with exception: {str(e)}"
        }


def _verify_order_cancelled(trader, symbol: str, order_id: Optional[str] = None,
                          order_link_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Verify that an order has been successfully cancelled by checking if it still exists.

    Args:
        trader: TradeExecutor instance
        symbol: Trading symbol
        order_id: Bybit order ID
        order_link_id: Client order link ID

    Returns:
        Dict with verification result:
        {
            "verified": bool,      # True if order is confirmed cancelled
            "order_status": str,   # Current order status if still exists
            "reason": str         # Reason for verification result
        }
    """
    logger = logging.getLogger(__name__)

    try:
        # Get current open orders to check if our order still exists
        # Use reduced logging to avoid spam
        orders_response = trader.get_open_orders(symbol=symbol, openOnly=0, limit=50)

        if orders_response.get("retCode") != 0:
            # If we can't get orders, assume verification failed but don't block cancellation
            logger.warning(f"⚠️ Could not verify cancellation for {symbol}: API error getting orders")
            return {
                "verified": False,
                "reason": f"Could not verify: API error getting orders ({orders_response.get('retMsg', 'Unknown error')})"
            }

        orders = orders_response.get("result", {}).get("list", [])

        # Look for our specific order
        for order in orders:
            order_symbol = order.get("symbol", "")
            order_order_id = order.get("orderId", "")
            order_link_id_in_order = order.get("orderLinkId", "")
            order_status = order.get("orderStatus", "")

            # Check if this is our order
            id_match = False
            if order_id and order_order_id == order_id:
                id_match = True
            elif order_link_id and order_link_id_in_order == order_link_id:
                id_match = True

            if id_match and order_symbol == symbol:
                # Order still exists!
                logger.warning(f"⚠️ Order still exists: {symbol} (ID: {order_id or order_link_id}, Status: {order_status})")
                return {
                    "verified": False,
                    "order_status": order_status,
                    "reason": f"Order still exists with status: {order_status}"
                }

        # Order not found in open orders - it's been cancelled
        logger.debug(f"✅ Order verification successful: {symbol} (ID: {order_id or order_link_id}) not found in open orders")
        return {
            "verified": True,
            "reason": "Order not found in open orders (confirmed cancelled)"
        }

    except Exception as e:
        logger.error(f"❌ Exception during order verification for {symbol}: {e}")
        # On verification error, assume the order was cancelled to avoid blocking
        return {
            "verified": True,
            "reason": f"Verification failed with exception, assuming cancelled: {str(e)}"
        }
