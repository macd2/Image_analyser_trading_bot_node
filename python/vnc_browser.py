#!/usr/bin/env python3
"""
Interactive Browser Launcher - Launches a visible browser window for manual TradingView login.
Purpose: Manual session capture for later automated use.
Does NOT take screenshots (the browser is visible on desktop).
Session is saved to database when browser is closed.
"""
import signal
import sys
import asyncio
import json
import time
from pathlib import Path
from datetime import datetime

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from trading_bot.db.client import get_connection, execute, query_one, get_boolean_comparison, get_boolean_value, DB_TYPE


class InteractiveBrowser:
    def __init__(self):
        self.context = None
        self.browser = None
        self.page = None
        self.playwright = None
        self.running = True
        self.tv_config = None

    async def start_browser(self):
        """Start browser for manual login - uses same settings as sourcer but NO screenshots."""
        print("🚀 Launching interactive browser for manual login...")
        print("="*60)
        print("⚠️  This browser is for MANUAL LOGIN ONLY")
        print("   - Log in to TradingView manually")
        print("   - Session will be saved when you close this browser")
        print("   - NO screenshots are taken (browser is visible)")
        print("="*60 + "\n")

        from trading_bot.config.settings_v2 import ConfigV2
        from playwright.async_api import async_playwright

        # Get first active instance
        conn = None
        try:
            conn = get_connection()
            is_active_check = get_boolean_comparison('is_active', True)
            first_instance = query_one(conn, f"SELECT id FROM instances WHERE {is_active_check} LIMIT 1", ())
        finally:
            # Always release connection back to pool (PostgreSQL) or close (SQLite)
            if conn is not None:
                release_connection(conn)

        if not first_instance:
            raise Exception("No active instance found. Please create and activate an instance in the dashboard.")

        instance_id = first_instance.get('id') if isinstance(first_instance, dict) else first_instance[0]
        config = ConfigV2.from_instance(instance_id)
        self.tv_config = config.tradingview

        try:
            self.playwright = await async_playwright().start()

            # Use EXACT same browser args as sourcer for consistency
            browser_args = [
                '--disable-blink-features=AutomationControlled',
                '--disable-automation',
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-setuid-sandbox',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-infobars',
                f'--window-size={self.tv_config.browser.viewport_width},{self.tv_config.browser.viewport_height}',
                '--start-maximized',
                '--window-position=0,0',
            ]

            print("🔧 Launching Chromium (non-headless for manual login)...")
            self.browser = await self.playwright.chromium.launch(
                headless=False,  # Always visible for manual login
                args=browser_args
            )

            # Create context with same settings as sourcer
            self.context = await self.browser.new_context(
                viewport={
                    'width': self.tv_config.browser.viewport_width,
                    'height': self.tv_config.browser.viewport_height
                },
                user_agent=self.tv_config.browser.user_agent,
                java_script_enabled=True,
                locale='en-US',
                timezone_id='America/New_York',
                bypass_csp=True,
                ignore_https_errors=True
            )

            # Load existing session cookies if any
            await self._load_existing_session()

            # Create page
            self.page = await self.context.new_page()

            # Anti-detection scripts (same as sourcer)
            await self.page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                window.chrome = { runtime: {} };
            """)

            # Navigate to login page (NOT target chart - let user decide where to go)
            login_url = self.tv_config.login_url or "https://www.tradingview.com/accounts/signin/"
            print(f"🌐 Navigating to login page: {login_url}")
            await self.page.goto(login_url, timeout=60000)
            await self.page.wait_for_load_state('networkidle', timeout=30000)

            print("\n" + "="*60)
            print("✅ BROWSER READY FOR MANUAL LOGIN")
            print("="*60)
            print("📝 Instructions:")
            print("   1. Log in to TradingView in the browser window")
            print("   2. Navigate to your chart to verify login works")
            print("   3. Press Ctrl+C here when done to save session")
            print("="*60 + "\n")

            # Wait loop - just keep browser alive, NO screenshots
            while self.running:
                try:
                    # Check if browser is still alive
                    if not self.browser or not self.browser.is_connected():
                        print("⚠️  Browser was closed")
                        break
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"Error in wait loop: {e}")
                    break

        except Exception as e:
            print(f"❌ Failed to start browser: {e}")
            import traceback
            traceback.print_exc()

    async def _load_existing_session(self):
        """Load existing session cookies from file."""
        try:
            session_file = self._get_session_file_path()
            if session_file.exists():
                with open(session_file, 'r') as f:
                    session_data = json.load(f)
                if session_data and self.context:
                    cookies = session_data.get('cookies', [])
                    if cookies:
                        await self.context.add_cookies(cookies)
                        print(f"✅ Loaded {len(cookies)} existing session cookies")
        except Exception as e:
            print(f"⚠️  Could not load existing session: {e}")

    def _get_session_file_path(self) -> Path:
        """Get session file path (same logic as sourcer)."""
        import os
        from dotenv import load_dotenv
        # Load .env.local from project root (unified env file)
        _env_path = Path(__file__).parent.parent / '.env.local'
        if _env_path.exists():
            load_dotenv(_env_path)
        else:
            load_dotenv()

        username = os.getenv('TRADINGVIEW_EMAIL', '')
        # Sanitize for filename
        sanitized = username.replace('@', '_').replace('.', '_')
        sanitized = "".join(c for c in sanitized if c.isalnum() or c in "_-")

        base_path = Path(self.tv_config.auth.session_file if self.tv_config else "data/")
        return base_path / f".tradingview_session_{sanitized}"

    async def save_session(self):
        """Save session cookies to file (same location as sourcer)."""
        if not self.context:
            print("⚠️  No browser context - cannot save session")
            return

        try:
            cookies = await self.context.cookies()
            if not cookies:
                print("⚠️  No cookies to save")
                return

            session_file = self._get_session_file_path()
            session_file.parent.mkdir(parents=True, exist_ok=True)

            session_data = {
                'timestamp': time.time(),
                'cookies': cookies,
                'saved_by': 'interactive_browser'
            }

            with open(session_file, 'w') as f:
                json.dump(session_data, f, indent=2)

            print(f"💾 Session saved: {len(cookies)} cookies → {session_file}")

            # Also save to database (encrypted)
            await self._save_session_to_db(session_data)

        except Exception as e:
            print(f"❌ Failed to save session: {e}")
            import traceback
            traceback.print_exc()

    async def _save_session_to_db(self, session_data: dict):
        """Save session to database with encryption."""
        try:
            from trading_bot.core.secrets_manager import SecretsManager
            import os

            # Encrypt session data
            secrets = SecretsManager()
            encrypted = secrets.encrypt(json.dumps(session_data))

            # Get username for this session
            username = os.getenv('TRADINGVIEW_EMAIL', 'unknown')

            # Use centralized database client
            conn = get_connection()

            # Create sessions table if not exists
            execute(conn, """
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    encrypted_data TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')),
                    expires_at TEXT,
                    is_valid INTEGER DEFAULT 1
                )
            """)

            # Invalidate old sessions for this user
            is_valid_false = get_boolean_value(False)
            is_valid_true = get_boolean_value(True)
            execute(conn, f"UPDATE sessions SET is_valid = {is_valid_false} WHERE username = ?", (username,))

            # Insert new session
            execute(conn, f"""
                INSERT INTO sessions (username, encrypted_data, is_valid)
                VALUES (?, ?, {is_valid_true})
            """, (username, encrypted))

            conn.commit()
            conn.close()

            print("✅ Session saved to database (encrypted)")

        except Exception as e:
            print(f"⚠️  Could not save to database: {e}")

    async def cleanup(self):
        """Clean up browser resources."""
        self.running = False

        if self.context:
            await self.save_session()

        if self.page:
            try:
                await self.page.close()
            except:
                pass

        if self.context:
            try:
                await self.context.close()
            except:
                pass

        if self.browser:
            try:
                await self.browser.close()
            except:
                pass

        if self.playwright:
            try:
                await self.playwright.stop()
            except:
                pass

        print("✅ Browser closed and session saved")


async def main():
    browser = InteractiveBrowser()

    def signal_handler(sig, frame):
        print("\n🛑 Stopping and saving session...")
        browser.running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await browser.start_browser()
    except KeyboardInterrupt:
        pass
    finally:
        await browser.cleanup()


if __name__ == "__main__":
    asyncio.run(main())

