"""
Test numpy type conversion in database layer.
"""

import pytest
import numpy as np
from trading_bot.db.client import convert_numpy_types


class TestNumpyConversion:
    """Test convert_numpy_types function."""
    
    def test_convert_float64(self):
        """Test np.float64 conversion."""
        params = (np.float64(3.14159),)
        result = convert_numpy_types(params)
        assert isinstance(result[0], float)
        assert result[0] == pytest.approx(3.14159)
    
    def test_convert_float32(self):
        """Test np.float32 conversion."""
        params = (np.float32(2.71828),)
        result = convert_numpy_types(params)
        assert isinstance(result[0], float)
        assert result[0] == pytest.approx(2.71828, rel=1e-5)
    
    def test_convert_int64(self):
        """Test np.int64 conversion."""
        params = (np.int64(42),)
        result = convert_numpy_types(params)
        assert isinstance(result[0], int)
        assert result[0] == 42
    
    def test_convert_int32(self):
        """Test np.int32 conversion."""
        params = (np.int32(100),)
        result = convert_numpy_types(params)
        assert isinstance(result[0], int)
        assert result[0] == 100
    
    def test_convert_bool(self):
        """Test np.bool_ conversion."""
        params = (np.bool_(True), np.bool_(False))
        result = convert_numpy_types(params)
        assert isinstance(result[0], bool)
        assert isinstance(result[1], bool)
        assert result[0] is True
        assert result[1] is False
    
    def test_convert_ndarray(self):
        """Test np.ndarray conversion."""
        arr = np.array([1.0, 2.0, 3.0])
        params = (arr,)
        result = convert_numpy_types(params)
        assert isinstance(result[0], list)
        assert result[0] == [1.0, 2.0, 3.0]
    
    def test_convert_mixed_types(self):
        """Test conversion of mixed numpy and Python types."""
        params = (
            np.float64(3.14),
            42,
            "string",
            np.int64(100),
            3.14,
            None,
            np.bool_(True),
        )
        result = convert_numpy_types(params)
        
        assert isinstance(result[0], float)
        assert result[0] == pytest.approx(3.14)
        assert isinstance(result[1], int)
        assert result[1] == 42
        assert isinstance(result[2], str)
        assert result[2] == "string"
        assert isinstance(result[3], int)
        assert result[3] == 100
        assert isinstance(result[4], float)
        assert result[4] == pytest.approx(3.14)
        assert result[5] is None
        assert isinstance(result[6], bool)
        assert result[6] is True
    
    def test_convert_nested_tuple(self):
        """Test conversion of nested tuples."""
        params = (
            (np.float64(1.5), np.int64(10)),
            np.float64(2.5),
        )
        result = convert_numpy_types(params)
        
        assert isinstance(result[0], tuple)
        assert isinstance(result[0][0], float)
        assert isinstance(result[0][1], int)
        assert result[0][0] == pytest.approx(1.5)
        assert result[0][1] == 10
        assert isinstance(result[1], float)
        assert result[1] == pytest.approx(2.5)
    
    def test_convert_nested_list(self):
        """Test conversion of nested lists."""
        params = [
            [np.float64(1.5), np.int64(10)],
            np.float64(2.5),
        ]
        result = convert_numpy_types(params)
        
        assert isinstance(result, list)
        assert isinstance(result[0], list)
        assert isinstance(result[0][0], float)
        assert isinstance(result[0][1], int)
    
    def test_preserve_none(self):
        """Test that None values are preserved."""
        params = (None, np.float64(1.5), None)
        result = convert_numpy_types(params)
        
        assert result[0] is None
        assert isinstance(result[1], float)
        assert result[2] is None
    
    def test_empty_tuple(self):
        """Test empty tuple."""
        params = ()
        result = convert_numpy_types(params)
        assert result == ()
    
    def test_empty_list(self):
        """Test empty list."""
        params = []
        result = convert_numpy_types(params)
        assert result == []
    
    def test_real_world_trade_params(self):
        """Test with real-world trade recording parameters."""
        # Simulate parameters from _record_trade
        params = (
            "trade_123",  # id
            "rec_456",  # recommendation_id
            "run_789",  # run_id
            "cycle_000",  # cycle_id
            "BTCUSDT",  # symbol
            "Buy",  # side
            np.float64(50000.5),  # entry_price
            np.float64(49500.0),  # take_profit
            np.float64(49000.0),  # stop_loss
            np.float64(0.01),  # quantity
            "submitted",  # status
            "order_123",  # order_id
            np.float64(0.85),  # confidence
            np.float64(2.5),  # rr_ratio
            "1h",  # timeframe
            False,  # dry_run
            "2025-12-20T06:45:00Z",  # created_at
        )
        
        result = convert_numpy_types(params)
        
        # Verify all numpy types are converted
        assert isinstance(result[6], float)  # entry_price
        assert isinstance(result[7], float)  # take_profit
        assert isinstance(result[8], float)  # stop_loss
        assert isinstance(result[9], float)  # quantity
        assert isinstance(result[12], float)  # confidence
        assert isinstance(result[13], float)  # rr_ratio
        assert isinstance(result[15], bool)  # dry_run
        
        # Verify values are correct
        assert result[6] == pytest.approx(50000.5)
        assert result[7] == pytest.approx(49500.0)
        assert result[8] == pytest.approx(49000.0)
        assert result[12] == pytest.approx(0.85)

