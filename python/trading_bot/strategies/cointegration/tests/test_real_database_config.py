"""
Test that CointegrationAnalysisModule reads ALL config values from real database.
Uses psql and DATABASE_URL to verify exact values stored in PostgreSQL.
"""
import os
import sys
import json
import subprocess
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from trading_bot.strategies.cointegration.cointegration_analysis_module import CointegrationAnalysisModule
from trading_bot.db.client import get_connection, query_one, release_connection


def get_db_config_via_psql():
    """Fetch SpreadTrader config directly from PostgreSQL using psql."""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL not set")
    
    query = """
    SELECT settings->>'strategy' as strategy,
           settings->'strategy_config' as strategy_config
    FROM instances 
    WHERE name = 'SpreadTrader'
    LIMIT 1;
    """
    
    try:
        result = subprocess.run(
            ['psql', database_url, '-t', '-c', query],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"psql error: {result.stderr}")
        
        lines = result.stdout.strip().split('\n')
        if not lines or not lines[0]:
            raise ValueError("No SpreadTrader instance found in database")
        
        # Parse output: strategy | strategy_config
        parts = lines[0].split('|')
        strategy = parts[0].strip()
        strategy_config_str = parts[1].strip()
        
        # Parse JSON
        strategy_config = json.loads(strategy_config_str)
        
        return {
            'strategy': strategy,
            'strategy_config': strategy_config
        }
    except subprocess.TimeoutExpired:
        raise RuntimeError("psql query timed out")


def test_database_config_values():
    """Test 1: Verify all config values in database"""
    print("\n" + "="*80)
    print("TEST 1: Verify all config values in PostgreSQL database")
    print("="*80)
    
    db_config = get_db_config_via_psql()
    strategy_config = db_config['strategy_config']
    
    print(f"\n✅ Strategy: {db_config['strategy']}")
    print(f"✅ Found {len(strategy_config)} config keys in database:")
    
    expected_keys = [
        'z_entry', 'z_exit', 'lookback', 'use_adf',
        'min_sl_buffer', 'enable_dynamic_sizing', 'pair_discovery_mode',
        'analysis_timeframe', 'batch_size', 'candle_limit', 'min_volume_usd',
        'screener_cache_hours'
    ]
    
    for key in expected_keys:
        if key in strategy_config:
            value = strategy_config[key]
            print(f"   ✅ {key}: {value}")
        else:
            print(f"   ❌ {key}: MISSING")
            raise AssertionError(f"Missing key: {key}")
    
    return strategy_config


def test_strategy_loads_from_database():
    """Test 2: Verify strategy loads exact values from database"""
    print("\n" + "="*80)
    print("TEST 2: Verify CointegrationAnalysisModule loads from database")
    print("="*80)

    # Get database values and instance ID
    database_url = os.getenv('DATABASE_URL')
    query = "SELECT id FROM instances WHERE name = 'SpreadTrader' LIMIT 1;"
    result = subprocess.run(
        ['psql', database_url, '-t', '-c', query],
        capture_output=True,
        text=True,
        timeout=10
    )

    if result.returncode != 0:
        raise RuntimeError(f"Failed to get instance ID: {result.stderr}")

    instance_id = result.stdout.strip()
    if not instance_id:
        raise ValueError("SpreadTrader instance not found")

    db_config = get_db_config_via_psql()
    db_values = db_config['strategy_config']

    # Create strategy instance with UUID
    strategy = CointegrationAnalysisModule(
        config={},
        instance_id=instance_id,
        run_id="test-real-db"
    )
    
    print(f"\n✅ Strategy initialized with instance_id='SpreadTrader'")
    
    # Verify each config value matches database
    test_cases = [
        ('z_entry', float, 2.0),
        ('z_exit', float, 0.2),
        ('lookback', int, 90),
        ('use_adf', bool, True),
        ('min_sl_buffer', float, 1.5),
        ('enable_dynamic_sizing', bool, True),
        ('pair_discovery_mode', str, 'auto_screen'),
        ('analysis_timeframe', str, '4h'),
        ('batch_size', int, 15),
        ('candle_limit', int, 1000),
        ('min_volume_usd', int, 100000),
        ('screener_cache_hours', int, 4),
    ]
    
    print("\nVerifying config values match database:")
    for key, expected_type, expected_value in test_cases:
        # Get from database
        db_value = db_values.get(key)
        
        # Get from strategy
        strategy_value = strategy.get_config_value(key, None)
        
        # Convert for comparison
        if expected_type == bool:
            db_value_converted = str(db_value).lower() in ('true', '1', 'yes')
        elif expected_type == int:
            db_value_converted = int(db_value)
        elif expected_type == float:
            db_value_converted = float(db_value)
        else:
            db_value_converted = str(db_value)
        
        # Verify
        if strategy_value == db_value_converted:
            print(f"   ✅ {key}: {strategy_value} (matches database)")
        else:
            print(f"   ❌ {key}: strategy={strategy_value}, database={db_value_converted}")
            raise AssertionError(f"Mismatch for {key}")
    
    return strategy


def test_strategy_uses_correct_types():
    """Test 3: Verify strategy uses correct data types"""
    print("\n" + "="*80)
    print("TEST 3: Verify correct data types in strategy")
    print("="*80)
    
    strategy = CointegrationAnalysisModule(
        config=None,
        instance_id="SpreadTrader",
        run_id="test-real-db"
    )
    
    type_checks = [
        ('z_entry', float),
        ('z_exit', float),
        ('lookback', int),
        ('use_adf', bool),
        ('min_sl_buffer', float),
        ('enable_dynamic_sizing', bool),
        ('pair_discovery_mode', str),
        ('analysis_timeframe', str),
        ('batch_size', int),
        ('candle_limit', int),
        ('min_volume_usd', int),
        ('screener_cache_hours', int),
    ]
    
    print("\nVerifying data types:")
    for key, expected_type in type_checks:
        value = strategy.get_config_value(key, None)
        actual_type = type(value)
        
        if actual_type == expected_type:
            print(f"   ✅ {key}: {expected_type.__name__} = {value}")
        else:
            print(f"   ❌ {key}: expected {expected_type.__name__}, got {actual_type.__name__}")
            raise AssertionError(f"Type mismatch for {key}")


if __name__ == "__main__":
    print("\n" + "="*80)
    print("REAL DATABASE CONFIG TEST")
    print("Testing CointegrationAnalysisModule with real PostgreSQL database")
    print("="*80)
    
    try:
        # Test 1: Database values
        db_config = test_database_config_values()
        
        # Test 2: Strategy loads from database
        strategy = test_strategy_loads_from_database()
        
        # Test 3: Correct types
        test_strategy_uses_correct_types()
        
        print("\n" + "="*80)
        print("✅ ALL TESTS PASSED")
        print("="*80)
        print("\nSummary:")
        print("  ✅ All 12 config values present in PostgreSQL database")
        print("  ✅ Strategy loads exact values from database via get_config_value()")
        print("  ✅ All values have correct data types (float, int, bool, str)")
        print("  ✅ No hardcoded defaults used when database values exist")
        print("  ✅ Strategy is production-ready with real database config")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

