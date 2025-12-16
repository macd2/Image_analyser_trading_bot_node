"""
Stop Loss Adjuster Service - Adjusts SL prices before trade execution.

Applies configurable percentage-based SL widening to recommendations
before they are executed as trades. Records all adjustments for audit trail
and trade reproducibility.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple

from trading_bot.db.client import execute, get_connection, release_connection

logger = logging.getLogger(__name__)


class StopLossAdjuster:
    """
    Adjusts stop loss prices before trade execution.
    
    Records all adjustments to sl_adjustments table for full audit trail
    and trade reproducibility.
    """

    def __init__(self):
        """
        Initialize adjuster.
        Database connections are obtained fresh for each operation to avoid
        connection pool exhaustion in multi-threaded/async environments.
        """
        pass

    def adjust_recommendation(
        self,
        recommendation: Dict[str, Any],
        instance_settings: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        """
        Apply SL adjustment to recommendation if configured.

        Args:
            recommendation: Recommendation dict with entry_price, stop_loss, take_profit
            instance_settings: Instance settings dict with sl_adjustment config

        Returns:
            Tuple of (adjusted_recommendation, adjustment_record)
            - adjusted_recommendation: Recommendation with adjusted SL (or original if no adjustment)
            - adjustment_record: Dict with adjustment details (or None if no adjustment)
        """
        # Check if adjustment enabled
        # Support both old nested format and new flat config format
        sl_enabled = instance_settings.get('sl_adjustment', {}).get('enabled', False)
        if not sl_enabled:
            # Try new flat config format
            sl_enabled = instance_settings.get('trading.sl_adjustment_enabled', False)
            if isinstance(sl_enabled, str):
                sl_enabled = sl_enabled.lower() == 'true'

        if not sl_enabled:
            return recommendation, None

        # Get adjustment percentage based on direction
        direction = recommendation.get('recommendation', '').upper()
        if direction not in ('LONG', 'SHORT', 'BUY', 'SELL'):
            return recommendation, None

        # Normalize direction
        is_long = direction in ('LONG', 'BUY')

        # Support both old nested format and new flat config format
        if 'sl_adjustment' in instance_settings:
            # Old format
            adjustment_pct = instance_settings['sl_adjustment'].get(
                'long_adjustment' if is_long else 'short_adjustment',
                0
            )
        else:
            # New flat config format
            key = 'trading.sl_adjustment_long_pct' if is_long else 'trading.sl_adjustment_short_pct'
            adjustment_pct = instance_settings.get(key, 0)
            if isinstance(adjustment_pct, str):
                adjustment_pct = float(adjustment_pct)

        if adjustment_pct <= 0:
            return recommendation, None

        # Get values
        entry = recommendation.get('entry_price')
        original_sl = recommendation.get('stop_loss')

        if not entry or not original_sl:
            return recommendation, None

        # Calculate adjusted SL
        risk = abs(entry - original_sl)
        
        if is_long:
            # For longs, SL is below entry - widen means move DOWN
            adjusted_sl = original_sl - (risk * adjustment_pct / 100)
        else:
            # For shorts, SL is above entry - widen means move UP
            adjusted_sl = original_sl + (risk * adjustment_pct / 100)

        # Create adjustment record
        adjustment_record = {
            'id': str(uuid.uuid4())[:8],
            'recommendation_id': recommendation.get('recommendation_id'),
            'original_stop_loss': original_sl,
            'adjusted_stop_loss': adjusted_sl,
            'adjustment_type': 'percentage',
            'adjustment_value': adjustment_pct,
            'reason': 'config_adjustment',
        }

        # Record to database
        self._record_adjustment(adjustment_record)

        # Return adjusted recommendation
        adjusted_rec = recommendation.copy()
        adjusted_rec['stop_loss'] = adjusted_sl
        adjusted_rec['adjustment_applied'] = True
        adjusted_rec['adjustment_id'] = adjustment_record['id']

        logger.info(
            f"[{recommendation.get('symbol')}] 📊 SL Adjusted: "
            f"{original_sl:.4f} → {adjusted_sl:.4f} ({adjustment_pct}% wider)"
        )

        return adjusted_rec, adjustment_record

    def _record_adjustment(self, record: Dict[str, Any]) -> None:
        """Record adjustment to sl_adjustments table."""
        conn = None
        try:
            # Get fresh connection for this operation
            conn = get_connection()
            timestamp = datetime.now(timezone.utc).isoformat()

            execute(conn, """
                INSERT INTO sl_adjustments
                (id, recommendation_id, original_stop_loss, adjusted_stop_loss,
                 adjustment_type, adjustment_value, reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record['id'],
                record['recommendation_id'],
                record['original_stop_loss'],
                record['adjusted_stop_loss'],
                record['adjustment_type'],
                record['adjustment_value'],
                record['reason'],
                timestamp,
            ))

        except Exception as e:
            logger.error(f"Failed to record SL adjustment: {e}")
        finally:
            if conn:
                release_connection(conn)

