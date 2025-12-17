"""Tests for reproducibility data capture in analysis and execution phases."""

import pytest
import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

# Add python directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from trading_bot.strategies.base import BaseAnalysisModule
from trading_bot.strategies.prompt.prompt_strategy import PromptStrategy


class TestReproducibilityDataCapture:
    """Test reproducibility data capture functionality."""

    @pytest.fixture
    def mock_strategy(self):
        """Create a mock strategy for testing."""
        with patch('trading_bot.strategies.prompt.prompt_strategy.ChartSourcer'), \
             patch('trading_bot.strategies.prompt.prompt_strategy.ChartCleaner'), \
             patch('trading_bot.strategies.prompt.prompt_strategy.ChartAnalyzer'), \
             patch('trading_bot.strategies.prompt.prompt_strategy.BybitAPIManager'), \
             patch('trading_bot.strategies.prompt.prompt_strategy.OpenAI'):
            
            mock_config = Mock()
            mock_config.openai = Mock(model='gpt-4-vision')
            mock_config.trading = Mock()
            
            strategy = PromptStrategy(config=mock_config, instance_id='test_instance')
            return strategy

    def test_capture_reproducibility_data_with_all_fields(self, mock_strategy):
        """Test capturing all reproducibility data fields."""
        analysis_result = {
            "recommendation": "LONG",
            "confidence": 0.85,
            "entry_price": 100.0,
            "stop_loss": 99.0,
            "take_profit": 102.0,
            "confidence_components": {"trend": 0.8, "support": 0.9},
            "setup_quality_components": {"pattern": 0.85, "volume": 0.8},
            "market_environment_components": {"volatility": 0.6, "trend_strength": 0.7},
            "validation_results": {"price_sanity": True, "levels_valid": True},
        }
        
        market_data = {
            "symbol": "BTCUSDT",
            "last_price": 100.5,
            "volume_24h": 1000000,
            "candles": [{"open": 99, "high": 101, "low": 98, "close": 100}],
        }
        
        reproducibility_data = mock_strategy.capture_reproducibility_data(
            analysis_result=analysis_result,
            chart_path=None,
            market_data=market_data,
            model_version="gpt-4-vision",
            model_params={"temperature": 0.7, "max_tokens": 2000},
            prompt_version="1.0",
            prompt_content="Analyze this chart...",
        )
        
        # Verify all fields are captured
        assert reproducibility_data["model_version"] == "gpt-4-vision"
        assert reproducibility_data["model_params"]["temperature"] == 0.7
        assert reproducibility_data["market_data_snapshot"]["symbol"] == "BTCUSDT"
        assert reproducibility_data["confidence_components"]["trend"] == 0.8
        assert reproducibility_data["setup_quality_components"]["pattern"] == 0.85
        assert reproducibility_data["market_environment_components"]["volatility"] == 0.6
        assert reproducibility_data["validation_results"]["price_sanity"] is True
        assert reproducibility_data["prompt_version"] == "1.0"
        assert reproducibility_data["prompt_content"] == "Analyze this chart..."

    def test_capture_reproducibility_data_with_chart_hash(self, mock_strategy, tmp_path):
        """Test capturing chart hash for reproducibility."""
        # Create a temporary chart file
        chart_file = tmp_path / "test_chart.png"
        chart_file.write_bytes(b"fake chart data")
        
        analysis_result = {
            "recommendation": "LONG",
            "confidence": 0.85,
        }
        
        reproducibility_data = mock_strategy.capture_reproducibility_data(
            analysis_result=analysis_result,
            chart_path=str(chart_file),
            market_data={},
            model_version="gpt-4-vision",
        )
        
        # Verify chart hash is captured
        assert "chart_hash" in reproducibility_data
        assert len(reproducibility_data["chart_hash"]) == 32  # MD5 hash length

    def test_capture_reproducibility_data_handles_missing_fields(self, mock_strategy):
        """Test that missing fields are handled gracefully."""
        analysis_result = {
            "recommendation": "LONG",
            "confidence": 0.85,
        }

        reproducibility_data = mock_strategy.capture_reproducibility_data(
            analysis_result=analysis_result,
            chart_path=None,
            market_data=None,
            model_version=None,
        )

        # Verify defaults are used for missing fields
        assert reproducibility_data["model_version"] == "unknown"
        assert reproducibility_data["model_params"] == {}
        assert reproducibility_data["market_data_snapshot"] == {}
        # Optional fields should not be present if not in analysis_result
        assert "confidence_components" not in reproducibility_data or reproducibility_data["confidence_components"] == {}

    def test_capture_reproducibility_data_preserves_strategy_config(self, mock_strategy):
        """Test that strategy config is captured for reproducibility."""
        analysis_result = {"recommendation": "LONG", "confidence": 0.85}
        
        reproducibility_data = mock_strategy.capture_reproducibility_data(
            analysis_result=analysis_result,
            chart_path=None,
            market_data={},
            model_version="gpt-4-vision",
        )
        
        # Verify strategy config is captured
        assert "strategy_config_snapshot" in reproducibility_data
        assert isinstance(reproducibility_data["strategy_config_snapshot"], dict)

    def test_capture_reproducibility_data_json_serializable(self, mock_strategy):
        """Test that captured data is JSON serializable."""
        analysis_result = {
            "recommendation": "LONG",
            "confidence": 0.85,
            "confidence_components": {"trend": 0.8},
            "setup_quality_components": {"pattern": 0.85},
            "market_environment_components": {"volatility": 0.6},
        }
        
        reproducibility_data = mock_strategy.capture_reproducibility_data(
            analysis_result=analysis_result,
            chart_path=None,
            market_data={"symbol": "BTCUSDT"},
            model_version="gpt-4-vision",
            model_params={"temperature": 0.7},
        )
        
        # Verify all data is JSON serializable
        json_str = json.dumps(reproducibility_data, default=str)
        assert json_str is not None
        
        # Verify we can deserialize it back
        deserialized = json.loads(json_str)
        assert deserialized["model_version"] == "gpt-4-vision"

