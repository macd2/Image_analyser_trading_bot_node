"""Core file validation module for trading bot chart files."""
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from PIL import Image
from trading_bot.db.client import get_connection, query_one


class FileValidator:
    """Core validation module for file integrity, naming patterns, and database consistency."""
    
    def __init__(self, enable_backup: bool = False):
        self.logger = logging.getLogger(__name__)
        self.enable_backup = enable_backup
        
        # File naming patterns
        self.new_pattern = re.compile(r'^([A-Z0-9]+(?:\.P)?(?:USDT|USD|PERP)?)_([0-9]+[mhd])_(\d{8})_(\d{6})\.(png|jpg|jpeg)$')
        self.legacy_pattern = re.compile(r'^([A-Z0-9]+(?:\.P)?(?:USDT|USD|PERP)?)_(\d{8})_(\d{6})\.(png|jpg|jpeg)$')
        
        # Symbol validation patterns
        self.spot_pattern = re.compile(r'^[A-Z0-9]+USDT?$')
        self.perpetual_pattern = re.compile(r'^[A-Z0-9]+\.P$')
        self.futures_pattern = re.compile(r'^[A-Z0-9]+USDT?PERP$')
        
        # File size limits (in bytes)
        self.min_file_size = 1024  # 1KB minimum
        self.max_file_size = 10 * 1024 * 1024  # 10MB maximum
        
    def validate_file_integrity(self, file_path: str) -> Dict[str, Any]:
        """
        Validate file integrity including size, format, and corruption checks.
        
        Returns:
            Dict with validation results including is_valid, errors, and file_info
        """
        result = {
            "is_valid": True,
            "errors": [],
            "warnings": [],
            "file_info": {}
        }
        
        try:
            file_path_obj = Path(file_path)
            
            # Check if file exists
            if not file_path_obj.exists():
                result["is_valid"] = False
                result["errors"].append(f"File does not exist: {file_path}")
                return result
            
            # Check file size
            file_size = file_path_obj.stat().st_size
            result["file_info"]["size_bytes"] = file_size
            
            if file_size < self.min_file_size:
                result["is_valid"] = False
                result["errors"].append(f"File too small ({file_size} bytes, minimum {self.min_file_size})")
            
            if file_size > self.max_file_size:
                result["is_valid"] = False
                result["errors"].append(f"File too large ({file_size} bytes, maximum {self.max_file_size})")
            
            # Check file extension
            extension = file_path_obj.suffix.lower()
            if extension not in ['.png', '.jpg', '.jpeg']:
                result["is_valid"] = False
                result["errors"].append(f"Invalid file extension: {extension}")
                return result
            
            result["file_info"]["extension"] = extension

            # Try to open and validate image
            try:
                from trading_bot.core.storage import read_file
                import io

                # Read image from storage (supports both local and Supabase)
                image_data = read_file(file_path)
                if image_data is None:
                    result["is_valid"] = False
                    result["errors"].append(f"Image not found in storage: {file_path}")
                    return result

                with Image.open(io.BytesIO(image_data)) as img:
                    result["file_info"]["format"] = img.format
                    result["file_info"]["size"] = img.size
                    result["file_info"]["mode"] = img.mode

                    # Basic corruption check - try to load image data
                    img.load()

            except Exception as e:
                result["is_valid"] = False
                result["errors"].append(f"Image corruption or invalid format: {str(e)}")
            
            # Check file permissions
            if not os.access(file_path, os.R_OK):
                result["warnings"].append("File is not readable")
            
        except Exception as e:
            result["is_valid"] = False
            result["errors"].append(f"Unexpected error during file validation: {str(e)}")
        
        return result
    
    def validate_symbol_format(self, symbol: str) -> Dict[str, Any]:
        """
        Validate symbol format for spot, perpetual, and futures contracts.
        
        Returns:
            Dict with validation results and symbol type
        """
        result = {
            "is_valid": True,
            "symbol_type": None,
            "normalized_symbol": symbol.upper(),
            "errors": []
        }
        
        symbol_upper = symbol.upper()
        
        # Check for perpetual contracts
        if self.perpetual_pattern.match(symbol_upper):
            result["symbol_type"] = "perpetual"
        # Check for futures contracts
        elif self.futures_pattern.match(symbol_upper):
            result["symbol_type"] = "futures"
        # Check for spot contracts
        elif self.spot_pattern.match(symbol_upper):
            result["symbol_type"] = "spot"
        else:
            result["is_valid"] = False
            result["errors"].append(f"Invalid symbol format: {symbol}")
        
        return result
    
    def parse_filename(self, filename: str) -> Dict[str, Any]:
        """
        Parse filename and extract components with flexible timeframe handling.
        
        Returns:
            Dict with parsed components or validation errors
        """
        result = {
            "is_valid": True,
            "pattern_type": None,
            "symbol": None,
            "timeframe": None,
            "date": None,
            "time": None,
            "extension": None,
            "errors": []
        }
        
        filename_only = Path(filename).name
        
        # Try new pattern first (with timeframe)
        match = self.new_pattern.match(filename_only)
        if match:
            result["pattern_type"] = "new"
            result["symbol"] = match.group(1)
            result["timeframe"] = match.group(2)
            result["date"] = match.group(3)
            result["time"] = match.group(4)
            result["extension"] = match.group(5)
            return result
        
        # Try legacy pattern (without timeframe)
        match = self.legacy_pattern.match(filename_only)
        if match:
            result["pattern_type"] = "legacy"
            result["symbol"] = match.group(1)
            result["timeframe"] = None  # Will need to be inferred
            result["date"] = match.group(2)
            result["time"] = match.group(3)
            result["extension"] = match.group(4)
            return result
        
        # No pattern matched
        result["is_valid"] = False
        result["errors"].append(f"Filename does not match any known pattern: {filename_only}")
        
        return result
    
    def infer_timeframe_from_database(self, file_path: str, db_path: Optional[str] = None) -> Optional[str]:
        """
        Infer timeframe from database records for legacy files.
        
        Returns:
            Timeframe string if found, None otherwise
        """
        try:
            conn = get_connection()

            # Try exact path match first
            row = query_one(conn, '''
                SELECT timeframe FROM analysis_results
                WHERE image_path = ?
                ORDER BY timestamp DESC LIMIT 1
            ''', (file_path,))

            if row:
                # UnifiedRow supports both index and key access
                timeframe = row['timeframe']
                if timeframe:
                    conn.close()
                    return timeframe

            # Try filename match if exact path fails
            filename = Path(file_path).name
            row = query_one(conn, '''
                SELECT timeframe FROM analysis_results
                WHERE image_path LIKE ?
                ORDER BY timestamp DESC LIMIT 1
            ''', (f'%{filename}',))

            conn.close()

            if row:
                # UnifiedRow supports both index and key access
                return row['timeframe']

            return None

        except Exception as e:
            self.logger.error(f"Error inferring timeframe from database: {e}")
            return None
    
    def validate_filename_pattern(self, filename: str, require_timeframe: bool = False) -> Dict[str, Any]:
        """
        Validate filename pattern with flexible timeframe handling.
        
        Args:
            filename: The filename to validate
            require_timeframe: Whether timeframe is required in filename
            
        Returns:
            Dict with validation results
        """
        result = self.parse_filename(filename)
        
        if not result["is_valid"]:
            return result
        
        # Validate symbol format
        if result["symbol"]:
            symbol_validation = self.validate_symbol_format(result["symbol"])
            if not symbol_validation["is_valid"]:
                result["is_valid"] = False
                result["errors"].extend(symbol_validation["errors"])
        
        # Check timeframe requirement
        if require_timeframe and not result["timeframe"]:
            result["is_valid"] = False
            result["errors"].append("Timeframe is required but not found in filename")
        
        # Validate date format
        if result["date"]:
            try:
                datetime.strptime(result["date"], "%Y%m%d")
            except ValueError:
                result["is_valid"] = False
                result["errors"].append(f"Invalid date format: {result['date']}")
        
        # Validate time format
        if result["time"]:
            try:
                datetime.strptime(result["time"], "%H%M%S")
            except ValueError:
                result["is_valid"] = False
                result["errors"].append(f"Invalid time format: {result['time']}")
        
        return result
    
    def safe_file_operation(self, operation: str, file_path: str, **kwargs) -> Dict[str, Any]:
        """
        Perform safe file operations with rollback capabilities.
        
        Args:
            operation: Type of operation ('move', 'copy', 'delete')
            file_path: Source file path
            **kwargs: Additional arguments (e.g., destination for move/copy)
            
        Returns:
            Dict with operation results
        """
        result = {
            "success": False,
            "operation": operation,
            "file_path": file_path,
            "backup_path": None,
            "error": None
        }
        
        try:
            file_path_obj = Path(file_path)
            
            # Validate file exists
            if not file_path_obj.exists():
                result["error"] = f"Source file does not exist: {file_path}"
                return result
            
            # Create backup for destructive operations (only if enabled)
            if operation in ['move', 'delete'] and self.enable_backup:
                backup_dir = file_path_obj.parent / '.backup'
                backup_dir.mkdir(exist_ok=True)
                backup_path = backup_dir / f"{file_path_obj.name}.backup"
                
                import shutil
                shutil.copy2(file_path, backup_path)
                result["backup_path"] = str(backup_path)
            
            # Perform operation
            if operation == 'move':
                destination = kwargs.get('destination')
                if not destination:
                    result["error"] = "Destination required for move operation"
                    return result
                
                import shutil
                shutil.move(file_path, destination)
                result["destination"] = destination
                
            elif operation == 'copy':
                destination = kwargs.get('destination')
                if not destination:
                    result["error"] = "Destination required for copy operation"
                    return result
                
                import shutil
                shutil.copy2(file_path, destination)
                result["destination"] = destination
                
            elif operation == 'delete':
                # Check if this is a chart file (in data/charts directory)
                # If so, use centralized storage layer
                file_path_obj = Path(file_path)
                if 'charts' in file_path_obj.parts:
                    from trading_bot.core.storage import delete_file, get_storage_type

                    # Extract filename for storage layer
                    filename = file_path_obj.name
                    storage_result = delete_file(filename)

                    if not storage_result.get('success'):
                        raise Exception(storage_result.get('error', 'Delete failed'))
                else:
                    # For non-chart files, use direct file system operation
                    os.remove(file_path)
            
            else:
                result["error"] = f"Unknown operation: {operation}"
                return result
            
            result["success"] = True
            
        except Exception as e:
            result["error"] = f"Operation failed: {str(e)}"
            
            # Attempt rollback if backup exists
            if result["backup_path"] and Path(result["backup_path"]).exists():
                try:
                    import shutil
                    shutil.move(result["backup_path"], file_path)
                    self.logger.info(f"Rollback successful for {file_path}")
                except Exception as rollback_e:
                    self.logger.error(f"Rollback failed for {file_path}: {rollback_e}")
        
        return result
    
    def get_file_database_status(self, file_path: str, db_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Check if file exists in database and get its status.
        
        Returns:
            Dict with database status information
        """
        result = {
            "exists_in_db": False,
            "record_count": 0,
            "latest_timestamp": None,
            "timeframe": None,
            "symbol": None
        }

        try:
            conn = get_connection()

            # Check for exact path match
            row = query_one(conn, '''
                SELECT COUNT(*) as count, MAX(timestamp) as max_ts, timeframe, symbol
                FROM analysis_results
                WHERE image_path = ?
            ''', (file_path,))

            # UnifiedRow supports both index and key access
            if row and row['count'] > 0:
                result["exists_in_db"] = True
                result["record_count"] = row['count']
                result["latest_timestamp"] = row['max_ts']
                result["timeframe"] = row['timeframe']
                result["symbol"] = row['symbol']
            else:
                # Try filename match
                filename = Path(file_path).name
                row = query_one(conn, '''
                    SELECT COUNT(*) as count, MAX(timestamp) as max_ts, timeframe, symbol
                    FROM analysis_results
                    WHERE image_path LIKE ?
                ''', (f'%{filename}',))

                # UnifiedRow supports both index and key access
                if row and row['count'] > 0:
                    result["exists_in_db"] = True
                    result["record_count"] = row['count']
                    result["latest_timestamp"] = row['max_ts']
                    result["timeframe"] = row['timeframe']
                    result["symbol"] = row['symbol']

            conn.close()

        except Exception as e:
            self.logger.error(f"Error checking database status: {e}")

        return result