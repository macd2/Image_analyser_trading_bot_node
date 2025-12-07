import base64
import io
import logging
from pathlib import Path
from typing import Optional

import requests
from PIL import Image
from dotenv import load_dotenv
from trading_bot.core.secrets_manager import get_openai_api_key
from trading_bot.config.settings_v2 import ConfigV2

# Load .env.local from project root (unified env file)
_env_path = Path(__file__).parent.parent.parent.parent / '.env.local'
if _env_path.exists():
    load_dotenv(_env_path)
else:
    load_dotenv()

class TimeframeExtractor:
    def __init__(self, config: Optional[ConfigV2] = None, instance_id: Optional[str] = None):
        self.api_key = get_openai_api_key()
        self.logger = logging.getLogger(__name__)
        # Use provided config or load from database
        if config:
            cfg = config
        elif instance_id:
            cfg = ConfigV2.from_instance(instance_id)
        else:
            raise ValueError("Either config or instance_id must be provided")
        self.model = cfg.openai.model
        self.max_tokens = cfg.openai.max_tokens
        self.temperature = cfg.openai.temperature

    def extract_timeframe_from_image(self, image: Image.Image) -> str | None:
        """
        Extracts the timeframe from a chart image using the OpenAI Vision API.

        Args:
            image: A PIL Image object.

        Returns:
            The extracted timeframe as a string (e.g., "15m", "1h", "4h") or None if extraction fails
        """
        if not self.api_key:
            self.logger.warning("OpenAI API key not found - cannot extract timeframe")
            return None

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
                            "text": "What is the timeframe displayed in this chart? Look for timeframe indicators like '15', '30', '1h', '4h', '1d', etc. Return only the timeframe as a single word (e.g., '15m', '1h', '4h', '1d'). If unclear, return 'None'. Note if there is only a number such as 15 than it is minutes and you should interpret it as 15m every timeframe less than 1 houre has no additon and are minutes"
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
            "max_tokens": 50,
            "temperature": self.temperature
        }

        try:
            response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            timeframe = result['choices'][0]['message']['content'].strip().lower()
            
            # Validate and normalize timeframe
            valid_timeframes = {"1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w", "1m"}
            if timeframe in valid_timeframes:
                print("Extracted Timeframe:",timeframe)
                return timeframe
            else:
                self.logger.warning(f"Invalid timeframe extracted: '{timeframe}' - not in valid timeframes")
                return None
                
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                self.logger.error(f"OpenAI API rate limit exceeded (429): Out of credits or too many requests. Skipping timeframe extraction.")
                print("❌ OpenAI API rate limit exceeded - please check your API credits and usage limits")
                return None
            else:
                self.logger.error(f"HTTP error during timeframe extraction: {str(e)}")
                return None
        except requests.exceptions.RequestException as e:
            self.logger.error(f"API request failed during timeframe extraction: {str(e)}")
            return None
