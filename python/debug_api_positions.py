#!/usr/bin/env python3
"""
Debug script to diagnose Bybit API position fetch errors.

This script tests the API connection and provides detailed error information.
"""
import sys
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load .env.local from project root (unified env file)
env_path = project_root.parent / '.env.local'
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ Loaded environment from: {env_path}")
else:
    load_dotenv()  # Fallback to default .env lookup
    print("⚠️  Using default .env lookup")

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

def main():
    """Run diagnostic tests on Bybit API connection."""
    logger.info("=" * 60)
    logger.info("Bybit API Position Fetch Diagnostic")
    logger.info("=" * 60)
    
    # Step 1: Check environment variables
    logger.info("\n1. Checking environment variables...")
    api_key = os.getenv('BYBIT_API_KEY')
    api_secret = os.getenv('BYBIT_API_SECRET')
    
    if not api_key:
        logger.error("❌ BYBIT_API_KEY not found in environment")
    else:
        key_preview = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "***"
        logger.info(f"✅ BYBIT_API_KEY found: {key_preview}")
    
    if not api_secret:
        logger.error("❌ BYBIT_API_SECRET not found in environment")
    else:
        logger.info(f"✅ BYBIT_API_SECRET found: {len(api_secret)} characters")
    
    if not api_key or not api_secret:
        logger.error("\n❌ Missing API credentials. Cannot proceed with API tests.")
        logger.info("Please set BYBIT_API_KEY and BYBIT_API_SECRET environment variables.")
        return 1
    
    # Step 2: Test Bybit API directly
    logger.info("\n2. Testing Bybit API connection directly...")
    try:
        from pybit.unified_trading import HTTP

        # Get credentials
        from trading_bot.core.secrets_manager import get_bybit_credentials
        api_key, api_secret = get_bybit_credentials()

        # Create session
        testnet = os.getenv('BYBIT_TESTNET', 'false').lower() == 'true'
        logger.info(f"Creating Bybit session (testnet={testnet})...")

        session = HTTP(
            testnet=testnet,
            api_key=api_key,
            api_secret=api_secret,
            recv_window=60000,
            timeout=30,
        )

        logger.info("✅ Bybit session created successfully")

    except Exception as e:
        logger.error(f"❌ Failed to create Bybit session: {e}", exc_info=True)
        return 1

    # Step 3: Test get_positions
    logger.info("\n3. Testing get_positions() API call...")
    try:
        response = session.get_positions(
            category="linear",
            settleCoin="USDT",
        )

        logger.info(f"Response type: {type(response)}")
        logger.info(f"Response keys: {response.keys() if isinstance(response, dict) else 'N/A'}")

        ret_code = response.get('retCode', 'N/A')
        ret_msg = response.get('retMsg', 'N/A')
        error = response.get('error', '')

        logger.info(f"retCode: {ret_code}")
        logger.info(f"retMsg: {ret_msg}")
        if error:
            logger.info(f"error: {error}")

        if ret_code == 0:
            logger.info("✅ API call successful!")
            positions = response.get('result', {}).get('list', [])
            logger.info(f"   - Found {len(positions)} positions")
            for pos in positions:
                symbol = pos.get('symbol')
                size = pos.get('size')
                side = pos.get('side')
                logger.info(f"   - {symbol}: {side} {size}")
        else:
            logger.error(f"❌ API call failed: retCode={ret_code}, retMsg={ret_msg}")
            logger.debug(f"Full response: {response}")

    except Exception as e:
        logger.error(f"❌ Exception during get_positions: {type(e).__name__}: {e}", exc_info=True)
        return 1
    
    # Step 4: Test get_positions
    logger.info("\n4. Testing get_positions() API call...")
    try:
        response = api_manager.get_positions()
        
        logger.info(f"Response type: {type(response)}")
        logger.info(f"Response keys: {response.keys() if isinstance(response, dict) else 'N/A'}")
        
        ret_code = response.get('retCode', 'N/A')
        ret_msg = response.get('retMsg', 'N/A')
        error = response.get('error', '')
        
        logger.info(f"retCode: {ret_code}")
        logger.info(f"retMsg: {ret_msg}")
        if error:
            logger.info(f"error: {error}")
        
        if ret_code == 0:
            logger.info("✅ API call successful!")
            positions = response.get('result', {}).get('list', [])
            logger.info(f"   - Found {len(positions)} positions")
            for pos in positions:
                symbol = pos.get('symbol')
                size = pos.get('size')
                side = pos.get('side')
                logger.info(f"   - {symbol}: {side} {size}")
        else:
            logger.error(f"❌ API call failed: retCode={ret_code}, retMsg={ret_msg}")
            logger.debug(f"Full response: {response}")
            
    except Exception as e:
        logger.error(f"❌ Exception during get_positions: {type(e).__name__}: {e}", exc_info=True)
        return 1
    
    # Step 5: Test get_open_orders
    logger.info("\n5. Testing get_open_orders() API call...")
    try:
        response = api_manager.get_open_orders()
        
        ret_code = response.get('retCode', 'N/A')
        ret_msg = response.get('retMsg', 'N/A')
        
        logger.info(f"retCode: {ret_code}")
        logger.info(f"retMsg: {ret_msg}")
        
        if ret_code == 0:
            logger.info("✅ API call successful!")
            orders = response.get('result', {}).get('list', [])
            logger.info(f"   - Found {len(orders)} orders")
        else:
            logger.error(f"❌ API call failed: retCode={ret_code}, retMsg={ret_msg}")
            
    except Exception as e:
        logger.error(f"❌ Exception during get_open_orders: {type(e).__name__}: {e}", exc_info=True)
        return 1
    
    logger.info("\n" + "=" * 60)
    logger.info("Diagnostic complete!")
    logger.info("=" * 60)
    return 0

if __name__ == "__main__":
    sys.exit(main())

