"""
Centralized timestamp validation utility for trading bot.

This module provides comprehensive timestamp validation functionality including:
- Validation of recommendation timestamps against timeframe boundaries
- Timestamp format parsing and normalization
- Timeframe normalization and conversion
- Boundary calculation for different timeframes
- UTC standardization and timezone handling

Author: Trading Bot Core Team
"""

import logging
import random
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Union, Optional


@dataclass
class ValidationResult:
    """Result of timestamp validation operation."""
    is_valid: bool
    remaining_time: Optional[timedelta]
    next_boundary: Optional[datetime]
    error_message: Optional[str] = None


@dataclass
class TimeframeInfo:
    """Information about a normalized timeframe."""
    original: str
    normalized: str
    minutes: int
    timedelta: timedelta


class TimestampValidationError(Exception):
    """Base exception for timestamp validation errors."""
    pass


class InvalidTimestampFormatError(TimestampValidationError):
    """Raised when timestamp format is invalid or unparseable."""
    pass


class InvalidTimeframeError(TimestampValidationError):
    """Raised when timeframe format is invalid or unsupported."""
    pass


class TimezoneConversionError(TimestampValidationError):
    """Raised when timezone conversion fails."""
    pass


class TimestampValidator:
    """
    Centralized timestamp validation utility for trading recommendations.
    
    This class provides methods to validate if trading recommendations are still
    valid based on their timestamp and timeframe, handling boundary calculations
    and format normalization.
    """
    
    # Supported timeframes with their minute equivalents
    TIMEFRAME_MINUTES = {
        "1m": 1,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "1h": 60,
        "2h": 120,
        "4h": 240,
        "6h": 360,
        "12h": 720,
        "1d": 1440,
        "1w": 10080
    }
    
    # Timeframe normalization mappings
    TIMEFRAME_NORMALIZATIONS = {
        "60m": "1h",
        "120m": "2h",
        "240m": "4h",
        "360m": "6h",
        "720m": "12h",
        "1440m": "1d",
        "10080m": "1w",
        "min": "m",
        "minute": "m",
        "minutes": "m",
        "hour": "1h",
        "hours": "1h",
        "day": "1d",
        "days": "1d",
        "week": "1w",
        "weeks": "1w"
    }
    
    def __init__(self, default_timezone: str = "UTC"):
        """
        Initialize the timestamp validator.
        
        Args:
            default_timezone: Default timezone for timestamp operations (default: "UTC")
        """
        self.default_timezone = default_timezone
        self.logger = logging.getLogger(__name__)
        
    def is_recommendation_valid(
        self, 
        timestamp: Union[str, datetime], 
        timeframe: str,
        current_time: Optional[datetime] = None,
        allow_current_period: bool = True,
        grace_period_minutes: int = 15
    ) -> ValidationResult:
        """
        Check if a trading recommendation is still valid based on timestamp and timeframe.
        
        A recommendation is valid if the current time is still within the same timeframe
        boundary as when the recommendation was made, with additional grace period for
        processing delays typical in trading workflows.
        
        Args:
            timestamp: The recommendation timestamp (string or datetime)
            timeframe: The chart timeframe (e.g., "15m", "1h", "4h", "1d")
            current_time: Current time for validation (default: now in UTC)
            allow_current_period: If True, also consider recommendations from the current 
                                 timeframe period as valid (default: True)
            grace_period_minutes: Additional minutes to allow for processing delays (default: 15)
            
        Returns:
            ValidationResult with validation status and timing information
            
        Example:
            >>> validator = TimestampValidator()
            >>> result = validator.is_recommendation_valid("2024-01-15 14:14:00", "15m")
            >>> print(f"Valid: {result.is_valid}, Remaining: {result.remaining_time}")
        """
        try:
            # Parse and normalize inputs
            parsed_timestamp = self.parse_timestamp(timestamp)
            timeframe_info = self.normalize_timeframe(timeframe)
            
            if current_time is None:
                current_time = datetime.now(timezone.utc)
            elif current_time.tzinfo is None:
                current_time = current_time.replace(tzinfo=timezone.utc)
                
            # Calculate the next boundary after the recommendation timestamp
            next_boundary = self.calculate_next_boundary(parsed_timestamp, timeframe_info.normalized)
            
            # Add grace period to next boundary
            grace_period = timedelta(minutes=grace_period_minutes)
            next_boundary_with_grace = next_boundary + grace_period
            
            # Check if current time is still before the next boundary (with grace period)
            is_valid = current_time < next_boundary_with_grace
            
            # If allow_current_period is True, also check if the recommendation is from 
            # the current timeframe period (i.e., the period that just started)
            if not is_valid and allow_current_period:
                # Calculate the current period boundary
                current_period_boundary = self.calculate_next_boundary(current_time, timeframe_info.normalized) - timeframe_info.timedelta
                # Check if the recommendation timestamp is within the current period (with grace period)
                is_valid = parsed_timestamp >= current_period_boundary and parsed_timestamp < current_period_boundary + timeframe_info.timedelta + grace_period
            
            remaining_time = next_boundary_with_grace - current_time if is_valid else timedelta(0)
            
            self.logger.debug(
                f"Validation: timestamp={parsed_timestamp}, timeframe={timeframe_info.normalized}, "
                f"next_boundary={next_boundary}, current={current_time}, valid={is_valid}"
            )
            
            return ValidationResult(
                is_valid=is_valid,
                remaining_time=remaining_time if is_valid else None,
                next_boundary=next_boundary,
                error_message=None
            )
            
        except Exception as e:
            self.logger.error(f"Validation failed: {str(e)}")
            return ValidationResult(
                is_valid=False,
                remaining_time=None,
                next_boundary=None,
                error_message=str(e)
            )
    
    def get_remaining_validity_time(
        self, 
        timestamp: Union[str, datetime], 
        timeframe: str,
        current_time: Optional[datetime] = None
    ) -> Optional[timedelta]:
        """
        Calculate remaining time until recommendation expires.
        
        Args:
            timestamp: The recommendation timestamp
            timeframe: The chart timeframe
            current_time: Current time for calculation (default: now in UTC)
            
        Returns:
            Remaining time as timedelta, or None if already expired
        """
        result = self.is_recommendation_valid(timestamp, timeframe, current_time)
        return result.remaining_time
    
    def parse_timestamp(self, timestamp: Union[str, datetime]) -> datetime:
        """
        Parse various timestamp formats to UTC datetime.
        
        Supported formats:
        - "YYYY-MM-DD HH:MM:SS" (from timestamp_extractor)
        - "YYYY-MM-DDTHH:MM:SSZ" (ISO UTC)
        - "YYYY-MM-DD HH:MM:SS.ffffff" (with microseconds)
        - datetime objects (with timezone conversion)
        
        Args:
            timestamp: Timestamp in various formats
            
        Returns:
            Parsed datetime in UTC timezone
            
        Raises:
            InvalidTimestampFormatError: If timestamp format is not supported
        """
        if isinstance(timestamp, datetime):
            if timestamp.tzinfo is None:
                # Treat naive datetime as UTC
                return timestamp.replace(tzinfo=timezone.utc)
            else:
                # Convert to UTC
                return timestamp.astimezone(timezone.utc)
        
        if not isinstance(timestamp, str):
            raise InvalidTimestampFormatError(f"Timestamp must be string or datetime, got {type(timestamp)}")
        
        timestamp = timestamp.strip()
        
        # Define timestamp patterns and their corresponding formats
        patterns = [
            # ISO format with Z suffix
            (r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$', '%Y-%m-%dT%H:%M:%SZ'),
            # ISO format with timezone
            (r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$', '%Y-%m-%dT%H:%M:%S%z'),
            # Standard format with microseconds
            (r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{6}$', '%Y-%m-%d %H:%M:%S.%f'),
            # Standard format (from timestamp_extractor)
            (r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$', '%Y-%m-%d %H:%M:%S'),
            # Date only
            (r'^\d{4}-\d{2}-\d{2}$', '%Y-%m-%d'),
        ]
        
        for pattern, fmt in patterns:
            if re.match(pattern, timestamp):
                try:
                    parsed = datetime.strptime(timestamp, fmt)
                    # If no timezone info, treat as UTC
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    else:
                        # Convert to UTC
                        parsed = parsed.astimezone(timezone.utc)
                    return parsed
                except ValueError as e:
                    self.logger.warning(f"Failed to parse timestamp '{timestamp}' with format '{fmt}': {e}")
                    continue
        
        raise InvalidTimestampFormatError(f"Unsupported timestamp format: '{timestamp}'")
    
    def normalize_to_utc_iso(self, timestamp: Union[str, datetime]) -> str:
        """
        Convert timestamp to UTC ISO format string.
        
        Args:
            timestamp: Timestamp in various formats
            
        Returns:
            ISO format string in UTC (YYYY-MM-DDTHH:MM:SSZ)
        """
        parsed = self.parse_timestamp(timestamp)
        return parsed.strftime('%Y-%m-%dT%H:%M:%SZ')
    
    def normalize_timeframe(self, timeframe: str) -> TimeframeInfo:
        """
        Normalize timeframe format and extract information.
        
        Handles various timeframe formats:
        - "60m" → "1h"
        - "1440m" → "1d"
        - "minute" → "m"
        - "hours" → "h"
        
        Args:
            timeframe: Timeframe string to normalize
            
        Returns:
            TimeframeInfo with normalized data
            
        Raises:
            InvalidTimeframeError: If timeframe is not supported
        """
        if not isinstance(timeframe, str):
            raise InvalidTimeframeError(f"Timeframe must be string, got {type(timeframe)}")
        
        original = timeframe
        normalized = timeframe.lower().strip()
        
        # Apply normalization mappings (order matters - longer strings first)
        sorted_mappings = sorted(self.TIMEFRAME_NORMALIZATIONS.items(), key=lambda x: len(x[0]), reverse=True)
        for old, new in sorted_mappings:
            if old in normalized:
                normalized = normalized.replace(old, new)
                break  # Only apply first match to avoid double replacements
        
        # Handle special cases
        if normalized == "m":  # "minutes" -> "m" needs to become "1m"
            normalized = "1m"
        elif normalized == "h":  # "hours" -> "h" needs to become "1h"
            normalized = "1h"
        elif normalized == "d":  # "days" -> "d" needs to become "1d"
            normalized = "1d"
        elif normalized == "w":  # "weeks" -> "w" needs to become "1w"
            normalized = "1w"
        elif normalized.isdigit():  # Handle numeric-only timeframes (treat as minutes)
            normalized = f"{normalized}m"
        
        # Validate against supported timeframes
        if normalized not in self.TIMEFRAME_MINUTES:
            raise InvalidTimeframeError(f"Unsupported timeframe: '{original}' (normalized: '{normalized}')")
        
        minutes = self.TIMEFRAME_MINUTES[normalized]
        td = timedelta(minutes=minutes)
        
        return TimeframeInfo(
            original=original,
            normalized=normalized,
            minutes=minutes,
            timedelta=td
        )
    
    def timeframe_to_minutes(self, timeframe: str) -> int:
        """
        Convert timeframe to minutes.
        
        Args:
            timeframe: Timeframe string (e.g., "15m", "1h", "1d")
            
        Returns:
            Number of minutes
        """
        timeframe_info = self.normalize_timeframe(timeframe)
        return timeframe_info.minutes
    
    def timeframe_to_timedelta(self, timeframe: str) -> timedelta:
        """
        Convert timeframe to timedelta object.
        
        Args:
            timeframe: Timeframe string (e.g., "15m", "1h", "1d")
            
        Returns:
            timedelta object
        """
        timeframe_info = self.normalize_timeframe(timeframe)
        return timeframe_info.timedelta
    
    def calculate_next_boundary(self, timestamp: datetime, timeframe: str, add_random_delay: bool = False) -> datetime:
        """
        Calculate the next timeframe boundary after the given timestamp.
        
        Boundary calculation examples:
        - 15m timeframe at 14:14 → next boundary at 14:15
        - 1h timeframe at 13:55 → next boundary at 14:00
        - 1d timeframe → next boundary at 00:00 next day
        
        Args:
            timestamp: Reference timestamp (should be in UTC)
            timeframe: Normalized timeframe string
            add_random_delay: If True, adds 1-5 minutes random delay after boundary
            
        Returns:
            Next boundary datetime in UTC (with optional random delay)
            
        Raises:
            InvalidTimeframeError: If timeframe is not supported
        """
        timeframe_info = self.normalize_timeframe(timeframe)
        minutes = timeframe_info.minutes
        
        # Ensure timestamp is in UTC
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        else:
            timestamp = timestamp.astimezone(timezone.utc)
        
        if timeframe_info.normalized == "1w":
            # Weekly boundary: next Monday at 00:00 UTC
            days_until_monday = (7 - timestamp.weekday()) % 7
            if days_until_monday == 0:  # If it's Monday, go to next Monday
                days_until_monday = 7
            next_boundary = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
            next_boundary += timedelta(days=days_until_monday)
            
        elif timeframe_info.normalized == "1d":
            # Daily boundary: next day at 00:00 UTC
            next_boundary = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
            next_boundary += timedelta(days=1)
            
        elif minutes >= 60:
            # Hourly boundaries: align to hour boundaries
            hours = minutes // 60
            current_hour = timestamp.hour
            next_hour = ((current_hour // hours) + 1) * hours
            
            if next_hour >= 24:
                # Move to next day
                next_boundary = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
                next_boundary += timedelta(days=1, hours=next_hour - 24)
            else:
                next_boundary = timestamp.replace(hour=next_hour, minute=0, second=0, microsecond=0)
                
        else:
            # Minute boundaries: align to minute boundaries
            current_minute = timestamp.hour * 60 + timestamp.minute
            next_minute = ((current_minute // minutes) + 1) * minutes
            
            if next_minute >= 1440:  # 24 * 60
                # Move to next day
                next_boundary = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
                next_boundary += timedelta(days=1, minutes=next_minute - 1440)
            else:
                hour = next_minute // 60
                minute = next_minute % 60
                next_boundary = timestamp.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # Add random delay if requested (1 Minutes to 2 minutes after boundary)
        if add_random_delay:
            random_minutes = random.randint(1, 2)
            next_boundary += timedelta(minutes=random_minutes)
            self.logger.debug(f"Added random delay of {random_minutes} minutes to boundary")
        
        self.logger.debug(
            f"Boundary calculation: timestamp={timestamp}, timeframe={timeframe_info.normalized}, "
            f"next_boundary={next_boundary}, random_delay={add_random_delay}"
        )
        
        return next_boundary


# Convenience functions for common operations
def validate_recommendation(
    timestamp: Union[str, datetime], 
    timeframe: str,
    current_time: Optional[datetime] = None
) -> ValidationResult:
    """
    Convenience function to validate a trading recommendation.
    
    Args:
        timestamp: The recommendation timestamp
        timeframe: The chart timeframe
        current_time: Current time for validation (default: now in UTC)
        
    Returns:
        ValidationResult with validation status and timing information
    """
    validator = TimestampValidator()
    return validator.is_recommendation_valid(timestamp, timeframe, current_time)


def get_remaining_time(
    timestamp: Union[str, datetime], 
    timeframe: str,
    current_time: Optional[datetime] = None
) -> Optional[timedelta]:
    """
    Convenience function to get remaining validity time.
    
    Args:
        timestamp: The recommendation timestamp
        timeframe: The chart timeframe
        current_time: Current time for calculation (default: now in UTC)
        
    Returns:
        Remaining time as timedelta, or None if already expired
    """
    validator = TimestampValidator()
    return validator.get_remaining_validity_time(timestamp, timeframe, current_time)


def normalize_timestamp(timestamp: Union[str, datetime]) -> str:
    """
    Convenience function to normalize timestamp to UTC ISO format.
    
    Args:
        timestamp: Timestamp in various formats
        
    Returns:
        ISO format string in UTC (YYYY-MM-DDTHH:MM:SSZ)
    """
    validator = TimestampValidator()
    return validator.normalize_to_utc_iso(timestamp)
