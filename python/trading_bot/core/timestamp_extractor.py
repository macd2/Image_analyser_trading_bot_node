import base64
import io
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

import requests
from PIL import Image
from dotenv import load_dotenv
from pathlib import Path
from trading_bot.core.secrets_manager import get_openai_api_key
from trading_bot.core.timestamp_validator import TimestampValidator
from trading_bot.config.settings_v2 import ConfigV2

# Load .env.local from project root (unified env file)
_env_path = Path(__file__).parent.parent.parent.parent / '.env.local'
if _env_path.exists():
    load_dotenv(_env_path)
else:
    load_dotenv()

class TimestampExtractor:
    def __init__(self, config: Optional[ConfigV2] = None):
        self.api_key = get_openai_api_key()
        # Use provided config or load from database
        cfg = config or ConfigV2.load()
        self.model = cfg.openai.model
        self.max_tokens = cfg.openai.max_tokens
        self.temperature = cfg.openai.temperature
        self.logger = logging.getLogger(__name__)
        self.timestamp_validator = TimestampValidator()

    def crop_timestamp_area_legacy(self, image: Image.Image) -> Image.Image:
        """
        Crop the timestamp area using legacy coordinates (top-left corner).
        
        Uses legacy coordinates: (0, 0, 500, 30) - top-left corner
        
        Args:
            image: PIL Image object of the full screenshot
            
        Returns:
            Cropped PIL Image object containing just the timestamp area
        """
        return image.crop((0, 0, 500, 30))

    def crop_timestamp_area_new(self, image: Image.Image) -> Image.Image:
        """
        Crop the timestamp area from a chart screenshot (lower right corner with offsets).
        
        Uses optimized coordinates: 200x35 pixels with 300px left offset and 50px bottom offset
        
        Args:
            image: PIL Image object of the full screenshot
            
        Returns:
            Cropped PIL Image object containing just the timestamp area
        """
        width, height = image.size
        crop_width = 200  # Width of timestamp area
        crop_height = 35  # Height of timestamp area
        left_offset = 300  # Offset from right edge to move left
        bottom_offset = 50  # Offset from bottom edge to move up
        
        # Calculate coordinates for lower right corner with left and bottom offsets
        left = width - crop_width - left_offset
        top = height - crop_height - bottom_offset
        right = width - left_offset
        bottom = height - bottom_offset
        
        return image.crop((left, top, right, bottom))

    def extract_timestamp_from_image(self, image: Image.Image, crop_method: str = "new",
                                   validate_timestamp: bool = True) -> str:
        """
        Extracts the timestamp from a chart image using the OpenAI Vision API.

        Args:
            image: A PIL Image object (full screenshot).
            crop_method: Cropping method to use:
                        "new" (default) - uses optimized lower-right corner cropping
                        "legacy" - uses old top-left corner cropping
                        "none" - no cropping, uses full image
            validate_timestamp: Whether to validate the extracted timestamp (default: True)

        Returns:
            The extracted timestamp as a string, or an empty string if not found.
        """
        if not self.api_key:
            return "Error: OPENAI_API_KEY not found."

        # Apply cropping based on method
        if crop_method == "new":
            image = self.crop_timestamp_area_new(image)
        elif crop_method == "legacy":
            image = self.crop_timestamp_area_legacy(image)
        # If crop_method == "none", use the full image as-is

        # Convert PIL image to base64
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        base64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"What is the {'date and time' if crop_method=='legacy' else 'time'} displayed in this image? {'' if crop_method=='legacy' else datetime.now(timezone.utc).date()} Please return only the timestamp in the format YYYY-MM-DD HH:MM:SS."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature
        }

        try:
            response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            extracted_timestamp = result['choices'][0]['message']['content'].strip()
            print("Time UTC", datetime.now(timezone.utc))
            print("Extracted Timestamp:", extracted_timestamp)
            
            # Add timestamp validation if requested
            if validate_timestamp:
                return self._validate_and_process_timestamp(extracted_timestamp)
            else:
                # Return raw timestamp without validation
                return extracted_timestamp
                    
        except requests.exceptions.RequestException as e:
            error_msg = f"Error calling OpenAI API: {e}"
            return error_msg

    def _validate_and_process_timestamp(self, extracted_timestamp: str) -> str:
        """
        Validate and process the extracted timestamp using TimestampValidator.
        
        Args:
            extracted_timestamp: The raw timestamp string from OpenAI API
            
        Returns:
            The validated timestamp string (returns original if validation fails)
        """
        validation_error = None
        normalized_timestamp = None
        is_valid = False
        
        try:
            # Validate timestamp format and parse it
            parsed_timestamp = self.timestamp_validator.parse_timestamp(extracted_timestamp)
            
            # Check if timestamp is reasonable (not too far in past/future)
            current_time = datetime.now(timezone.utc)
            time_diff = abs((parsed_timestamp - current_time).total_seconds())
            
            # Consider timestamp valid if it's within 1 year of current time
            # This catches obviously wrong extractions like dates from 1970 or far future
            max_reasonable_diff = 365 * 24 * 3600  # 1 year in seconds
            
            if time_diff > max_reasonable_diff:
                validation_error = f"Timestamp {extracted_timestamp} is too far from current time (diff: {time_diff/3600:.1f} hours)"
                is_valid = False
                self.logger.warning(f"Timestamp validation failed: {validation_error}")
            else:
                # Normalize to UTC ISO format
                normalized_timestamp = self.timestamp_validator.normalize_to_utc_iso(parsed_timestamp)
                is_valid = True
                self.logger.debug(f"Timestamp validation successful: {extracted_timestamp} -> {normalized_timestamp}")
                
        except Exception as e:
            validation_error = f"Timestamp validation failed: {str(e)}"
            is_valid = False
            self.logger.warning(validation_error)
        
        # For backward compatibility, return the original timestamp even if validation failed
        # but log the validation result
        if not is_valid:
            self.logger.warning(f"Returning potentially invalid timestamp: {extracted_timestamp}")
        return extracted_timestamp

    def extract_timestamp_with_validation(self, image: Image.Image, crop_method: str = "new") -> Dict[str, Any]:
        """
        Extracts the timestamp from a chart image with detailed validation information.

        Args:
            image: A PIL Image object (full screenshot).
            crop_method: Cropping method to use:
                        "new" (default) - uses optimized lower-right corner cropping
                        "legacy" - uses old top-left corner cropping
                        "none" - no cropping, uses full image

        Returns:
            Dict with 'timestamp', 'is_valid', 'normalized_timestamp', and 'validation_error' keys.
        """
        if not self.api_key:
            return {
                'timestamp': "",
                'is_valid': False,
                'normalized_timestamp': None,
                'validation_error': "Error: OPENAI_API_KEY not found."
            }

        # Apply cropping based on method
        if crop_method == "new":
            image = self.crop_timestamp_area_new(image)
        elif crop_method == "legacy":
            image = self.crop_timestamp_area_legacy(image)
        # If crop_method == "none", use the full image as-is

        # Convert PIL image to base64
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        base64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"What is the {'date and time' if crop_method=='legacy' else 'time'} displayed in this image? {'' if crop_method=='legacy' else datetime.now(timezone.utc).date()} Please return only the timestamp in the format YYYY-MM-DD HH:MM:SS."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature
        }

        try:
            response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            extracted_timestamp = result['choices'][0]['message']['content'].strip()
            print("Extracted Timestamp:", extracted_timestamp)
            
            # Perform detailed validation
            return self._get_validation_info(extracted_timestamp)
                    
        except requests.exceptions.RequestException as e:
            error_msg = f"Error calling OpenAI API: {e}"
            return {
                'timestamp': "",
                'is_valid': False,
                'normalized_timestamp': None,
                'validation_error': error_msg
            }

    def _get_validation_info(self, extracted_timestamp: str) -> Dict[str, Any]:
        """
        Get detailed validation information for a timestamp.
        
        Args:
            extracted_timestamp: The raw timestamp string
            
        Returns:
            Dict with validation details
        """
        validation_error = None
        normalized_timestamp = None
        is_valid = False
        
        try:
            # Validate timestamp format and parse it
            parsed_timestamp = self.timestamp_validator.parse_timestamp(extracted_timestamp)
            
            # Check if timestamp is reasonable (not too far in past/future)
            current_time = datetime.now(timezone.utc)
            time_diff = abs((parsed_timestamp - current_time).total_seconds())
            
            # Consider timestamp valid if it's within 1 year of current time
            # This catches obviously wrong extractions like dates from 1970 or far future
            max_reasonable_diff = 365 * 24 * 3600  # 1 year in seconds
            
            if time_diff > max_reasonable_diff:
                validation_error = f"Timestamp {extracted_timestamp} is too far from current time (diff: {time_diff/3600:.1f} hours)"
                is_valid = False
                self.logger.warning(f"Timestamp validation failed: {validation_error}")
            else:
                # Normalize to UTC ISO format
                normalized_timestamp = self.timestamp_validator.normalize_to_utc_iso(parsed_timestamp)
                is_valid = True
                self.logger.debug(f"Timestamp validation successful: {extracted_timestamp} -> {normalized_timestamp}")
                
        except Exception as e:
            validation_error = f"Timestamp validation failed: {str(e)}"
            is_valid = False
            self.logger.warning(validation_error)
        
        return {
            'timestamp': extracted_timestamp,
            'is_valid': is_valid,
            'normalized_timestamp': normalized_timestamp,
            'validation_error': validation_error
        }
