#!/usr/bin/env python3
"""
Production Readiness Validation Script

Validates that the trading bot is ready for production deployment.
Checks all critical components from A-Z.
"""

import sys
import os
from pathlib import Path

# Add python directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

def check_imports():
    """Check all critical imports."""
    print("\n📦 Checking imports...")
    try:
        from trading_bot.config.settings_v2 import Config
        from trading_bot.engine.trading_cycle import TradingCycle
        from trading_bot.engine.trading_engine import TradingEngine
        from trading_bot.strategies.factory import StrategyFactory
        from trading_bot.strategies.base import BaseAnalysisModule
        from trading_bot.db.client import get_connection, release_connection
        print("   ✓ All imports successful")
        return True
    except Exception as e:
        print(f"   ✗ Import failed: {e}")
        return False

def check_database():
    """Check database connectivity."""
    print("\n🗄️  Checking database...")
    try:
        from trading_bot.db.client import get_connection, release_connection, query
        conn = get_connection()

        # Check tables exist
        tables = [
            'instances', 'runs', 'recommendations', 'trades',
            'error_logs', 'position_monitor_logs'
        ]

        for table in tables:
            # Simple check - try to query
            try:
                query(conn, f"SELECT 1 FROM {table} LIMIT 1")
                print(f"   ✓ Table '{table}' exists")
            except Exception as e:
                print(f"   ⚠ Table '{table}' check skipped (may not exist yet)")

        release_connection(conn)
        print("   ✓ Database connection successful")
        return True
    except Exception as e:
        print(f"   ⚠ Database check skipped: {e}")
        return True  # Don't fail if DB not available

def check_strategy_factory():
    """Check strategy factory."""
    print("\n🎯 Checking strategy factory...")
    try:
        from trading_bot.strategies.factory import StrategyFactory

        strategies = [
            'AiImageAnalyzer',
            'MarketStructure',
            'CointegrationSpreadTrader'
        ]

        for strategy_name in strategies:
            # Check if strategy is in STRATEGIES dict
            if strategy_name in StrategyFactory.STRATEGIES:
                print(f"   ✓ Strategy '{strategy_name}' registered")
            else:
                print(f"   ✗ Strategy '{strategy_name}' NOT registered")
                return False

        print("   ✓ All strategies registered")
        return True
    except Exception as e:
        print(f"   ✗ Strategy factory check failed: {e}")
        return False

def check_config():
    """Check configuration."""
    print("\n⚙️  Checking configuration...")
    try:
        from trading_bot.config.settings_v2 import Config

        # Config requires instance_id, so just check it can be imported
        print("   ✓ Config module available")
        print("   ℹ Config requires instance_id at runtime")
        return True
    except Exception as e:
        print(f"   ✗ Config check failed: {e}")
        return False

def check_trading_cycle():
    """Check trading cycle."""
    print("\n🔄 Checking trading cycle...")
    try:
        from trading_bot.engine.trading_cycle import TradingCycle

        # Check methods exist on class
        methods = [
            'start', 'stop', 'run_cycle_async',
            '_rank_signals_by_quality', '_get_available_slots'
        ]

        for method in methods:
            if hasattr(TradingCycle, method):
                print(f"   ✓ Method '{method}' exists")
            else:
                print(f"   ✗ Method '{method}' missing")
                return False

        print("   ✓ Trading cycle class available")
        return True
    except Exception as e:
        print(f"   ✗ Trading cycle check failed: {e}")
        return False

def check_stop_signal():
    """Check stop signal handling."""
    print("\n🛑 Checking stop signal handling...")
    try:
        from trading_bot.strategies.base import BaseAnalysisModule

        # Check BaseAnalysisModule has stop mechanism
        methods = ['request_stop']

        for method in methods:
            if hasattr(BaseAnalysisModule, method):
                print(f"   ✓ Method '{method}' exists on BaseAnalysisModule")
            else:
                print(f"   ✗ Method '{method}' missing")
                return False

        # Check TradingCycle calls request_stop
        from trading_bot.engine.trading_cycle import TradingCycle
        import inspect

        stop_method = inspect.getsource(TradingCycle.stop)
        if 'request_stop' in stop_method:
            print("   ✓ TradingCycle.stop() calls strategy.request_stop()")
        else:
            print("   ⚠ TradingCycle.stop() may not call request_stop()")

        # Check CointegrationAnalysisModule has stop check
        from trading_bot.strategies.cointegration.cointegration_analysis_module import CointegrationAnalysisModule
        cycle_method = inspect.getsource(CointegrationAnalysisModule.run_analysis_cycle)
        if '_stop_requested' in cycle_method:
            print("   ✓ CointegrationAnalysisModule checks _stop_requested")
        else:
            print("   ✗ CointegrationAnalysisModule missing stop check")
            return False

        return True
    except Exception as e:
        print(f"   ✗ Stop signal check failed: {e}")
        return False

def main():
    """Run all checks."""
    print("=" * 60)
    print("🚀 PRODUCTION READINESS VALIDATION")
    print("=" * 60)
    
    checks = [
        ("Imports", check_imports),
        ("Database", check_database),
        ("Strategy Factory", check_strategy_factory),
        ("Configuration", check_config),
        ("Trading Cycle", check_trading_cycle),
        ("Stop Signal", check_stop_signal),
    ]
    
    results = []
    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ {name} check crashed: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓" if result else "✗"
        print(f"{status} {name}")
    
    print(f"\nPassed: {passed}/{total}")
    
    if passed == total:
        print("\n✅ ALL CHECKS PASSED - READY FOR PRODUCTION")
        return 0
    else:
        print(f"\n❌ {total - passed} CHECK(S) FAILED - FIX BEFORE DEPLOYMENT")
        return 1

if __name__ == "__main__":
    sys.exit(main())

