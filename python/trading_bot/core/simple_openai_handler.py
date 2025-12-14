"""Simple OpenAI Assistant API handler with image support."""
import base64
import io
import logging
import os
import tempfile
import time
from typing import Dict, Any, Optional, Set

import openai
from PIL import Image


class SimpleOpenAIAssistantHandler:
    """Simple wrapper for OpenAI Assistant API with text-only messaging."""

    def __init__(self, client: openai.OpenAI, config: Optional[Any] = None):
        """Initialize the OpenAI Assistant handler.

        Args:
            client: OpenAI client instance
            config: Configuration object (optional)
        """
        self.client = client
        self.config = config
        self.logger = logging.getLogger(__name__)
        # Track threads created per agent to allow cleanup at end of runs
        self._threads_by_agent: Dict[str, Set[str]] = {}

    def encode_image_pil(self, image: Image.Image) -> str:
        """Encode PIL image to base64 string.

        Args:
            image: PIL Image object

        Returns:
            Base64 encoded image string
        """
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        return base64.b64encode(buffer.getvalue()).decode('utf-8')

    def encode_image_path(self, image_path: str) -> str:
        """Encode image file to base64 string.

        Args:
            image_path: Path to image file

        Returns:
            Base64 encoded image string
        """
        from trading_bot.core.storage import read_file

        # Read file from storage (supports both local and Supabase)
        image_data = read_file(image_path)
        if image_data is None:
            raise FileNotFoundError(f"Image not found: {image_path}")

        return base64.b64encode(image_data).decode("utf-8")

    def create_thread(self) -> str:
        """Create a new conversation thread.

        Returns:
            Thread ID string
        """
        try:
            thread = self.client.beta.threads.create()
            self.logger.info(f"Created new thread: {thread.id}")
            return thread.id
        except Exception as e:
            self.logger.error(f"Failed to create thread: {e}")
            raise

    def upload_image_file(self, image_path: str) -> str:
        """Upload an image file to OpenAI and return the file ID.

        Args:
            image_path: Path to image file (can be storage path or local temp file)

        Returns:
            File ID string
        """
        try:
            from trading_bot.core.storage import read_file
            import io
            from pathlib import Path

            # Check if this is a temporary file (starts with /tmp or contains tempfile pattern)
            is_temp_file = image_path.startswith('/tmp') or 'tmp' in image_path.lower()

            if is_temp_file:
                # For temporary files, read directly from filesystem
                with open(image_path, 'rb') as f:
                    image_data = f.read()
            else:
                # For storage paths, use centralized storage layer
                image_data = read_file(image_path)
                if image_data is None:
                    raise FileNotFoundError(f"Image not found in storage: {image_path}")

            # Extract filename from path to preserve extension
            filename = Path(image_path).name

            # Create a file-like object from bytes with a name attribute
            file_like = io.BytesIO(image_data)
            file_like.name = filename  # OpenAI needs this to detect file type

            file_obj = self.client.files.create(
                file=file_like,
                purpose="vision"
            )
            self.logger.debug(f"Uploaded file: {file_obj.id} (filename: {filename})")
            return file_obj.id
        except Exception as e:
            self.logger.error(f"Failed to upload file {image_path}: {e}")
            raise

    def delete_uploaded_file(self, file_id: str) -> bool:
        """Delete an uploaded file from OpenAI storage.

        Args:
            file_id: The file ID to delete

        Returns:
            True if deletion was successful, False otherwise
        """
        try:
            self.client.files.delete(file_id)
            self.logger.debug(f"Deleted file: {file_id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete file {file_id}: {e}")
            return False

    def add_message_to_thread(self, thread_id: str, message: str,
                            image: Optional[Image.Image] = None,
                            image_path: Optional[str] = None) -> Dict[str, Any]:
        """Add a message to an existing thread with optional image.

        Args:
            thread_id: Thread ID to add message to
            message: Text message content
            image: Optional PIL Image object
            image_path: Optional path to image file

        Returns:
            Dictionary with message_id and optional file_id
        """
        try:
            # Start with text content
            content: list = [{"type": "text", "text": message}]
            uploaded_file_id: Optional[str] = None

            # Add image if provided
            if image is not None:
                # Save PIL image to temporary file and upload
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
                    image.save(tmp_file.name, format='PNG')
                    uploaded_file_id = self.upload_image_file(tmp_file.name)
                    os.unlink(tmp_file.name)  # Clean up temp file

                content.append({
                    "type": "image_file",
                    "image_file": {
                        "file_id": uploaded_file_id
                    }
                })
            elif image_path is not None:
                uploaded_file_id = self.upload_image_file(image_path)
                content.append({
                    "type": "image_file",
                    "image_file": {
                        "file_id": uploaded_file_id
                    }
                })

            message_obj = self.client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=content
            )

            self.logger.debug(f"Added message to thread {thread_id}: {message_obj.id}")
            return {
                "message_id": message_obj.id,
                "file_id": uploaded_file_id
            }

        except Exception as e:
            self.logger.error(f"Failed to add message to thread {thread_id}: {e}")
            raise

    def run_assistant(self, thread_id: str, assistant_id: str,
                     additional_instructions: Optional[str] = None,
                     reasoning_effort: Optional[str] = None) -> str:
        """Run the assistant on a thread.

        Args:
            thread_id: Thread ID to run assistant on
            assistant_id: Assistant ID to use
            additional_instructions: Optional additional instructions
            reasoning_effort: Optional reasoning effort for o-series models

        Returns:
            Run ID string
        """
        try:
            run_params: Dict[str, Any] = {
                "thread_id": thread_id,
                "assistant_id": assistant_id
            }

            if additional_instructions:
                run_params["additional_instructions"] = additional_instructions

            if reasoning_effort:
                run_params["reasoning_effort"] = reasoning_effort

            run = self.client.beta.threads.runs.create(**run_params)
            self.logger.debug(f"Started run {run.id} on thread {thread_id}")
            return run.id

        except Exception as e:
            self.logger.error(f"Failed to run assistant on thread {thread_id}: {e}")
            raise

    def wait_for_run_completion(self, thread_id: str, run_id: str,
                              timeout: int = 300, poll_interval: float = 1.0) -> Dict[str, Any]:
        """Wait for a run to complete and return the result.

        Args:
            thread_id: Thread ID
            run_id: Run ID to wait for
            timeout: Maximum time to wait in seconds
            poll_interval: Time between status checks in seconds

        Returns:
            Dictionary with run status and result
        """
        start_time = time.time()

        try:
            while time.time() - start_time < timeout:
                run = self.client.beta.threads.runs.retrieve(
                    thread_id=thread_id,
                    run_id=run_id
                )

                self.logger.debug(f"Run {run_id} status: {run.status}")

                if run.status == "completed":
                    # Get the assistant's response
                    messages = self.client.beta.threads.messages.list(
                        thread_id=thread_id,
                        order="desc",
                        limit=1
                    )

                    if messages.data:
                        # Handle different content types safely
                        content_block = messages.data[0].content[0]
                        # Check if content block has text attribute safely
                        if hasattr(content_block, 'text'):
                            text_attr = getattr(content_block, 'text', None)
                            if text_attr is not None and hasattr(text_attr, 'value'):
                                response_content = text_attr.value
                            else:
                                response_content = str(content_block)
                        else:
                            response_content = str(content_block)

                        return {
                            "status": "completed",
                            "response": response_content,
                            "run_id": run_id
                        }
                    else:
                        return {
                            "status": "completed",
                            "response": "",
                            "run_id": run_id
                        }

                elif run.status == "failed":
                    error_message = "Unknown error"
                    if run.last_error is not None:
                        error_message = getattr(run.last_error, 'message', 'Unknown error')
                    return {
                        "status": "failed",
                        "error": error_message,
                        "run_id": run_id
                    }

                elif run.status == "cancelled":
                    return {
                        "status": "cancelled",
                        "run_id": run_id
                    }

                elif run.status == "expired":
                    return {
                        "status": "expired",
                        "run_id": run_id
                    }

                elif run.status in ["queued", "in_progress", "requires_action"]:
                    # Handle requires_action if needed (for function calls, etc.)
                    if run.status == "requires_action":
                        self.logger.warning(f"Run {run_id} requires action - not implemented")
                        return {
                            "status": "requires_action",
                            "run_id": run_id,
                            "required_action": run.required_action
                        }

                    time.sleep(poll_interval)
                    continue

                else:
                    self.logger.warning(f"Unknown run status: {run.status}")
                    time.sleep(poll_interval)

            # Timeout reached
            return {
                "status": "timeout",
                "run_id": run_id,
                "error": f"Run did not complete within {timeout} seconds"
            }

        except Exception as e:
            self.logger.error(f"Error waiting for run completion: {e}")
            return {
                "status": "error",
                "run_id": run_id,
                "error": str(e)
            }

    def send_message(self, message: str, agent_id: str,
                    thread_id: Optional[str] = None,
                    image: Optional[Image.Image] = None,
                    image_path: Optional[str] = None,
                    additional_instructions: Optional[str] = None,
                    reasoning_effort: Optional[str] = None,
                    timeout: int = 300) -> Dict[str, Any]:
        """Send a message to an assistant and get the response.

        This is the main method that combines all the steps:
        1. Create thread if not provided
        2. Add message to thread (with optional image)
        3. Run assistant
        4. Wait for completion and return response

        Args:
            message: Text message to send
            agent_id: Assistant ID to use
            thread_id: Optional existing thread ID
            image: Optional PIL Image object
            image_path: Optional path to image file
            additional_instructions: Optional additional instructions
            timeout: Maximum time to wait for response

        Returns:
            Dictionary with response and metadata
        """
        try:
            # Create thread if not provided
            if thread_id is None:
                thread_id = self.create_thread()
            # Track thread under agent for later cleanup
            try:
                self._threads_by_agent.setdefault(agent_id, set()).add(str(thread_id))
            except Exception:
                pass

            # Add message to thread with optional image
            message_result = self.add_message_to_thread(
                thread_id=thread_id,
                message=message,
                image=image,
                image_path=image_path
            )
            message_id = message_result["message_id"]
            uploaded_file_id = message_result["file_id"]

            # Run assistant
            run_id = self.run_assistant(
                thread_id=thread_id,
                assistant_id=agent_id,
                additional_instructions=additional_instructions,
                reasoning_effort=reasoning_effort
            )

            # Wait for completion
            result = self.wait_for_run_completion(
                thread_id=thread_id,
                run_id=run_id,
                timeout=timeout
            )

            # Add metadata
            result.update({
                "thread_id": thread_id,
                "message_id": message_id,
                "agent_id": agent_id,
                "file_id": uploaded_file_id
            })

            return result

        except Exception as e:
            self.logger.error(f"Error in send_message: {e}")
            return {
                "status": "error",
                "error": str(e),
                "thread_id": thread_id,
                "agent_id": agent_id
            }

    def analyze_chart_for_autotrader(self, message: str, agent_id: str,
                                   image_path: str, symbol: str,
                                   timeframe: str = "1h",
                                   last_close_price: Optional[float] = None,
                                   timeout: int = 300,
                                   prompt_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Analyze chart and return autotrader-compatible JSON response.

        Args:
            message: Analysis message (optional, will use default if empty)
            agent_id: Assistant ID to use
            image_path: Path to chart image
            symbol: Trading symbol (e.g., ALGOUSDT)
            timeframe: Chart timeframe (e.g., 1h, 4h, 1d)
            last_close_price: Optional last close price
            timeout: Maximum time to wait for response
            prompt_data: Optional full prompt data including decision matrix

        Returns:
            Dictionary with autotrader-compatible format
        """
        try:
            # Create comprehensive analysis prompt
            #             Please analyze this {symbol} chart for the {timeframe} timeframe and provide a comprehensive trading analysis.

            # Analyze the chart for:
            # 1. Overall trend direction and strength
            # 2. Key support and resistance levels
            # 3. Entry, stop loss, and take profit recommendations
            # 4. Risk factors and market conditions
            # 5. Confidence level in your analysis
            # analysis_prompt = f"""


            # Return your analysis in this exact JSON format:
            # {{
            #     "recommendation": "buy" | "hold" | "sell",
            #     "summary": "Your detailed analysis summary here",
            #     "key_levels": {{
            #         "support": 0.0,
            #         "resistance": 0.0
            #     }},
            #     "risk_factors": ["List of risk factors"],
            #     "timeframe": "short_term" | "medium_term" | "long_term",
            #     "extracted_timeframe": "{timeframe}",
            #     "normalized_timeframe": "{timeframe}",
            #     "symbol": "{symbol}",
            #     "confidence": 0.0,
            #     "evidence": "Evidence supporting your recommendation",
            #     "last_close_price": {last_close_price if last_close_price else "null"},
            #     "entry_price": 0.0,
            #     "stop_loss": 0.0,
            #     "take_profit": 0.0,
            #     "trade_confidence": 0.0,
            #     "direction": "Long" | "Short"
            # }}

            # Make sure all numeric values are realistic based on the chart analysis.
            # """

            analysis_prompt = message + "\n Make sure all numeric values are realistic based on the chart analysis."

            # Get reasoning_effort from config if available
            reasoning_effort = None
            if self.config and hasattr(self.config, 'get_agent_config'):
                try:
                    analyzer_config = self.config.get_agent_config('analyzer')
                    reasoning_effort = getattr(analyzer_config, 'reasoning_effort', None)
                except:
                    pass

            # Discover assistant model for traceability
            assistant_model = None
            try:
                assistant_obj = self.client.beta.assistants.retrieve(agent_id)
                assistant_model = getattr(assistant_obj, 'model', None)
            except Exception:
                assistant_model = None

            # Send message with image
            result = self.send_message(
                message=analysis_prompt,
                agent_id=agent_id,
                image_path=image_path,
                reasoning_effort=reasoning_effort,
                timeout=timeout
            )

            if result.get('status') == 'completed':
                response_text = result.get('response', '')

                # Try to extract JSON from response
                import json
                import re

                # Look for JSON in the response
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    try:
                        analysis_data = json.loads(json_match.group())

                        # Ensure all required fields are present
                        required_fields = {
                            "recommendation": "hold",
                            "summary": response_text,
                            "key_levels": {"support": 0.0, "resistance": 0.0},
                            "risk_factors": ["Analysis unavailable"],
                            "timeframe": "short_term",
                            "extracted_timeframe": timeframe,
                            "normalized_timeframe": timeframe,
                            "symbol": symbol,
                            "confidence": 0.5,
                            "evidence": "Chart analysis",
                            "last_close_price": last_close_price,
                            "entry_price": None,  # Don't default to 0.0 - let downstream handle missing prices
                            "stop_loss": None,    # Don't default to 0.0 - let downstream handle missing prices
                            "take_profit": None,  # Don't default to 0.0 - let downstream handle missing prices
                            "trade_confidence": 0.5,
                            "direction": "Long"
                        }

                        # Fill in missing fields with defaults
                        for key, default_value in required_fields.items():
                            if key not in analysis_data:
                                analysis_data[key] = default_value

                        # Validate: if recommendation is buy/sell, price levels must be provided
                        recommendation = str(analysis_data.get("recommendation", "hold")).lower()
                        if recommendation in ["buy", "sell"]:
                            entry = analysis_data.get("entry_price")
                            sl = analysis_data.get("stop_loss")
                            tp = analysis_data.get("take_profit")

                            # Check if any price level is missing or zero
                            if not entry or not sl or not tp:
                                self.logger.warning(
                                    f"⚠️ AI returned '{recommendation}' but missing price levels: "
                                    f"entry={entry}, stop_loss={sl}, take_profit={tp}. "
                                    f"Downgrading to 'hold' to prevent invalid trades."
                                )
                                analysis_data["recommendation"] = "hold"
                                analysis_data["llm_original_recommendation"] = recommendation

                        # Apply decision matrix enforcement if enabled in prompt
                        if prompt_data and isinstance(prompt_data, dict):
                            decision_matrix = prompt_data.get('decision_matrix')
                            if decision_matrix and decision_matrix.get('enabled'):
                                try:
                                    confidence = float(analysis_data.get('confidence', 0))
                                    direction = str(analysis_data.get('direction', 'Long'))
                                    current_rec = str(analysis_data.get('recommendation', 'hold')).lower()

                                    min_conf = float(decision_matrix.get('rules', {}).get('min_confidence_for_trade', 0.60))

                                    if confidence >= min_conf:
                                        # Should be a trade (buy or sell based on direction)
                                        expected_rec = 'buy' if direction.lower() == 'long' else 'sell'
                                        if current_rec != expected_rec:
                                            analysis_data['llm_original_recommendation'] = current_rec
                                            analysis_data['recommendation'] = expected_rec
                                            self.logger.info(
                                                f"✅ Decision matrix enforced: confidence={confidence:.2f} >= {min_conf}, "
                                                f"direction={direction}, changed '{current_rec}' → '{expected_rec}'"
                                            )
                                    else:
                                        # Should be hold
                                        if current_rec != 'hold':
                                            analysis_data['llm_original_recommendation'] = current_rec
                                            analysis_data['recommendation'] = 'hold'
                                            self.logger.info(
                                                f"✅ Decision matrix enforced: confidence={confidence:.2f} < {min_conf}, "
                                                f"changed '{current_rec}' → 'hold'"
                                            )
                                except Exception as e:
                                    self.logger.warning(f"⚠️ Failed to apply decision matrix: {e}")

                        # Inject assistant metadata and raw response
                        analysis_data["assistant_id"] = agent_id
                        analysis_data["assistant_model"] = assistant_model
                        analysis_data["raw_response"] = response_text  # Store raw response for debugging/analysis

                        # Clean up thread and uploaded file
                        thread_id_val = result.get('thread_id')
                        if thread_id_val is not None:
                            self.delete_thread(str(thread_id_val))

                        # Clean up uploaded file
                        file_id_val = result.get('file_id')
                        if file_id_val is not None:
                            self.delete_uploaded_file(str(file_id_val))

                        return analysis_data

                    except json.JSONDecodeError:
                        self.logger.warning("Failed to parse JSON from assistant response")

                # Fallback: create structured response from text
                return {
                    "recommendation": "hold",
                    "summary": response_text,
                    "key_levels": {"support": 0.0, "resistance": 0.0},
                    "risk_factors": ["Manual analysis required"],
                    "timeframe": "short_term",
                    "extracted_timeframe": timeframe,
                    "normalized_timeframe": timeframe,
                    "symbol": symbol,
                    "confidence": 0.5,
                    "evidence": "Assistant analysis",
                    "last_close_price": last_close_price,
                    "entry_price": 0.0,
                    "stop_loss": 0.0,
                    "take_profit": 0.0,
                    "trade_confidence": 0.5,
                    "direction": "Long",
                    "assistant_id": agent_id,
                    "assistant_model": assistant_model,
                    "raw_response": response_text  # Store raw response for debugging/analysis
                }
            else:
                # Error case - try to clean up thread/file if present
                try:
                    thread_id_val = result.get('thread_id')
                    if thread_id_val is not None:
                        self.delete_thread(str(thread_id_val))
                    file_id_val = result.get('file_id')
                    if file_id_val is not None:
                        self.delete_uploaded_file(str(file_id_val))
                except Exception:
                    pass
                return {
                    "error": result.get('error', 'Analysis failed'),
                    "recommendation": "hold",
                    "summary": f"Analysis failed: {result.get('error', 'Unknown error')}",
                    "symbol": symbol,
                    "extracted_timeframe": timeframe,
                    "confidence": 0.0,
                    "assistant_id": agent_id,
                    "assistant_model": assistant_model
                }

        except Exception as e:
            self.logger.error(f"Error in analyze_chart_for_autotrader: {e}")
            return {
                "error": str(e),
                "recommendation": "hold",
                "summary": f"Analysis error: {str(e)}",
                "symbol": symbol,
                "extracted_timeframe": timeframe,
                "confidence": 0.0,
                "assistant_id": agent_id,
                "assistant_model": None
            }

    def delete_thread(self, thread_id: str) -> bool:
        """Delete a thread.

        Args:
            thread_id: Thread ID to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.beta.threads.delete(thread_id)
            self.logger.info(f"Deleted thread: {thread_id}")
            try:
                self._untrack_thread(str(thread_id))
            except Exception:
                pass
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete thread {thread_id}: {e}")
            return False

    def _untrack_thread(self, thread_id: str) -> None:
        """Remove a thread from local tracking maps if present."""
        try:
            for agent, tset in list(self._threads_by_agent.items()):
                if thread_id in tset:
                    tset.discard(thread_id)
                    if not tset:
                        self._threads_by_agent.pop(agent, None)
                    break
        except Exception:
            pass

    def cleanup_threads_for_agent(self, agent_id: str) -> int:
        """Delete all threads created via this handler for the given agent_id.
        Returns number of threads successfully deleted.
        """
        deleted = 0
        try:
            thread_ids = list(self._threads_by_agent.get(agent_id, set()))
            for tid in thread_ids:
                try:
                    self.client.beta.threads.delete(tid)
                    self.logger.info(f"Deleted thread: {tid}")
                    deleted += 1
                    self._untrack_thread(tid)
                except Exception as e:
                    self.logger.error(f"Failed to delete thread {tid}: {e}")
        except Exception:
            pass
        return deleted

    def cleanup_all_threads(self) -> int:
        """Best-effort delete of all tracked threads across all agents."""
        total = 0
        try:
            # Copy keys to avoid concurrent modification
            for agent_id in list(self._threads_by_agent.keys()):
                total += self.cleanup_threads_for_agent(agent_id)
        except Exception:
            pass
        return total


    def delete_all_assistant_files(self, include_vision_files: bool = True) -> int:
        """Delete all files with purpose 'assistants' (old image uploads).

        This method should be called by the autotrader at the end of each cycle
        to clean up old image uploads.

        Args:
            include_vision_files: If True, also delete vision files (chart images)

        Returns:
            Number of files deleted
        """
        total_deleted = 0

        try:
            # Delete assistant files
            self.logger.info("Deleting assistant files...")
            response = self.client.files.list(purpose="assistants")
            assistant_files = list(response.data)

            deleted_count = 0
            for file in assistant_files:
                try:
                    self.client.files.delete(file.id)
                    self.logger.debug(f"Deleted assistant file: {file.filename} [{file.id}]")
                    deleted_count += 1
                except Exception as e:
                    self.logger.error(f"Failed to delete assistant file {file.id}: {e}")
                    continue

            self.logger.info(f"Deleted {deleted_count} assistant files.")
            total_deleted += deleted_count

            # Delete vision files if requested
            if include_vision_files:
                self.logger.info("Deleting vision files...")
                response = self.client.files.list(purpose="vision")
                vision_files = list(response.data)

                deleted_count = 0
                for file in vision_files:
                    try:
                        self.client.files.delete(file.id)
                        self.logger.debug(f"Deleted vision file: {file.filename} [{file.id}]")
                        deleted_count += 1
                    except Exception as e:
                        self.logger.error(f"Failed to delete vision file {file.id}: {e}")
                        continue

                self.logger.info(f"Deleted {deleted_count} vision files.")
                total_deleted += deleted_count

            return total_deleted

        except Exception as e:
            self.logger.error(f"Failed to list or delete files: {e}")
            return total_deleted
