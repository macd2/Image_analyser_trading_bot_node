"""Chart analysis module using OpenAI Vision API and Assistant API."""
import base64
import io
import json
import logging
import re
from typing import Dict, Any, Optional, Callable

from PIL import Image

from .data_agent import DataAgent
from .simple_openai_handler import SimpleOpenAIAssistantHandler
from .timeframe_extractor import TimeframeExtractor
from .timestamp_extractor import TimestampExtractor
from .timestamp_validator import TimestampValidator
from .bybit_api_manager import BybitAPIManager
from .utils import smart_format_price, normalize_symbol_for_bybit
from ..config.settings_v2 import ConfigV2
# Use the dynamic prompt registry for looking up prompts by name
from .prompts.prompt_registry import get_prompt_function as get_prompt_by_name



class ChartAnalyzer:
    """Analyzes chart images using OpenAI's Vision API and Assistant API."""

    def __init__(self, openai_client, config: ConfigV2, skip_boundary_validation: bool = False, api_manager: Optional[BybitAPIManager] = None, logger: Optional[logging.Logger] = None):
        self.client = openai_client
        self.config = config
        self.skip_boundary_validation = skip_boundary_validation
        self.data_agent = DataAgent()
        self.timestamp_extractor = TimestampExtractor(config=config)
        self.timeframe_extractor = TimeframeExtractor(config=config)
        self.timestamp_validator = TimestampValidator()

        # Use provided logger or fallback to module logger
        self.logger = logger or logging.getLogger(__name__)

        # Initialize Assistant handler if assistant is configured
        self.assistant_handler = None
        if hasattr(config, 'openai') and getattr(config.openai, 'assistant_id', None):
            self.assistant_handler = SimpleOpenAIAssistantHandler(openai_client, config)

        # Use provided API manager or create new one
        if api_manager:
            self.bybit_api_manager = api_manager
            self.bybit_session = api_manager.session
        else:
            # Initialize Bybit client for market data
            try:
                self.bybit_api_manager = BybitAPIManager(self.config, use_testnet=self.config.bybit.use_testnet)
                self.bybit_session = self.bybit_api_manager.session
            except (ImportError, Exception) as e:
                print(f"Failed to initialize BybitAPIManager: {e}")
                self.bybit_api_manager = None
                self.bybit_session = None

    def encode_image(self, image_path: str) -> str:
        """Encode image to base64."""
        from trading_bot.core.storage import read_file

        # Read file from storage (supports both local and Supabase)
        image_data = read_file(image_path)
        if image_data is None:
            raise FileNotFoundError(f"Image not found: {image_path}")

        return base64.b64encode(image_data).decode("utf-8")

    def encode_image_pil(self, image: Image.Image) -> str:
        """Encode PIL image to base64."""
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def get_bid_ask_prices(self, symbol: str, category: str = "linear") -> Dict[str, Optional[float]]:
        """Get bid and ask prices for a symbol using tickers endpoint."""
        if not self.bybit_api_manager:
            return {"bid": None, "ask": None, "mid": None}

        try:
            normalized_symbol = normalize_symbol_for_bybit(symbol)
            response = self.bybit_api_manager.get_tickers(
                category=category,
                symbol=normalized_symbol
            )

            if response and response.get("retCode") == 0:
                ticker_list = response.get("result", {}).get("list", [])
                if ticker_list:
                    ticker = ticker_list[0]
                    bid = float(ticker.get("bid1Price", 0))
                    ask = float(ticker.get("ask1Price", 0))
                    mid = (bid + ask) / 2 if bid > 0 and ask > 0 else None
                    return {"bid": bid, "ask": ask, "mid": mid}
        except Exception as e:
            print(f"Failed to get bid/ask prices: {e}")

        return {"bid": None, "ask": None, "mid": None}

    def get_enriched_market_data(self, symbol: str, timeframe: str, category: str = "linear") -> Dict[str, Any]:
        """
        Get enriched market data from Bybit tickers API with descriptive keys for prompt injection.

        Returns dict with: last_price, price_change_24h_percent, high_24h, low_24h,
                          funding_rate, long_short_ratio, timeframe, symbol
        """
        market_data: Dict[str, Any] = {
            'last_price': 'N/A',
            'price_change_24h_percent': 'N/A',
            'high_24h': 'N/A',
            'low_24h': 'N/A',
            'funding_rate': 'N/A',
            'long_short_ratio': 'N/A',
            'timeframe': timeframe,
            'symbol': symbol
        }

        if not self.bybit_api_manager:
            print(f"⚠️ Bybit API manager not available - using placeholder market data")
            return market_data

        try:
            normalized_symbol = normalize_symbol_for_bybit(symbol)

            # Get ticker data (includes price, 24h stats, etc.)
            ticker_response = self.bybit_api_manager.get_tickers(
                category=category,
                symbol=normalized_symbol
            )

            if ticker_response and ticker_response.get("retCode") == 0:
                ticker_list = ticker_response.get("result", {}).get("list", [])
                if ticker_list:
                    ticker = ticker_list[0]

                    # Extract price data
                    last_price = ticker.get("lastPrice", "N/A")
                    market_data['last_price'] = float(last_price) if last_price != "N/A" else "N/A"

                    # Extract 24h statistics
                    price_change_pct = ticker.get("price24hPcnt", "N/A")
                    if price_change_pct != "N/A":
                        # Convert to percentage format (e.g., "0.0068" -> "+0.68%")
                        pct_value = float(price_change_pct) * 100
                        market_data['price_change_24h_percent'] = f"{'+' if pct_value >= 0 else ''}{pct_value:.2f}%"

                    high_24h = ticker.get("highPrice24h", "N/A")
                    market_data['high_24h'] = float(high_24h) if high_24h != "N/A" else "N/A"

                    low_24h = ticker.get("lowPrice24h", "N/A")
                    market_data['low_24h'] = float(low_24h) if low_24h != "N/A" else "N/A"

                    # Funding rate is already in ticker for linear/inverse
                    funding_rate = ticker.get("fundingRate", "N/A")
                    if funding_rate != "N/A":
                        # Convert to percentage format (e.g., "0.0001" -> "0.01%")
                        fr_value = float(funding_rate) * 100
                        market_data['funding_rate'] = f"{fr_value:.4f}%"

            # Get long/short ratio (separate API call)
            try:
                ls_ratio_response = self.bybit_api_manager.get_long_short_ratio(
                    symbol=normalized_symbol,
                    timeframe=timeframe
                )

                if ls_ratio_response and ls_ratio_response.get("retCode") == 0:
                    ratio_list = ls_ratio_response.get("result", {}).get("list", [])
                    if ratio_list:
                        market_data['long_short_ratio'] = ratio_list[0].get("buyRatio", "N/A")
            except Exception as e:
                print(f"⚠️ Could not fetch long/short ratio for {symbol}: {e}")

        except Exception as e:
            print(f"❌ Error fetching enriched market data for {symbol}: {e}")

        return market_data

    def clean_json_response(self, content: str) -> str:
        """Clean and fix common JSON formatting issues from AI responses."""
        if not content or not content.strip():
            return ""

        # Remove markdown formatting
        clean_content = content.strip()
        if clean_content.startswith('```json'):
            clean_content = clean_content[7:]
        if clean_content.startswith('```'):
            clean_content = clean_content[3:]
        if clean_content.endswith('```'):
            clean_content = clean_content[:-3]
        clean_content = clean_content.strip()

        # Fix common JSON issues
        # Remove trailing commas before closing brackets
        clean_content = re.sub(r',(\s*[\]}])', r'\1', clean_content)

        # Ensure proper quotes
        clean_content = re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)(\s*:)', r'\1"\2"\3', clean_content)

        # Fix unquoted property names
        clean_content = re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)(\s*:\s*")', r'\1"\2"\3', clean_content)

        # Remove commas from numbers to prevent JSON errors
        clean_content = re.sub(r'(?<=\d),(?=\d)', '', clean_content)

        return clean_content

    def get_last_close_price(self, symbol: str, timeframe: str) -> Optional[float]:
        """Get the last close price for a given symbol and timeframe."""
        if not self.bybit_api_manager:
            return None

        # Normalize the symbol for Bybit API
        normalized_symbol = normalize_symbol_for_bybit(symbol)
        if normalized_symbol != symbol:
            pass  # Symbol normalized

        # Map common intervals to Bybit kline intervals
        interval_map = {
            "1m": "1", "5m": "5", "15m": "15", "30m": "30",
            "1h": "60", "2h": "120", "4h": "240", "6h": "360",
            "12h": "720", "1d": "D", "1w": "W", "1M": "M"
        }
        bybit_interval = interval_map.get(timeframe.lower())  # Use the actual timeframe interval

        if not bybit_interval:
            bybit_interval = "60"  # Default to 1 hour if timeframe not recognized

        try:
            # Fetch last 2 candles to ensure we get a completed one
            response = self.bybit_api_manager.get_kline(
                category="linear",
                symbol=normalized_symbol, # Use normalized symbol here
                interval=bybit_interval,
                limit=2  # Get the last 2 candles
            )

            if response and response.get("retCode") == 0 and response.get("result") and response["result"].get("list"):
                candles = response["result"]["list"]

                if not candles:
                    return None # No candles returned

                # Get server time for comparison
                from .utils import get_bybit_server_time, parse_timeframe_to_minutes
                server_time_ms = get_bybit_server_time(self.bybit_api_manager.session)

                # If server time is not available, or only one candle is returned,
                # we can't reliably determine if the first candle is open.
                # In this case, we default to using the first candle if it exists,
                # or the second if it exists and the first doesn't.
                if not server_time_ms or len(candles) == 1:
                    return float(candles[0][4]) # Use the first candle if only one or no server time

                # Check if the first candle (index 0) is still open
                first_candle_start_time_ms = int(candles[0][0])  # Start time of the first candle in ms
                timeframe_duration_ms = parse_timeframe_to_minutes(timeframe) * 60 * 1000  # Convert timeframe to ms

                # A candle is considered open if the current server time is within its duration
                # from its start time.
                # We add a small buffer (e.g., 1000ms) to account for API latency and clock skew.
                if (server_time_ms - first_candle_start_time_ms) < (timeframe_duration_ms - 1000):
                    # The first candle is still open, so use the second candle (index 1)
                    # This assumes the second candle is always a completed one.
                    return float(candles[1][4]) if len(candles) > 1 else None
                else:
                    # The first candle is completed, so use it
                    return float(candles[0][4])
            else:
                return None
        except Exception:
            return None

    def analyze_chart_with_assistant(  # noqa: ARG002
        self,
        image_path: str,
        assistant_id: Optional[str] = None,
        target_timeframe: Optional[str] = None,
        prompt_function: Optional[Callable] = None,
        custom_prompt_data: Optional[Dict[str, Any]] = None,
        skip_market_data: bool = False
    ) -> Dict[str, Any]:
        """Analyze chart using OpenAI Assistant API when available."""

        # Capture the analysis prompt for storage
        analysis_prompt = None

        if not self.assistant_handler:
            print("⚠️ Assistant handler not available, falling back to Vision API")
            return {
                "recommendation": "hold",
                "confidence": 0.0,
                "summary": "Assistant handler not available",
                "error": True,
                "fallback_required": True
            }

        # Check database existence FIRST - before ANY processing
        # If already analyzed, return the stored recommendation instead of re-analyzing
        stored_analysis = self.data_agent.get_analysis_by_image_path(image_path)
        if stored_analysis:
            print(f"         ♻️ Using cached analysis for {image_path}")
            # Parse analysis_data (raw_response) if it's a JSON string
            # This contains the FULL analysis response from the assistant
            analysis_data = stored_analysis.get("analysis_data") or "{}"
            if isinstance(analysis_data, str):
                try:
                    analysis_data = json.loads(analysis_data)
                except json.JSONDecodeError:
                    analysis_data = {}

            # Return the full analysis object in the same format as fresh analysis
            # The raw_response contains all the fields from the assistant handler
            if isinstance(analysis_data, dict):
                # Merge database fields with the full analysis data
                # Database fields take precedence for critical trading fields
                result = analysis_data.copy()
                result["entry_price"] = stored_analysis.get("entry_price")
                result["stop_loss"] = stored_analysis.get("stop_loss")
                result["take_profit"] = stored_analysis.get("take_profit")
                result["risk_reward"] = stored_analysis.get("risk_reward")
                result["cached"] = True
                result["timestamp"] = stored_analysis.get("timestamp")
                return result
            else:
                # Fallback if analysis_data is not a dict
                return {
                    "recommendation": stored_analysis.get("recommendation", "hold"),
                    "confidence": stored_analysis.get("confidence", 0.0),
                    "summary": stored_analysis.get("summary", ""),
                    "analysis": {},
                    "entry_price": stored_analysis.get("entry_price"),
                    "stop_loss": stored_analysis.get("stop_loss"),
                    "take_profit": stored_analysis.get("take_profit"),
                    "risk_reward": stored_analysis.get("risk_reward"),
                    "cached": True,
                    "error": False
                }

        try:
            from trading_bot.core.storage import read_file
            import io

            # Read image from storage (supports both local and Supabase)
            image_data = read_file(image_path)
            if image_data is None:
                raise FileNotFoundError(f"Image not found: {image_path}")

            with Image.open(io.BytesIO(image_data)) as img:
                # For autotrader: use filename timestamp instead of image extraction to avoid timezone issues
                from .utils import extract_timestamp_from_filename
                filename_timestamp = extract_timestamp_from_filename(image_path)

                if filename_timestamp:
                    extracted_timestamp = filename_timestamp
                    print(f"🔧 Using filename timestamp: {extracted_timestamp} (UTC)")
                else:
                    extracted_timestamp = self.timestamp_extractor.extract_timestamp_from_image(img, crop_method="new")
                    print(f"⚠️ Using image-extracted timestamp: {extracted_timestamp}")

                # Determine timeframe: in backtest (skip_market_data=True) use provided target_timeframe to avoid OCR/API cost
                if skip_market_data and target_timeframe:
                    timeframe = target_timeframe
                else:
                    # Crop the image for the timeframe extractor (production path)
                    timeframe_cropped = img.crop((100, 0, 400, 70))
                    timeframe = self.timeframe_extractor.extract_timeframe_from_image(timeframe_cropped)
        except Exception as e:
            return {
                "recommendation": "hold",
                "confidence": 0.0,
                "summary": f"Extraction failed: {e}",
                "error": True
            }

        # Check if timeframe extraction failed
        if timeframe is None:
            from pathlib import Path
            symbol = Path(image_path).stem.split('_')[0].upper()
            print(f"⏸️ SKIPPED {symbol}: Missing timeframe")
            return {
                "recommendation": "hold",
                "confidence": 0.0,
                "summary": f"Skipped {symbol}: Missing timeframe",
                "skipped": True,
                "error": False,
                "skip_reason": "missing_timeframe"
            }

        # Validate and normalize timeframe
        try:
            timeframe_info = self.timestamp_validator.normalize_timeframe(timeframe)
            normalized_timeframe = timeframe_info.normalized

            # Early validation: Skip if target_timeframe is specified and doesn't match
            if target_timeframe and normalized_timeframe != target_timeframe:
                from pathlib import Path
                symbol = Path(image_path).stem.split('_')[0].upper()
                print(f"⏸️ SKIPPED {symbol}: Timeframe '{normalized_timeframe}' doesn't match target '{target_timeframe}'")
                return {
                    "recommendation": "hold",
                    "confidence": 0.0,
                    "summary": f"Skipped {symbol}: Timeframe '{normalized_timeframe}' doesn't match target '{target_timeframe}'",
                    "skipped": True,
                    "error": False,
                    "skip_reason": "timeframe_mismatch"
                }
        except Exception as e:
            from pathlib import Path
            symbol = Path(image_path).stem.split('_')[0].upper()
            print(f"⏸️ SKIPPED {symbol}: Invalid timeframe '{timeframe}' - {e}")
            return {
                "recommendation": "hold",
                "confidence": 0.0,
                "summary": f"Skipped {symbol}: Invalid timeframe '{timeframe}' - {e}",
                "skipped": True,
                "error": False,
                "skip_reason": "invalid_timeframe"
            }

        # Extract symbol from filename
        from pathlib import Path
        symbol = Path(image_path).stem.split('_')[0].upper()

        # Skip market data fetching for historical backtests
        if skip_market_data:
            # Use placeholder market data for historical backtests
            market_data = {
                'last_price': 'N/A',
                'price_change_24h_percent': 'N/A',
                'high_24h': 'N/A',
                'low_24h': 'N/A',
                'funding_rate': 'N/A',
                'long_short_ratio': 'N/A',
                'timeframe': normalized_timeframe,
                'symbol': symbol
            }
            print(f"📊 Skipping market data fetch for historical backtest")
        else:
            # Get enriched market data (includes last_price, 24h stats, funding, L/S ratio)
            market_data = self.get_enriched_market_data(symbol, normalized_timeframe)


        # Use configured assistant ID
        if not assistant_id:
            assistant_id = self.config.openai.assistant_id

        if not assistant_id:
            return {
                "recommendation": "hold",
                "confidence": 0.0,
                "summary": "No assistant ID configured",
                "error": True,
                "fallback_required": True,
            }

        # Prompt selection
        # If a custom prompt was provided by caller (e.g., backtests), use it as-is
        if custom_prompt_data is not None:
            prompt_data = custom_prompt_data
        elif prompt_function is not None:
            # If a prompt function was provided, build the prompt from market_data
            prompt_data = prompt_function(market_data)
        else:
            # Default: use trade playbook prompt (via dynamic registry)
            default_prompt_fn = get_prompt_by_name('get_analyzer_prompt_trade_playbook_v1')
            prompt_data = default_prompt_fn(market_data)

        analysis_prompt = prompt_data['prompt']

        # Retrieve assistant model name for logging visibility
        assistant_model_name = None
        try:
            asst_obj = self.client.beta.assistants.retrieve(assistant_id)
            assistant_model_name = getattr(asst_obj, 'model', None)
        except Exception:
            assistant_model_name = None


        # Log prompt version and assistant model for tracking
        print(f"📋 Using prompt version: {prompt_data['version']['version']} - {prompt_data['version']['name']} | Model: {assistant_model_name or 'N/A'}")
        print(f"""
        📊 Market Data for Analysis:
        Last Price: {market_data.get('last_price', 'N/A')}
        24h Change: {market_data.get('price_change_24h_percent', 'N/A')}
        24h High: {market_data.get('high_24h', 'N/A')}
        24h Low: {market_data.get('low_24h', 'N/A')}
        Funding Rate: {market_data.get('funding_rate', 'N/A')}
        Long/Short Ratio: {market_data.get('long_short_ratio', 'N/A')}
        Timeframe: {market_data.get('timeframe', 'N/A')}
        Symbol: {market_data.get('symbol', 'N/A')}
        """)

        # Use assistant to analyze the chart
        # Convert 'N/A' to None for type safety
        last_price_raw = market_data.get('last_price')
        last_price_value: Optional[float] = None if last_price_raw == 'N/A' else (float(last_price_raw) if isinstance(last_price_raw, (int, float, str)) and last_price_raw != 'N/A' else None)

        result = self.assistant_handler.analyze_chart_for_autotrader(
        message=analysis_prompt,
        agent_id=assistant_id,
        image_path=image_path,
        symbol=symbol,
        timeframe=normalized_timeframe,
        last_close_price=last_price_value,
        timeout=600, # Increased timeout to 10 minutes
        prompt_data=prompt_data  # Pass full prompt data including decision matrix
        )

        # Add timestamp information
        result['timestamp'] = extracted_timestamp
        result['original_timeframe'] = timeframe
        result['normalized_timeframe'] = normalized_timeframe
        result['analysis_method'] = 'assistant'
        result['analysis_prompt'] = analysis_prompt  # Store the prompt
        result['passed_image'] = image_path
        result['trade_confidence'] = result["confidence"]
        result['prompt_version'] = prompt_data['version']['name']  # Add prompt version
        result['prompt_id'] = prompt_data['version']['name']  # Add prompt_id for database
        result['market_data_snapshot'] = market_data  # Add market data snapshot for database

        # Log analyzer result
        self.logger.info("🤖 ASSISTANT ANALYSIS RESULT:")
        self.logger.info(f"   📊 Symbol: {symbol}")
        self.logger.info(f"   📈 Recommendation: {result.get('recommendation', 'N/A')}")
        self.logger.info(f"   🎯 Confidence: {result.get('confidence', 0):.2f}")
        self.logger.info(f"   💰 Entry: {result.get('entry_price', 'N/A')}")
        self.logger.info(f"   🛑 Stop Loss: {result.get('stop_loss', 'N/A')}")
        self.logger.info(f"   🎯 Take Profit: {result.get('take_profit', 'N/A')}")
        self.logger.info(f"   📊 Risk-Reward: {result.get('risk_reward_ratio', 'N/A')}")
        self.logger.info(f"   📋 Prompt: {result.get('prompt_version', 'N/A')} | Model: {result.get('assistant_model', 'N/A')}")

        # Show decision matrix correction if it happened
        if 'llm_original_recommendation' in result:
            original = result.get('llm_original_recommendation', 'N/A')
            corrected = result.get('recommendation', 'N/A')
            self.logger.info(f"   ⚖️  Decision Matrix: Corrected '{original}' → '{corrected}'")

        self.logger.info("   " + "="*50)

        # Note: Local image files are preserved for debugging and re-analysis
        # The assistant handler automatically cleans up uploaded files from OpenAI storage

        return result

    def analyze_chart(self, image_path: str, use_assistant: bool = False, target_timeframe: Optional[str] = None, prompt_function: Optional[Callable] = None, custom_prompt_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Main analysis method that chooses between Vision API and Assistant API."""

        # Skip boundary validation if configured (for backtesting)
        if not self.skip_boundary_validation:
            # Validate file timestamp against current boundary
            from pathlib import Path
            from .utils import extract_timeframe_from_filename, validate_file_timestamp_against_current_boundary

            # Extract timeframe from filename if not provided
            if not target_timeframe:
                target_timeframe = extract_timeframe_from_filename(image_path)

            # Validate file timestamp against current boundary
            if target_timeframe:
                validation_result = validate_file_timestamp_against_current_boundary(image_path, target_timeframe)
                if not validation_result["is_valid"]:
                    symbol = Path(image_path).stem.split("_")[0].upper()
                    print(f"⏸️ SKIPPED {symbol}: {validation_result['reason']}")
                    print(f"   File boundary: {validation_result.get('file_boundary')}")
                    print(f"   Current boundary: {validation_result.get('current_boundary')}")
                    return {
                        "recommendation": "hold",
                        "confidence": 0.0,
                        "summary": f"Skipped {symbol}: {validation_result['reason']}",
                        "skipped": True,
                        "error": False,
                        "skip_reason": "boundary_validation_failed",
                        "boundary_info": validation_result
                    }
            else:
                print(f"⚠️ Could not extract timeframe from filename for boundary validation: {image_path}")
                print(f"   Filename: {Path(image_path).name}")
                # Try to extract symbol for logging
                try:
                    symbol = Path(image_path).stem.split("_")[0].upper()
                    print(f"   Symbol: {symbol}")
                except:
                    pass
        else:
            print(f"🔄 BACKTEST MODE: Skipping boundary validation for {image_path}")

        # Auto-detect if we should use assistant based on configuration (when use_assistant not explicitly set)
        if not use_assistant:
            should_use_assistant = (
                self.assistant_handler is not None and
                hasattr(self.config.openai, 'assistant_id') and
                self.config.openai.assistant_id is not None and
                self.config.openai.assistant_id.strip() != ''
            )
            use_assistant = should_use_assistant

        # Determine if we should use assistant
        if use_assistant:
            print("         🤖 Using OpenAI Assistant API for chart analysis")
            # Try assistant first, fallback to vision API if needed
            result = self.analyze_chart_with_assistant(image_path, target_timeframe=target_timeframe, prompt_function=prompt_function, custom_prompt_data=custom_prompt_data)
            if result.get('fallback_required'):
                print("         ⚠️ Assistant unavailable, falling back to Vision API")
                return self._analyze_chart_vision_internal(image_path, target_timeframe)
            return result
        else:
            print("         👁️ Using OpenAI Vision API (standard) for chart analysis")
            # Use traditional vision API
            return self._analyze_chart_vision_internal(image_path, target_timeframe)

    def _analyze_chart_vision_internal(self, image_path: str, target_timeframe: Optional[str] = None) -> Dict[str, Any]:
        """Internal method for vision-based analysis (original analyze_chart)."""
        # This contains the original analyze_chart implementation
        # Check database existence FIRST - before ANY processing
        # If already analyzed, return the stored recommendation instead of re-analyzing
        stored_analysis = self.data_agent.get_analysis_by_image_path(image_path)
        if stored_analysis:
            print(f"         ♻️ Using cached analysis for {image_path}")
            # Parse analysis_data (raw_response) if it's a JSON string
            # This contains the FULL analysis response from the assistant
            analysis_data = stored_analysis.get("analysis_data") or "{}"
            if isinstance(analysis_data, str):
                try:
                    analysis_data = json.loads(analysis_data)
                except json.JSONDecodeError:
                    analysis_data = {}

            # Return the full analysis object in the same format as fresh analysis
            # The raw_response contains all the fields from the assistant handler
            if isinstance(analysis_data, dict):
                # Merge database fields with the full analysis data
                # Database fields take precedence for critical trading fields
                result = analysis_data.copy()
                result["entry_price"] = stored_analysis.get("entry_price")
                result["stop_loss"] = stored_analysis.get("stop_loss")
                result["take_profit"] = stored_analysis.get("take_profit")
                result["risk_reward"] = stored_analysis.get("risk_reward")
                result["cached"] = True
                result["timestamp"] = stored_analysis.get("timestamp")
                return result
            else:
                # Fallback if analysis_data is not a dict
                return {
                    "recommendation": stored_analysis.get("recommendation", "hold"),
                    "confidence": stored_analysis.get("confidence", 0.0),
                    "summary": stored_analysis.get("summary", ""),
                    "analysis": {},
                    "entry_price": stored_analysis.get("entry_price"),
                    "stop_loss": stored_analysis.get("stop_loss"),
                    "take_profit": stored_analysis.get("take_profit"),
                    "risk_reward": stored_analysis.get("risk_reward"),
                    "cached": True,
                    "error": False
                }

        try:
            from trading_bot.core.storage import read_file
            import io

            # Read image from storage (supports both local and Supabase)
            image_data = read_file(image_path)
            if image_data is None:
                raise FileNotFoundError(f"Image not found: {image_path}")

            with Image.open(io.BytesIO(image_data)) as img:
                # For autotrader: use filename timestamp instead of image extraction to avoid timezone issues
                from .utils import extract_timestamp_from_filename
                filename_timestamp = extract_timestamp_from_filename(image_path)

                if filename_timestamp:
                    # Use boundary-aligned timestamp from filename (already in UTC)
                    extracted_timestamp = filename_timestamp
                    print(f"📈 Using filename timestamp: {extracted_timestamp} (UTC)")
                else:
                    # Fallback to image extraction for non-autotrader scenarios
                    extracted_timestamp = self.timestamp_extractor.extract_timestamp_from_image(img, crop_method="new")
                    print(f"⚠️ Using image-extracted timestamp: {extracted_timestamp}")

                # Crop the image for the timeframe extractor
                timeframe_cropped = img.crop( (100, 0, 400, 70))
                timeframe = self.timeframe_extractor.extract_timeframe_from_image(timeframe_cropped)
        except Exception as e:
            return {
                "recommendation": "hold",
                "confidence": 0.0,
                "summary": f"Extraction failed: {e}",
                "error": True
            }

        # Check if timeframe extraction failed
        if timeframe is None:
            from pathlib import Path
            symbol = Path(image_path).stem.split('_')[0].upper()
            print(f"⏸️ SKIPPED {symbol}: Missing timeframe")
            return {
                "recommendation": "hold",
                "confidence": 0.0,
                "summary": f"Skipped {symbol}: Missing timeframe",
                "skipped": True,
                "error": False,
                "skip_reason": "missing_timeframe"
            }

        # Validate and normalize timeframe using TimestampValidator
        try:
            timeframe_info = self.timestamp_validator.normalize_timeframe(timeframe)
            normalized_timeframe = timeframe_info.normalized

            # Early validation: Skip if target_timeframe is specified and doesn't match
            if target_timeframe and normalized_timeframe != target_timeframe:
                from pathlib import Path
                symbol = Path(image_path).stem.split('_')[0].upper()
                print(f"⏸️ SKIPPED {symbol}: Timeframe '{normalized_timeframe}' doesn't match target '{target_timeframe}'")
                return {
                    "recommendation": "hold",
                    "confidence": 0.0,
                    "summary": f"Skipped {symbol}: Timeframe '{normalized_timeframe}' doesn't match target '{target_timeframe}'",
                    "skipped": True,
                    "error": False,
                    "skip_reason": "timeframe_mismatch"
                }
        except Exception as e:
            from pathlib import Path
            symbol = Path(image_path).stem.split('_')[0].upper()
            print(f"⏸️  SKIPPED {symbol}: Invalid timeframe '{timeframe}' - {e}")
            return {
                "recommendation": "hold",
                "confidence": 0.0,
                "summary": f"Skipped {symbol}: Invalid timeframe '{timeframe}' - {e}",
                "skipped": True,
                "error": False,
                "skip_reason": "invalid_timeframe"
            }

        # Validate timestamp if extracted (skip for backtesting)
        validation_result = None
        if extracted_timestamp and not self.skip_boundary_validation:
            try:
                validation_result = self.timestamp_validator.is_recommendation_valid(
                    extracted_timestamp, normalized_timeframe
                )
                if not validation_result.is_valid:
                    from pathlib import Path
                    from trading_bot.core.storage import delete_file, get_storage_type

                    symbol = Path(image_path).stem.split('_')[0].upper()
                    print(f"🗑️  DELETING {symbol}: Timestamp validation failed - recommendation expired")
                    print(f"   Extracted timestamp: {extracted_timestamp}")
                    print(f"   Timeframe: {normalized_timeframe}")
                    print(f"   Validation error: {validation_result.error_message}")

                    # Delete the expired file using centralized storage layer
                    try:
                        # Extract filename from path for storage layer
                        filename = Path(image_path).name
                        storage_type = get_storage_type()

                        # Use centralized delete_file function
                        result = delete_file(filename)

                        if result.get('success'):
                            print(f"✅ Deleted expired file: {filename} (storage: {storage_type})")
                        else:
                            print(f"❌ Failed to delete {filename}: {result.get('error', 'Unknown error')}")
                    except Exception as delete_error:
                        print(f"❌ Failed to delete {Path(image_path).name}: {delete_error}")

                    return {
                        "recommendation": "hold",
                        "confidence": 0.0,
                        "summary": f"Deleted {symbol}: Timestamp validation failed - recommendation expired",
                        "skipped": True,
                        "error": False,
                        "skip_reason": "timestamp_expired_deleted",
                        "timestamp": extracted_timestamp,
                        "timeframe": normalized_timeframe,
                        "validation_error": validation_result.error_message,
                        "file_deleted": True
                    }
            except Exception as e:
                from pathlib import Path
                symbol = Path(image_path).stem.split('_')[0].upper()
                print(f"⚠️  WARNING {symbol}: Timestamp validation error - {e}, proceeding with analysis")
        elif extracted_timestamp and self.skip_boundary_validation:
            print(f"🔄 BACKTEST MODE: Skipping timestamp validation for historical data")


        # Extract symbol from filename
        from pathlib import Path
        symbol = Path(image_path).stem.split('_')[0].upper()

        # Get last close price using normalized timeframe
        last_close_price = self.get_last_close_price(symbol, normalized_timeframe)

        # Get bid/ask prices
        bid_ask_prices = self.get_bid_ask_prices(symbol)
        bid_price = bid_ask_prices.get("bid")
        ask_price = bid_ask_prices.get("ask")
        mid_price = bid_ask_prices.get("mid")

        # Get funding rate
        funding_rate = "N/A"
        if self.bybit_api_manager:
            try:
                # Use a more descriptive name for the history variable
                # Use normalized symbol for Bybit API
                normalized_symbol = normalize_symbol_for_bybit(symbol)
                funding_history = self.bybit_api_manager.get_funding_rate_history(symbol=normalized_symbol)
                if funding_history and funding_history.get("retCode") == 0 and funding_history.get("result", {}).get("list"):
                    # Get the funding rate, provide a default if the key is missing
                    funding_rate = funding_history["result"]["list"][0].get("fundingRate", "N/A")
            except Exception as e:
                print(f"⚠️ Could not fetch funding rate for {symbol}: {e}")

        # Get long/short ratio
        long_short_ratio = "N/A"
        if self.bybit_api_manager:
            try:
                # Use a more descriptive name for the ratio variable
                # Use normalized symbol for Bybit API
                normalized_symbol = normalize_symbol_for_bybit(symbol)
                ratio_data = self.bybit_api_manager.get_long_short_ratio(symbol=normalized_symbol, timeframe=normalized_timeframe)
                if ratio_data and ratio_data.get("retCode") == 0 and ratio_data.get("result", {}).get("list"):
                    # Get the latest ratio data
                    latest_ratio = ratio_data["result"]["list"][0]
                    long_short_ratio = f"Buy: {latest_ratio.get('buyRatio', 'N/A')}, Sell: {latest_ratio.get('sellRatio', 'N/A')}"
            except Exception as e:
                print(f"⚠️ Could not fetch long/short ratio for {symbol}: {e}")

        # Get historical volatility
        volatility = "N/A"
        if self.bybit_api_manager:
            try:
                # Use a more descriptive name for the volatility variable
                # Extract base coin using utility function for consistent formatting
                from .utils import extract_base_coin_for_historical_volatility
                base_coin = extract_base_coin_for_historical_volatility(symbol)
                vol_data = self.bybit_api_manager.get_historical_volatility(baseCoin=base_coin)
                if vol_data and vol_data.get("retCode") == 0 and vol_data.get("result", []):
                    # Get the latest volatility data
                    latest_vol = vol_data["result"][0]
                    volatility = f"{latest_vol.get('value', 'N/A')} (Period: {latest_vol.get('period', 'N/A')}h)"
            except Exception as e:
                print(f"⚠️ Could not fetch historical volatility for {symbol}: {e}")

        base64_image = self.encode_image(image_path)

        # First prompt for general analysis
        analysis_prompt = f"""
            You are a professional trader with extensive knowledge and experience in the crypto markets.
            Your task is to analyze the provided chart image and provide a structured trading recommendation.

            Timeframe: {timeframe}
            {f'Current market price (mid): {smart_format_price(mid_price)}.' if mid_price else ''}
            Best Bid: {smart_format_price(bid_price)}
            Best Ask: {smart_format_price(ask_price)}
            Latest Funding Rate: {funding_rate}
            Long/Short Ratio: {long_short_ratio}
            Historical Volatility: {volatility}
            Timeframe: {timeframe}
            {f'Current market price (mid): {smart_format_price(mid_price)}.' if mid_price else ''}
            Best Bid: {smart_format_price(bid_price)}
            Best Ask: {smart_format_price(ask_price)}
            Latest Funding Rate: {funding_rate}
            Long/Short Ratio: {long_short_ratio}
            Historical Volatility: {volatility}

            Return your analysis in this exact JSON format:
            {{
            "recommendation": "buy" | "hold" | "sell",
            "summary": "Brief technical analysis summary",
            "evidence": "Evidence supporting your recommendation",
            "key_levels": {{
                "support": 0.0,
                "resistance": 0.0
            }},
            "risk_factors": ["Market volatility", "Potential reversal", "Trend"],
            "market_condition": "TRENDING" | "RANGING",
            "market_direction": "UP" | "DOWN",
            "timeframe": "short_term" | "medium_term" | "long_term",
            "extracted_timeframe": "{timeframe}",
            "normalized_timeframe": "{normalized_timeframe}",
            "symbol": "{symbol}",
            "confidence": 0.0,
            "last_close_price": {last_close_price if last_close_price else "null"},
            "bid_price": {bid_price if bid_price else "null"},
            "ask_price": {ask_price if ask_price else "null"},
            "mid_price": {mid_price if mid_price else "null"}
            }}

            Base your recommendation on:
            - Technical patterns (support/resistance, trends, formations)
            - Technical Indicators
            - Volume analysis if visible
            - Market sentiment indicators
            - The normalized timeframe for context
            - Current market price level

            🔄 Process
            - Identify trend
            - Identify key S/R zones
            - Look for patterns or setups
            - Confirm with volume or indicator

            Be precise and data-driven. Only return valid JSON.
            Crucially, all keys in the JSON structure must be enclosed in double quotes.
            IMPORTANT: Numerical values in the JSON, like for 'support' and 'resistance', must be standard numbers (e.g., 2992.33) and must NOT contain commas (e.g., use 2992.33, not 2,992.33).
        """

        try:
            # First request: General analysis
            analyzer_config = self.config.get_agent_config('analyzer')
            analysis_response = self.client.chat.completions.create(
                model=analyzer_config.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": analysis_prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=analyzer_config.max_tokens,
                temperature=analyzer_config.temperature
            )

            # Second prompt for position details
            position_prompt = f"""
                Based on the chart analysis, provide specific position recommendations with exact price levels.
                Chartanalysis: {analysis_response.choices[0].message.content}

                Return your position recommendation in this exact JSON format:
                {{
                "entry_price": 3000.50,
                "stop_loss": 2985.25,
                "take_profit": 3045.75,
                "trade_confidence": 0.82,
                "direction": "Long" | "Short",
                "entry_explenation":"explain why you choose this entry price",
                "take_profit_explenation":"explain why you choose this take profit price",
                "stop_loss_explenation":"explain why you choose this stop loss price",
                "bid_price": {bid_price if bid_price else "null"},
                "ask_price": {ask_price if ask_price else "null"},
                "mid_price": {mid_price if mid_price else "null"}
                }}

                Process:
                - Aim for for a RR of 1:2
                - "Determine your entry thesis for the trade, identify the invalidation level where your thesis is disproved, and place your stop loss just beyond this level.",
                "when_to_use": "Use this technique whenever entering a trade to limit potential losses.",
                - "If entering a short position after a support level breaks, place the stop loss just above the broken support level."

                All prices should be actual numerical values based on the chart's price scale.
                Be precise and provide actionable levels.
            """

            # Second request: Position details
            position_response = self.client.chat.completions.create(
                model=analyzer_config.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": position_prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=300,
                temperature=0.1
            )

            # Process analysis response
            analysis_content = analysis_response.choices[0].message.content
            if not analysis_content or not analysis_content.strip():
                return {
                    "recommendation": "hold",
                    "confidence": 0.0,
                    "summary": "AI response was empty",
                    "error": True
                }

            # Process position response
            position_content = position_response.choices[0].message.content
            if not position_content or not position_content.strip():
                return {
                    "recommendation": "hold",
                    "confidence": 0.0,
                    "summary": "Position analysis response was empty",
                    "error": True
                }

            # Clean and parse both responses
            clean_analysis = self.clean_json_response(analysis_content)
            clean_position = self.clean_json_response(position_content)

            if not clean_analysis or not clean_position:
                return {
                    "recommendation": "hold",
                    "confidence": 0.0,
                    "summary": "Failed to clean AI responses",
                    "raw_response": f"Analysis: {analysis_content}\nPosition: {position_content}",
                    "error": True
                }

            # Parse both JSON responses
            try:
                analysis_result = json.loads(clean_analysis)
                position_result = json.loads(clean_position)

                # Merge position details into analysis
                analysis_result.update(position_result)

            except json.JSONDecodeError as e:
                return {
                    "recommendation": "hold",
                    "confidence": 0.0,
                    "summary": f"Failed to parse AI response: {str(e)}",
                    "raw_response": f"Analysis: {clean_analysis}\nPosition: {clean_position}",
                    "error": True
                }

            # Add timestamp and validation information to analysis result
            analysis_result['timestamp'] = extracted_timestamp
            analysis_result['original_timeframe'] = timeframe
            analysis_result['normalized_timeframe'] = normalized_timeframe

            # Add validation information if available
            if validation_result:
                analysis_result['validation'] = {
                    'is_valid': validation_result.is_valid,
                    'remaining_time_seconds': validation_result.remaining_time.total_seconds() if validation_result.remaining_time else None,
                    'next_boundary': validation_result.next_boundary.isoformat() if validation_result.next_boundary else None,
                    'error_message': validation_result.error_message
                }
            else:
                analysis_result['validation'] = {
                    'is_valid': None,
                    'remaining_time_seconds': None,
                    'next_boundary': None,
                    'error_message': 'No timestamp extracted for validation'
                }

            # Add the analysis prompt
            analysis_result['analysis_prompt'] = analysis_prompt

            # Add bid/ask/mid prices to the result
            analysis_result['bid_price'] = bid_price
            analysis_result['ask_price'] = ask_price
            analysis_result['mid_price'] = mid_price

            # Log vision API result
            self.logger.info("👁️ VISION API ANALYSIS RESULT:")
            self.logger.info(f"   📊 Symbol: {symbol}")
            self.logger.info(f"   📈 Recommendation: {analysis_result.get('recommendation', 'N/A')}")
            self.logger.info(f"   🎯 Confidence: {analysis_result.get('confidence', 0):.2f}")
            self.logger.info(f"   💰 Entry: {analysis_result.get('entry_price', 'N/A')}")
            self.logger.info(f"   🛑 Stop Loss: {analysis_result.get('stop_loss', 'N/A')}")
            self.logger.info(f"   🎯 Take Profit: {analysis_result.get('take_profit', 'N/A')}")
            self.logger.info(f"   📊 Risk-Reward: {analysis_result.get('risk_reward_ratio', 'N/A')}")
            self.logger.info("   " + "="*50)

            return analysis_result

        except Exception as e:
            return {
                "recommendation": "hold",
                "confidence": 0.0,
                "summary": f"Analysis failed: {str(e)}",
                "error": True
            }
