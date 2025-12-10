"""Cleaner module for managing outdated chart files - moves old images to backup folder."""
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

from trading_bot.core.timestamp_validator import TimestampValidator
from trading_bot.core.utils import (
    extract_timestamp_from_filename,
    extract_timeframe_from_filename,
    extract_symbol_from_filename,
    align_timestamp_to_boundary
)
from trading_bot.db.client import get_connection, execute
from trading_bot.core.storage import move_file, get_storage_type, list_files


class ChartCleaner:
    """Manages cleanup of outdated chart files based on age and cycle boundaries."""

    def __init__(
        self,
        enable_backup: bool = True,
        enable_age_based_cleaning: bool = True,
        max_file_age_hours: int = 24,
        enable_cycle_based_cleaning: bool = True,
        db_connection=None
    ):
        self.logger = logging.getLogger(__name__)
        self.timestamp_validator = TimestampValidator()
        self.enable_backup = enable_backup
        self.enable_age_based_cleaning = enable_age_based_cleaning
        self.max_file_age_hours = max_file_age_hours
        self.enable_cycle_based_cleaning = enable_cycle_based_cleaning
        self._db = db_connection
        
    def is_file_outdated(self, file_path: str, file_timestamp: datetime, timeframe: str, current_time: datetime) -> tuple[bool, str]:
        """
        Check if file is outdated based on cycle boundaries.
        A file is outdated ONLY if:
        1. It's from a PREVIOUS cycle (older than current boundary) AND
        2. It's older than max_file_age_hours

        Files from the current cycle are ALWAYS kept, even if they're old.
        Files without valid boundary-aligned timestamps are preserved.

        Returns (is_outdated, reason)
        """
        reasons = []

        # Cycle-based check (primary method)
        if self.enable_cycle_based_cleaning:
            try:
                # Get current cycle boundary for this timeframe
                current_cycle_boundary = align_timestamp_to_boundary(current_time, timeframe)

                # Get the file's cycle boundary
                file_cycle_boundary = align_timestamp_to_boundary(file_timestamp, timeframe)

                # File is outdated ONLY if it's from a PREVIOUS cycle (strictly older)
                # Files from current cycle are always kept
                if file_cycle_boundary < current_cycle_boundary:
                    reasons.append(f"previous_cycle (file: {file_cycle_boundary.strftime('%Y-%m-%d %H:%M')}, current: {current_cycle_boundary.strftime('%Y-%m-%d %H:%M')})")
                else:
                    # File is from current cycle or future - keep it regardless of age
                    return (False, "")
            except Exception as e:
                self.logger.warning(f"Cycle check failed: {e}")
                # If we can't parse the boundary, preserve the file
                return (False, "")

        # Age-based check (secondary/fallback method) - only for files from previous cycles
        if self.enable_age_based_cleaning and reasons:
            age_hours = (current_time - file_timestamp).total_seconds() / 3600
            if age_hours > self.max_file_age_hours:
                reasons.append(f"age ({age_hours:.1f}h > {self.max_file_age_hours}h)")
            else:
                # File is from previous cycle but still within age limit - keep it
                return (False, "")

        return (len(reasons) > 0, ", ".join(reasons) if reasons else "")

    def scan_files(self, folder_path: str) -> List[Dict[str, Any]]:
        """Scan folder for chart files and check their status (respects STORAGE_TYPE)."""
        current_time = datetime.now(timezone.utc)
        storage_type = get_storage_type()

        # Get list of files based on storage type
        if storage_type == 'local':
            # Scan local filesystem
            folder = Path(folder_path)
            if not folder.exists():
                self.logger.warning(f"Folder does not exist: {folder_path}")
                return []

            image_extensions = {'.png', '.jpg', '.jpeg'}
            filenames = [f.name for f in folder.iterdir() if f.is_file() and f.suffix.lower() in image_extensions]
            self.logger.info(f"📂 Found {len(filenames)} image files in {folder_path} (local)")
        else:
            # Scan cloud storage (Supabase S3)
            # Files are stored under 'charts/' prefix in the bucket
            filenames = list_files('charts')  # List files in charts/ folder
            # Filter for image files
            image_extensions = {'.png', '.jpg', '.jpeg'}
            filenames = [f for f in filenames if any(f.lower().endswith(ext) for ext in image_extensions)]
            self.logger.info(f"📂 Found {len(filenames)} image files in bucket (cloud)")

        results = []
        for filename in filenames:
            try:
                symbol = extract_symbol_from_filename(filename)
                timeframe = extract_timeframe_from_filename(filename)
                timestamp_str = extract_timestamp_from_filename(filename)

                if not timeframe or not timestamp_str:
                    continue

                file_timestamp = self.timestamp_validator.parse_timestamp(timestamp_str)
                age_minutes = int((current_time - file_timestamp).total_seconds() / 60)

                # For cloud storage, file_path includes the charts/ prefix
                # For local storage, it's the full path
                file_path = str(Path(folder_path) / filename) if storage_type == 'local' else f'charts/{filename}'

                is_outdated, reason = self.is_file_outdated(file_path, file_timestamp, timeframe, current_time)

                results.append({
                    'file_path': file_path,
                    'filename': filename,
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'timestamp': file_timestamp,
                    'age_minutes': age_minutes,
                    'is_outdated': is_outdated,
                    'reason': reason
                })
            except Exception as e:
                self.logger.debug(f"Skipping {filename}: {e}")

        return results

    def clean_outdated_files(self, folder_path: str, dry_run: bool = True, cycle_id: Optional[str] = None) -> List[str]:
        """Clean outdated files by moving them to .backup folder (respects STORAGE_TYPE)."""
        storage_type = get_storage_type()
        self.logger.info(f"🧹 Starting cleanup for: {folder_path} (dry_run={dry_run}, storage={storage_type})")

        scan_results = self.scan_files(folder_path)
        outdated = [r for r in scan_results if r['is_outdated']]

        self.logger.info(f"📊 Found {len(outdated)}/{len(scan_results)} outdated files")

        if not outdated:
            return []

        moved_files = []
        moved_details = []

        # Create backup directory based on storage type
        if not dry_run and self.enable_backup and storage_type == 'local':
            backup_dir = Path(folder_path) / '.backup'
            backup_dir.mkdir(exist_ok=True)

        for item in outdated:
            file_path = item['file_path']
            filename = item['filename']

            try:
                if dry_run:
                    self.logger.info(f"🔍 DRY RUN: Would move {filename} ({item['reason']})")
                else:
                    # Move file using storage abstraction
                    if storage_type == 'local':
                        # Local filesystem move
                        src_path = Path(file_path)
                        backup_dir = src_path.parent / '.backup'
                        backup_dir.mkdir(exist_ok=True)
                        dest_path = backup_dir / filename
                        src_path.rename(dest_path)
                        self.logger.info(f"📦 Moved: {filename} → .backup/ (local)")
                    else:
                        # Cloud storage move (S3/Supabase)
                        # file_path already includes 'charts/' prefix
                        rel_source = file_path
                        rel_dest = f"charts/.backup/{filename}"
                        result = move_file(rel_source, rel_dest)
                        if not result['success']:
                            raise Exception(result.get('error', 'Move failed'))
                        self.logger.info(f"📦 Moved: {filename} → charts/.backup/ (cloud)")

                moved_files.append(file_path)
                moved_details.append({
                    'filename': filename,
                    'symbol': item.get('symbol'),
                    'timeframe': item.get('timeframe'),
                    'reason': item.get('reason'),
                    'age_minutes': item.get('age_minutes')
                })
            except Exception as e:
                self.logger.error(f"Failed to move {filename}: {e}")

        # Log to database audit trail
        if not dry_run and moved_files:
            self._log_cleanup_action(
                folder_path=folder_path,
                files_moved=len(moved_files),
                total_scanned=len(scan_results),
                details=moved_details,
                cycle_id=cycle_id
            )

        self.logger.info(f"✅ Cleanup complete: {len(moved_files)} files {'would be ' if dry_run else ''}moved")
        return moved_files

    def _log_cleanup_action(self, folder_path: str, files_moved: int, total_scanned: int, details: List[Dict], cycle_id: Optional[str] = None):
        """Log cleanup action to database for audit trail."""
        try:
            db = self._db or get_connection()
            cleanup_id = str(uuid.uuid4())[:8]

            # Ensure bot_actions table exists
            execute(db, """
                CREATE TABLE IF NOT EXISTS bot_actions (
                    id TEXT PRIMARY KEY,
                    cycle_id TEXT,
                    action_type TEXT NOT NULL,
                    action_data TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)

            action_data = {
                'folder_path': folder_path,
                'files_moved': files_moved,
                'total_scanned': total_scanned,
                'files': details,
                'config': {
                    'enable_age_based': self.enable_age_based_cleaning,
                    'max_age_hours': self.max_file_age_hours,
                    'enable_cycle_based': self.enable_cycle_based_cleaning
                }
            }

            execute(db, """
                INSERT INTO bot_actions (id, cycle_id, action_type, action_data)
                VALUES (?, ?, 'chart_cleanup', ?)
            """, (cleanup_id, cycle_id, json.dumps(action_data)))
            db.commit()

            self.logger.info(f"📝 Cleanup logged to audit trail (id={cleanup_id})")

        except Exception as e:
            self.logger.warning(f"Failed to log cleanup action: {e}")

    def get_summary(self, folder_path: str) -> Dict[str, Any]:
        """Get cleanup summary without making changes."""
        results = self.scan_files(folder_path)
        outdated = [r for r in results if r['is_outdated']]
        
        return {
            'total_files': len(results),
            'outdated_count': len(outdated),
            'current_count': len(results) - len(outdated),
            'outdated_files': [r['filename'] for r in outdated],
            'details': results
        }

