"""
Raw Output Logger for Image Backtest

Captures complete raw outputs from each analysis during backtest runs.
Creates one file per run containing:
- Run configuration (prompts, symbols, images, etc.)
- Each analysis with prompt name, image name, and complete model output
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class RawOutputLogger:
    """Logs raw model outputs from backtest analyses to files."""
    
    def __init__(self, output_dir: str = "prompt_performance/raw_outputs"):
        """
        Initialize the raw output logger.
        
        Args:
            output_dir: Directory to store raw output files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.current_file: Optional[Path] = None
        self.current_run_id: Optional[int] = None
        
    def start_run(
        self,
        run_id: int,
        config: Dict[str, Any]
    ) -> None:
        """
        Start a new run and create output file.
        
        Args:
            run_id: Unique run identifier
            config: Run configuration (prompts, symbols, num_images, etc.)
        """
        self.current_run_id = run_id
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"run_{run_id}_{timestamp}.txt"
        self.current_file = self.output_dir / filename
        
        # Write header with configuration
        with open(self.current_file, 'w', encoding='utf-8') as f:
            f.write("=" * 100 + "\n")
            f.write(f"BACKTEST RUN #{run_id}\n")
            f.write(f"Started: {datetime.now().isoformat()}\n")
            f.write("=" * 100 + "\n\n")
            
            f.write("CONFIGURATION:\n")
            f.write("-" * 100 + "\n")
            for key, value in config.items():
                if isinstance(value, (list, dict)):
                    f.write(f"{key}:\n")
                    f.write(f"  {json.dumps(value, indent=2)}\n")
                else:
                    f.write(f"{key}: {value}\n")
            f.write("-" * 100 + "\n\n")
            
        logger.info(f"📝 Raw output logging started: {self.current_file}")
    
    def log_analysis(
        self,
        prompt_name: str,
        image_name: str,
        symbol: str,
        timeframe: str,
        timestamp: str,
        raw_output: Any,
        analysis_result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ) -> None:
        """
        Log a single analysis output.
        
        Args:
            prompt_name: Name of the prompt function used
            image_name: Name of the image file analyzed
            symbol: Trading symbol
            timeframe: Chart timeframe
            timestamp: Image timestamp
            raw_output: Complete raw output from the model
            analysis_result: Parsed analysis result (optional)
            error: Error message if analysis failed (optional)
        """
        if self.current_file is None:
            logger.warning("No active run - cannot log analysis")
            return
            
        try:
            with open(self.current_file, 'a', encoding='utf-8') as f:
                f.write("\n" + "=" * 100 + "\n")
                f.write(f"ANALYSIS #{self._get_analysis_count() + 1}\n")
                f.write("=" * 100 + "\n")
                f.write(f"Prompt: {prompt_name}\n")
                f.write(f"Image: {image_name}\n")
                f.write(f"Symbol: {symbol}\n")
                f.write(f"Timeframe: {timeframe}\n")
                f.write(f"Timestamp: {timestamp}\n")
                f.write(f"Analyzed at: {datetime.now().isoformat()}\n")
                f.write("-" * 100 + "\n\n")
                
                if error:
                    f.write("❌ ERROR:\n")
                    f.write(f"{error}\n\n")
                
                f.write("RAW MODEL OUTPUT:\n")
                f.write("-" * 100 + "\n")
                
                # Handle different types of raw output
                if isinstance(raw_output, str):
                    f.write(raw_output + "\n")
                elif isinstance(raw_output, (dict, list)):
                    f.write(json.dumps(raw_output, indent=2) + "\n")
                else:
                    f.write(str(raw_output) + "\n")
                    
                f.write("-" * 100 + "\n")
                
                if analysis_result:
                    f.write("\nPARSED RESULT:\n")
                    f.write("-" * 100 + "\n")
                    f.write(json.dumps(analysis_result, indent=2) + "\n")
                    f.write("-" * 100 + "\n")
                
                f.write("\n")
                
        except Exception as e:
            logger.error(f"Failed to log analysis output: {e}")
    
    def end_run(self, summary: Optional[Dict[str, Any]] = None) -> None:
        """
        End the current run and write summary.
        
        Args:
            summary: Optional run summary (metrics, etc.)
        """
        if self.current_file is None:
            return
            
        try:
            with open(self.current_file, 'a', encoding='utf-8') as f:
                f.write("\n" + "=" * 100 + "\n")
                f.write("RUN COMPLETED\n")
                f.write("=" * 100 + "\n")
                f.write(f"Finished: {datetime.now().isoformat()}\n")
                f.write(f"Total analyses: {self._get_analysis_count()}\n")
                
                if summary:
                    f.write("\nSUMMARY:\n")
                    f.write("-" * 100 + "\n")
                    f.write(json.dumps(summary, indent=2) + "\n")
                    f.write("-" * 100 + "\n")
                
                f.write("\n")
                
            logger.info(f"✅ Raw output logging completed: {self.current_file}")
            
        except Exception as e:
            logger.error(f"Failed to end run logging: {e}")
        finally:
            self.current_file = None
            self.current_run_id = None
    
    def _get_analysis_count(self) -> int:
        """Count number of analyses logged in current file."""
        if self.current_file is None or not self.current_file.exists():
            return 0
            
        try:
            with open(self.current_file, 'r', encoding='utf-8') as f:
                content = f.read()
                # Count "ANALYSIS #" occurrences
                return content.count("ANALYSIS #")
        except Exception:
            return 0
    
    def get_output_file(self) -> Optional[Path]:
        """Get the current output file path."""
        return self.current_file

