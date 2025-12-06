import sqlite3
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

from .utils import generate_prompt_hash, normalize_prompt_for_hashing, extract_prompt_metadata
from .database_utils import CandleStoreDatabase

logger = logging.getLogger(__name__)

class AnalysisDataLoader:
    """Loader for analysis records from trading_bot database."""

    def __init__(self, analysis_db_path: Optional[str] = None):
        if analysis_db_path is None:
            # Default to the consolidated database in data/ folder
            import sys
            from pathlib import Path
            project_root = Path(__file__).parent.parent.parent
            analysis_db_path = str(project_root / "data" / "trading.db")

        self.analysis_db_path = analysis_db_path
        # Initialize backtest database for hash mappings
        self.backtest_db = CandleStoreDatabase()

    def get_connection(self) -> sqlite3.Connection:
        """Get connection to analysis database."""
        conn = sqlite3.connect(self.analysis_db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _parse_analysis_data(self, analysis_data_str) -> Dict[str, Any]:
        """Parse JSON analysis_data field."""
        if not analysis_data_str:
            return {}

        # If it's already a dict, return it as-is
        if isinstance(analysis_data_str, dict):
            return analysis_data_str

        # If it's a string, try to parse it as JSON
        if isinstance(analysis_data_str, str):
            try:
                return json.loads(analysis_data_str)
            except (json.JSONDecodeError, TypeError) as e:
                logger.debug(f"Failed to parse analysis_data string: {e}, data length: {len(analysis_data_str)}")
                return {}

        # For any other type, return empty dict
        logger.debug(f"Unexpected analysis_data type: {type(analysis_data_str)}, value: {analysis_data_str}")
        return {}

    def _normalize_timeframe(self, timeframe: Optional[str]) -> Optional[str]:
        """Normalize timeframe to standard format."""
        if not timeframe:
            return None

        # Handle common variations
        timeframe = timeframe.lower().strip()

        # Map variations to standard format
        mapping = {
            '1m': '1m', '1min': '1m', '1minute': '1m',
            '5m': '5m', '5min': '5m', '5minute': '5m',
            '15m': '15m', '15min': '15m', '15minute': '15m',
            '30m': '30m', '30min': '30m', '30minute': '30m',
            '1h': '1h', '1hour': '1h', '60m': '1h',
            '4h': '4h', '4hour': '4h', '240m': '4h',
            '1d': '1d', '1day': '1d', 'daily': '1d', 'd': '1d',
            '1w': '1w', '1week': '1w', 'weekly': '1w', 'w': '1w'
        }

        return mapping.get(timeframe, timeframe)

    def _is_valid_record(self, record: Dict[str, Any]) -> bool:
        """Check if record meets all filtering criteria."""
        # Must have prompt information (either prompt_version or analysis_prompt)
        analysis_data = self._parse_analysis_data(record.get('analysis_data'))

        # Debug logging for first few records
        if not hasattr(self, '_debug_count'):
            self._debug_count = 0

        if self._debug_count < 5:
            logger.debug(f"Record {record.get('id', 'unknown')}: recommendation={record.get('recommendation')}")
            logger.debug(f"  analysis_data keys: {list(analysis_data.keys()) if analysis_data else 'None'}")
            if analysis_data and 'analysis' in analysis_data:
                logger.debug(f"  analysis keys: {list(analysis_data['analysis'].keys()) if isinstance(analysis_data['analysis'], dict) else 'Not dict'}")
            self._debug_count += 1

        has_prompt_info = (
            analysis_data.get('prompt_version') or
            (analysis_data.get('analysis', {}).get('prompt_version'))
        )
        if not has_prompt_info:
            return False

        # Must have recommendation = 'buy' or 'sell'
        recommendation = record.get('recommendation', '').lower()
        if recommendation not in ['buy', 'sell']:
            return False

        # Must have valid timestamp
        if not record.get('timestamp'):
            return False

        # Must have valid prices
        try:
            entry_price = float(record.get('entry_price', 0))
            stop_loss = float(record.get('stop_loss', 0))
            take_profit = float(record.get('take_profit', 0))

            if entry_price <= 0 or stop_loss <= 0 or take_profit <= 0:
                return False

            # For buy: stop_loss < entry_price < take_profit
            # For sell: take_profit < entry_price < stop_loss
            if recommendation == 'buy':
                if not (stop_loss < entry_price < take_profit):
                    return False
            elif recommendation == 'sell':
                if not (take_profit < entry_price < stop_loss):
                    return False

        except (ValueError, TypeError):
            return False

        # Must have symbol
        if not record.get('symbol'):
            return False

        # Must have normalized timeframe
        normalized_tf = self._normalize_timeframe(record.get('timeframe') or record.get('normalized_timeframe'))
        if not normalized_tf:
            return False

        return True

    def _is_valid_record_for_prompt_hash(self, record: Dict[str, Any]) -> bool:
        """Check if record is valid for prompt hash analysis (uses dedicated analysis_prompt column)."""
        # Must have analysis_prompt from dedicated column
        analysis_prompt = record.get('analysis_prompt')
        if not analysis_prompt or not analysis_prompt.strip():
            return False

        # Generate and store hash mapping
        prompt_hash = generate_prompt_hash(analysis_prompt)
        record['prompt_hash'] = prompt_hash

        # Store hash mapping in database (only if not already exists)
        # Store the normalized prompt (with dynamic data removed) for cleaner representation
        existing_text = self.backtest_db.get_prompt_text_by_hash(prompt_hash)
        if existing_text is None:
            normalized_prompt = normalize_prompt_for_hashing(analysis_prompt)
            # Extract metadata from original prompt for analysis
            metadata = extract_prompt_metadata(analysis_prompt)
            self.backtest_db.store_prompt_hash_mapping(
                prompt_hash,
                normalized_prompt,
                metadata.get('timeframe'),
                metadata.get('symbol')
            )

        return True

    def load_filtered_records(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Load and filter analysis records."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Query records with prompt_version AND buy/sell recommendation
            query = """
                SELECT * FROM analysis_results
                WHERE json_extract(analysis_data, '$.analysis.prompt_version') IS NOT NULL
                AND recommendation IN ('buy', 'sell')
                ORDER BY rowid
            """
            if limit:
                query += f" LIMIT {limit}"

            cursor.execute(query)
            rows = cursor.fetchall()

            cursor.execute(query)
            rows = cursor.fetchall()

            filtered_records = []
            for row in rows:
                record = dict(row)

                # Parse analysis_data
                record['analysis_data'] = self._parse_analysis_data(record.get('analysis_data'))

                # Normalize timeframe
                record['normalized_timeframe'] = self._normalize_timeframe(
                    record.get('timeframe') or record.get('normalized_timeframe')
                )

                # Apply filters
                if self._is_valid_record(record):
                    filtered_records.append(record)

            logger.info(f"Loaded {len(filtered_records)} filtered analysis records from {len(rows)} total")
            return filtered_records

    def load_filtered_records_for_prompt_hash(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Load and filter analysis records for prompt hash analysis (uses dedicated analysis_prompt column)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Query records with analysis_prompt from dedicated column
            query = """
                SELECT * FROM analysis_results
                WHERE analysis_prompt IS NOT NULL
                AND analysis_prompt != ''
                AND recommendation IN ('buy', 'sell')
                ORDER BY rowid
            """
            if limit:
                query += f" LIMIT {limit}"

            cursor.execute(query)
            rows = cursor.fetchall()

            filtered_records = []
            for row in rows:
                record = dict(row)

                # Parse analysis_data (still needed for other fields)
                record['analysis_data'] = self._parse_analysis_data(record.get('analysis_data'))

                # Normalize timeframe
                record['normalized_timeframe'] = self._normalize_timeframe(
                    record.get('timeframe') or record.get('normalized_timeframe')
                )

                # Apply prompt hash specific filters
                if self._is_valid_record_for_prompt_hash(record):
                    filtered_records.append(record)

            logger.info(f"Loaded {len(filtered_records)} filtered analysis records for prompt hash from {len(rows)} total")
            return filtered_records

    def group_records_by_symbol_timeframe(self, records: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group records by (symbol, normalized_timeframe) combination."""
        groups = {}

        for record in records:
            symbol = record['symbol']
            timeframe = record['normalized_timeframe']
            key = f"{symbol}_{timeframe}"

            if key not in groups:
                groups[key] = []
            groups[key].append(record)

        # Sort each group by timestamp ascending
        for key in groups:
            groups[key].sort(key=lambda x: x['timestamp'])

        logger.info(f"Grouped records into {len(groups)} symbol/timeframe combinations")
        return groups

    def get_earliest_timestamp_in_group(self, group: List[Dict[str, Any]]) -> Optional[int]:
        """Get earliest timestamp in a group of records."""
        if not group:
            return None

        timestamps = []
        for record in group:
            timestamp = record.get('timestamp')
            if isinstance(timestamp, str):
                # Parse ISO string to timestamp
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    timestamps.append(int(dt.timestamp() * 1000))
                except ValueError:
                    continue
            elif isinstance(timestamp, (int, float)):
                timestamps.append(int(timestamp))

        return min(timestamps) if timestamps else None