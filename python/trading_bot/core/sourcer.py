"""Chart image sourcing module."""
import asyncio
import json
import logging
import os
import queue
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any

import requests
from trading_bot.core.secrets_manager import get_tradingview_email
from trading_bot.db.client import get_connection, query_one, execute, DB_TYPE

# Realistic user agents for stealth - rotated randomly
# These match real Chrome on Windows 10/11 installations
USER_AGENTS = [
    # Chrome 131 on Windows 10
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    # Chrome 130 on Windows 10
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    # Chrome 131 on Windows 11
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.86 Safari/537.36",
    # Chrome 130 on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    # Chrome 131 on macOS Sonoma
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]


def get_random_user_agent() -> str:
    """Get a random realistic user agent string."""
    return random.choice(USER_AGENTS)

# Image processing imports
try:
    from PIL import Image
    import io
    IMAGE_PROCESSING_AVAILABLE = True
except ImportError:
    IMAGE_PROCESSING_AVAILABLE = False

# TradingView automation imports (with graceful fallback)
try:
    from playwright.async_api import async_playwright, Browser, Page, BrowserContext
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    import keyring
    TRADINGVIEW_AVAILABLE = True
except ImportError:
    TRADINGVIEW_AVAILABLE = False
    Browser = None
    Page = None
    BrowserContext = None
    PlaywrightTimeoutError = Exception

# Playwright stealth for anti-detection
try:
    from playwright_stealth import stealth_async
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False
    stealth_async = None

from trading_bot.config.settings_v2 import Config, TradingViewConfig
from trading_bot.core.utils import check_system_resources, normalize_symbol_for_bybit # Import normalize_symbol_for_bybit


def is_railway_environment() -> bool:
    """Detect if running on Railway platform."""
    return os.environ.get('RAILWAY_ENVIRONMENT') is not None or \
           os.environ.get('RAILWAY_SERVICE_NAME') is not None


class ChartSourcer:
    """Responsible for sourcing chart images from various sources."""
    
    def __init__(self, config: Optional[Config] = None):
        if config is None:
            raise ValueError("config is required for ChartSourcer. Pass config from instance settings.")
        self.config = config
        self.config_dir = Path(config.paths.charts)
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Data directory is parent of charts (data/) - where trading.db lives
        self.data_dir = self.config_dir.parent
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Debug directory same as data dir
        self.debug_dir = self.data_dir
        self.tv_config = self.config.tradingview

        # TradingView automation state
        self.browser = None
        self.context = None
        self.page = None
        self.session_data = None
        self.last_request_time = 0.0

        # Setup logging
        self.logger = logging.getLogger(__name__)

        # Analysis queue for parallel processing
        self.analysis_queue = queue.Queue()
        self.analysis_results = {}

        # Check TradingView availability
        self.tradingview_enabled = (
            TRADINGVIEW_AVAILABLE and
            self.tv_config is not None and
            self.tv_config.enabled and
            self._check_credentials()
        )

        if not self.tradingview_enabled and self.tv_config is not None and self.tv_config.enabled:
            self.logger.warning(
                "TradingView automation disabled: missing dependencies or credentials"
            )
    
    def _check_credentials(self) -> bool:
        """
        Check if TradingView session is available.
        Note: Login is now manual via interactive browser, so we just check for saved session.
        """
        # We no longer check for password - login is manual
        # Just check if we have an email for session naming
        email = get_tradingview_email()
        return bool(email)

    def _get_username(self) -> Optional[str]:
        """Get the current TradingView username (email) for session file naming."""
        try:
            email = get_tradingview_email()

            if not email and TRADINGVIEW_AVAILABLE:
                try:
                    email = keyring.get_password("tradingview", "email")
                except Exception:
                    pass

            return email or 'default'
        except Exception:
            return 'default'
    
    def _sanitize_username_for_filename(self, username: str) -> str:
        """Sanitize username (email) for use in filename by replacing special characters."""
        if not username:
            return "default"
        
        # Replace special characters with underscores
        sanitized = username.replace("@", "_").replace(".", "_").replace("+", "_")
        # Remove any other characters that might be problematic for filenames
        sanitized = "".join(c for c in sanitized if c.isalnum() or c in "_-")
        return sanitized
    
    def _get_session_file_path(self) -> str:
        """Get the session file path based on the current username."""
        username = self._get_username()
        sanitized_username = self._sanitize_username_for_filename(username or "")
        base_path = Path(self.tv_config.auth.session_file).parent
        filename = f".tradingview_session_{sanitized_username}"
        return str(base_path / filename)
    
    def get_local_chart(self, symbol: str, timeframe: str = "1d") -> Optional[str]:
        """Get chart image from storage (local or cloud)."""
        from trading_bot.core.storage import list_files, get_storage_type

        # List all chart files
        all_files = list_files('charts')

        # Filter for matching pattern: SYMBOL_TIMEFRAME_*.png
        pattern_prefix = f"{symbol}_{timeframe}_"
        matches = [f for f in all_files if f.startswith(pattern_prefix) and f.endswith('.png')]

        if matches:
            # Return most recent (sorted by filename which includes timestamp)
            return sorted(matches)[-1]
        return None
    
    def save_chart(self, image_data: bytes, symbol: str, timeframe: str) -> str:
        """Save chart image to storage (local or cloud based on STORAGE_TYPE)."""
        # Import here to avoid circular imports
        from trading_bot.core.file_validator import FileValidator
        from trading_bot.core.timestamp_validator import TimestampValidator
        from trading_bot.core.utils import align_timestamp_to_boundary
        from trading_bot.core.storage import save_file, get_storage_type

        validator = FileValidator()
        timestamp_validator = TimestampValidator()

        # Normalize the symbol before validation and filename creation
        normalized_symbol = normalize_symbol_for_bybit(symbol)

        # Validate symbol format
        symbol_validation = validator.validate_symbol_format(normalized_symbol)
        if not symbol_validation["is_valid"]:
            raise ValueError(f"Invalid symbol format: {normalized_symbol} - {symbol_validation['errors']}")

        # Validate image data
        if not image_data or len(image_data) < validator.min_file_size:
            raise ValueError(f"Invalid image data: size {len(image_data)} bytes is too small")

        if len(image_data) > validator.max_file_size:
            raise ValueError(f"Invalid image data: size {len(image_data)} bytes is too large")

        # Create filename with boundary-aligned timestamp for autotrader consistency
        current_time = datetime.now(timezone.utc)
        boundary_aligned_time = align_timestamp_to_boundary(current_time, timeframe)
        timestamp = boundary_aligned_time.strftime("%Y%m%d_%H%M%S")
        filename = f"{normalized_symbol}_{timeframe}_{timestamp}.png" # Use normalized symbol

        self.logger.info(f"🕐 Aligned timestamp: {current_time.strftime('%H:%M:%S')} -> {boundary_aligned_time.strftime('%H:%M:%S')} for {timeframe}")

        # Validate filename pattern
        filename_validation = validator.validate_filename_pattern(filename, require_timeframe=True)
        if not filename_validation["is_valid"]:
            raise ValueError(f"Generated filename is invalid: {filename} - {filename_validation['errors']}")

        # Use storage abstraction layer (supports local and Supabase S3)
        storage_type = get_storage_type()
        self.logger.info(f"💾 Saving chart to {storage_type} storage: {filename}")

        # Save using storage module
        result = save_file(filename, image_data, content_type='image/png')

        if not result.get('success'):
            raise ValueError(f"Failed to save chart: {result.get('error', 'Unknown error')}")

        saved_path = result.get('path', filename)
        self.logger.info(f"✅ Successfully saved chart: {saved_path} (storage: {storage_type})")

        # For local storage, also keep reference to the filepath for backward compatibility
        if storage_type == 'local':
            return saved_path
        else:
            # For cloud storage, return the filename (caller can use get_public_url if needed)
            return filename
    
    def download_chart(self, url: str, symbol: str, timeframe: str) -> str:
        """Download chart from URL."""
        response = requests.get(url)
        response.raise_for_status()
        return self.save_chart(response.content, symbol, timeframe)
    
    def list_available_charts(self) -> List[str]:
        """List all available chart images from storage (local or cloud)."""
        from trading_bot.core.storage import list_files

        # List all PNG files in charts directory
        all_files = list_files('charts')
        return [f for f in all_files if f.endswith('.png')]

    def get_charts_for_current_boundary(self, timeframe: str) -> Dict[str, str]:
        """
        Check if charts already exist for the current boundary.
        Returns a dict mapping symbol to chart path if charts exist for current boundary.

        Args:
            timeframe: The timeframe to check (e.g., '1h', '4h', '1d')

        Returns:
            Dict mapping symbol names to chart paths for current boundary, or empty dict if none exist
        """
        from trading_bot.core.utils import align_timestamp_to_boundary
        from trading_bot.core.storage import list_files
        from datetime import datetime, timezone

        try:
            # Get current boundary-aligned timestamp
            current_time = datetime.now(timezone.utc)
            boundary_aligned_time = align_timestamp_to_boundary(current_time, timeframe)
            boundary_timestamp = boundary_aligned_time.strftime("%Y%m%d_%H%M%S")

            # Look for charts with this boundary timestamp
            # Pattern: *_TIMEFRAME_TIMESTAMP.png
            suffix = f"_{timeframe}_{boundary_timestamp}.png"
            matching_charts = {}

            # List all chart files from storage
            all_files = list_files('charts')

            for filename in all_files:
                if filename.endswith(suffix):
                    # Extract symbol from filename (format: SYMBOL_TIMEFRAME_TIMESTAMP.png)
                    # Remove .png extension
                    name_without_ext = filename[:-4]
                    parts = name_without_ext.rsplit('_', 2)  # Split from right: symbol, timeframe, timestamp
                    if len(parts) >= 1:
                        symbol = parts[0]
                        matching_charts[symbol] = filename

            if matching_charts:
                self.logger.info(f"✅ Found {len(matching_charts)} charts for current {timeframe} boundary ({boundary_timestamp})")
                return matching_charts
            else:
                self.logger.info(f"📷 No charts found for current {timeframe} boundary ({boundary_timestamp}) - will capture new ones")
                return {}

        except Exception as e:
            self.logger.error(f"Error checking for existing charts: {e}")
            return {}

    # TradingView Automation Methods
    
    async def capture_tradingview_chart(self, symbol: str, timeframe: str = "1d") -> Optional[str]:
        """
        Main method to capture chart from TradingView.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSD', 'AAPL')
            timeframe: Chart timeframe (e.g., '1d', '4h', '1h')
            
        Returns:
            Path to saved chart image or None if failed
        """
        # Normalize symbol at the entry point
        normalized_symbol = normalize_symbol_for_bybit(symbol)

        if not self.tradingview_enabled:
            self.logger.warning("TradingView automation not available, falling back to local charts")
            return self.get_local_chart(normalized_symbol, timeframe)
        
        try:
            # Rate limiting
            await self._respect_rate_limits()

            # Setup browser session
            if not await self.setup_browser_session():
                raise Exception("Failed to setup browser session")

            # Authenticate with retry mechanism
            if not await self._authenticate_with_retry():
                raise Exception("Failed to authenticate with TradingView after retries")
            
            # Navigate to chart using normalized symbol
            if not await self.navigate_to_chart(normalized_symbol, timeframe):
                raise Exception(f"Failed to navigate to chart for {normalized_symbol}")
            
            # Wait for chart to load
            if not await self.wait_for_chart_load():
                raise Exception("Chart failed to load properly")
            
            # Capture screenshot using normalized symbol
            screenshot_path = await self.capture_screenshot(normalized_symbol, timeframe)
            
            if screenshot_path:
                self.logger.info(f"Successfully captured TradingView chart for {normalized_symbol} ({timeframe})")
                return screenshot_path
            else:
                raise Exception("Failed to capture screenshot")
                
        except Exception as e:
            self.logger.error(f"TradingView chart capture failed for {normalized_symbol}: {str(e)}")
            # Fallback to local charts
            return self.get_local_chart(normalized_symbol, timeframe)
        
        finally:
            await self.cleanup_browser_session()
            pass
    
    async def setup_browser_session(self) -> bool:
        """Initialize Playwright browser with anti-detection measures and resource management."""
        if not TRADINGVIEW_AVAILABLE:
            return False
        
        try:
            # Check system resources before starting
            # if not await self._check_system_resources():
            #     self.logger.warning("Insufficient system resources for browser automation")
            #     return False
            
            if self.browser is None:
                try:
                    playwright = await async_playwright().start()
                except Exception as e:
                    self.logger.error(f"Failed to start Playwright: {str(e)}")
                    return False
                
                try:
                    # Detect Railway environment and auto-enable VNC mode
                    on_railway = is_railway_environment()
                    if on_railway:
                        self.logger.info("🚂 Railway environment detected - enabling VNC mode")
                        # Force VNC mode on Railway
                        self.tv_config.browser.use_vnc = True
                        self.tv_config.browser.vnc_display = ':99'
                        # Ensure DISPLAY is set
                        os.environ['DISPLAY'] = ':99'

                    # Prepare Firefox-specific browser arguments - optimized for both local and server environments
                    browser_args = []

                    if self.tv_config.browser.headless:
                        # Headless mode - use resource optimization flags
                        browser_args.extend([
                            '--headless',  # Run headless for resource efficiency
                            '--width=1600',
                            '--height=900',
                            '--disable-gpu',  # Disable GPU acceleration
                            '--disable-software-rasterizer',
                            '--memory-pressure-threshold=0.8',  # Trigger memory cleanup at 80%
                            '--memory-pressure-interval=1000',  # Check memory every second
                            '--disable-background-timer-throttling',
                            '--disable-renderer-backgrounding',
                            '--disable-backgrounding-occluded-windows',
                            '--disable-dev-shm-usage',  # Overcome limited resource problems
                            '--no-sandbox',
                            '--disable-web-security',  # Allow cross-origin requests
                            '--disable-features=VizDisplayCompositor',  # Disable display compositor
                            '--disable-accelerated-video-decode',  # Disable accelerated video
                            '--disable-gpu-compositing',  # Disable GPU compositing
                            '--disable-gpu-rasterization',  # Disable GPU rasterization
                            '--disable-background-media-download',  # Disable background media
                            '--disable-print-preview',  # Disable print preview
                            '--mute-audio',  # Mute audio
                            '--disable-notifications',  # Disable notifications
                            '--disable-popup-blocking',  # Disable popup blocking
                            '--disable-default-apps',  # Disable default apps
                            '--no-first-run',  # Skip first run experience
                            '--disable-sync',  # Disable sync
                            '--disable-translate',  # Disable translate
                            '--hide-scrollbars',  # Hide scrollbars
                            '--disable-extensions',  # Disable extensions for stability
                            '--disable-plugins',  # Disable plugins
                            '--safe-mode',  # Run in safe mode for stability
                        ])
                    else:
                        # Visual mode - minimal flags for local testing
                        browser_args.extend([
                            '--no-sandbox',
                            '--disable-web-security',  # Allow cross-origin requests
                            '--disable-features=VizDisplayCompositor',
                        ])

                    # Add window sizing arguments for both VNC and host system
                    if self.tv_config.browser.use_vnc and not self.tv_config.browser.headless:
                        self.logger.info("🔧 Enabling VNC integration mode")

                        # Set DISPLAY environment variable for VNC
                        display = os.environ.get('DISPLAY', self.tv_config.browser.vnc_display)
                        os.environ['DISPLAY'] = display
                        self.logger.info(f"📺 Using DISPLAY={display} for VNC")

                        # CRITICAL: Clear browser_args to avoid inheriting aggressive flags from visual mode
                        # TradingView detects --disable-web-security and crashes the browser
                        browser_args = []

                        # VNC-specific browser arguments - ULTRA MINIMAL for Railway/Docker compatibility
                        # Railway has limited /dev/shm (64MB) - use single-process mode to avoid OOM crashes
                        vnc_args = [
                            f'--display={display}',
                            f'--window-size={self.tv_config.browser.vnc_window_size}',
                            '--disable-dev-shm-usage',  # Critical for limited /dev/shm in Docker
                            '--no-sandbox',  # Required for Docker (no choice)
                            '--single-process',  # CRITICAL: Run in single process to avoid /dev/shm exhaustion
                            # DO NOT add --disable-web-security (causes TradingView to crash)
                            # DO NOT add --disable-gpu (let browser decide)
                            # DO NOT add --disable-features (causes detection)
                        ]
                        browser_args.extend(vnc_args)
                        self.logger.info(f"🔧 VNC browser args: {vnc_args}")

                        # Verify VNC connection
                        if not await self._verify_vnc_connection():
                            self.logger.warning("⚠️ VNC connection not detected, but continuing...")
                    else:
                        self.logger.info("🔧 Using standard browser mode (no VNC)")

                        # Add window sizing arguments for host system to ensure full screen usage
                        if not self.tv_config.browser.headless:
                            host_args = [
                                f'--window-size={self.tv_config.browser.viewport_width},{self.tv_config.browser.viewport_height}',
                                '--start-maximized',  # Start browser maximized
                                '--start-fullscreen',  # Start in fullscreen mode
                                '--app-window',  # App window mode
                                '--window-position=0,0',  # Position at top-left
                                '--no-default-browser-check',
                                '--disable-session-crashed-bubble',
                                '--disable-infobars',
                            ]
                            browser_args.extend(host_args)

                    # Launch Chromium browser (more compatible for local testing)
                    self.logger.info("🚀 Launching Chromium browser")
                    self.browser = await playwright.chromium.launch(
                        headless=self.tv_config.browser.headless,
                        args=browser_args
                    )
                except Exception as e:
                    self.logger.error(f"Failed to launch browser: {str(e)}")
                    try:
                        await playwright.stop()
                    except Exception:
                        pass
                    return False
                
                try:
                    # Load session data first to get stored user_agent (before creating context)
                    stored_session = await self._load_session_from_db()

                    # Use stored user_agent for consistency, or pick new random one
                    if stored_session and stored_session.get('user_agent'):
                        selected_ua = stored_session['user_agent']
                        self.logger.info(f"🥷 Using stored user agent: {selected_ua[:50]}...")
                    else:
                        selected_ua = get_random_user_agent()
                        self.logger.info(f"🥷 Using new random user agent: {selected_ua[:50]}...")

                    # Store for later saving with session
                    self._current_user_agent = selected_ua

                    # Create context with resource limits
                    self.context = await self.browser.new_context(
                        viewport={
                            'width': self.tv_config.browser.viewport_width,
                            'height': self.tv_config.browser.viewport_height
                        },
                        user_agent=selected_ua,
                        java_script_enabled=True,
                        accept_downloads=False,
                        has_touch=False,
                        is_mobile=False,
                        locale='en-US',
                        timezone_id='America/New_York',
                        # Resource limits
                        bypass_csp=True,
                        ignore_https_errors=True
                    )

                    # Now apply cookies from stored session
                    if stored_session:
                        cookies = stored_session.get('cookies', [])
                        if cookies:
                            await self.context.add_cookies(cookies)
                            self.logger.info(f"✅ Session loaded from database ({len(cookies)} cookies)")
                        self.session_data = stored_session
                    else:
                        self.logger.info("No session found in database - fresh login required")
                        self.session_data = None

                except Exception as e:
                    self.logger.error(f"Failed to create browser context: {str(e)}")
                    try:
                        await self.browser.close()
                    except Exception:
                        pass
                    self.browser = None
                    return False

                try:

                    # Create new page
                    self.page = await self.context.new_page()

                    # Apply playwright-stealth if available (comprehensive anti-detection)
                    if STEALTH_AVAILABLE and stealth_async:
                        try:
                            await stealth_async(self.page)
                            self.logger.info("🥷 Stealth mode applied successfully")
                        except Exception as e:
                            self.logger.warning(f"Stealth plugin failed (using fallback): {str(e)}")

                    # Add console error logging for debugging (with error handling)
                    try:
                        self.page.on("console", lambda msg: self.logger.debug(f"Browser console: {msg.type}: {msg.text}"))
                        self.page.on("pageerror", lambda err: self.logger.error(f"Page error: {err}"))
                    except Exception as e:
                        self.logger.warning(f"Failed to set up page event handlers: {str(e)}")

                    # Add request/response monitoring for debugging stuck loads (optional)
                    try:
                        self.page.on("request", lambda req: self.logger.debug(f"Request: {req.method} {req.url}"))
                        self.page.on("response", lambda res: self.logger.debug(f"Response: {res.status} {res.url}"))
                    except Exception as e:
                        self.logger.debug(f"Failed to set up request monitoring: {str(e)}")

                    # Add comprehensive anti-detection scripts and viewport fixes
                    try:
                        await self.page.add_init_script("""
                            // Comprehensive anti-detection measures
                            (() => {
                                // 1. Hide webdriver property
                                try {
                                    Object.defineProperty(navigator, 'webdriver', {
                                        get: () => undefined,
                                    });
                                    // Also delete it if possible
                                    delete navigator.__proto__.webdriver;
                                } catch (e) {}

                                // 2. Fake plugins array (Chrome typically has 3-5 plugins)
                                try {
                                    const fakePlugins = {
                                        length: 5,
                                        0: { name: 'Chrome PDF Plugin', description: 'Portable Document Format', filename: 'internal-pdf-viewer' },
                                        1: { name: 'Chrome PDF Viewer', description: '', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                                        2: { name: 'Native Client', description: '', filename: 'internal-nacl-plugin' },
                                        3: { name: 'Chromium PDF Plugin', description: 'Portable Document Format', filename: 'internal-pdf-viewer' },
                                        4: { name: 'Chromium PDF Viewer', description: '', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                                        item: function(i) { return this[i]; },
                                        namedItem: function(name) { return null; },
                                        refresh: function() {}
                                    };
                                    Object.defineProperty(navigator, 'plugins', {
                                        get: () => fakePlugins,
                                    });
                                } catch (e) {}

                                // 3. Fake languages
                                try {
                                    Object.defineProperty(navigator, 'languages', {
                                        get: () => ['en-US', 'en'],
                                    });
                                } catch (e) {}

                                // 4. Hide automation flags
                                try {
                                    Object.defineProperty(navigator, 'maxTouchPoints', {
                                        get: () => 0,
                                    });
                                } catch (e) {}

                                // 5. Override permissions query
                                try {
                                    const originalQuery = window.navigator.permissions.query;
                                    window.navigator.permissions.query = (parameters) => (
                                        parameters.name === 'notifications' ?
                                            Promise.resolve({ state: Notification.permission }) :
                                            originalQuery(parameters)
                                    );
                                } catch (e) {}

                                // 6. Fix chrome object
                                try {
                                    if (!window.chrome) {
                                        window.chrome = {
                                            runtime: {},
                                            loadTimes: function() {},
                                            csi: function() {},
                                            app: {}
                                        };
                                    }
                                } catch (e) {}

                                // 7. Fake hardware concurrency (realistic core count)
                                try {
                                    Object.defineProperty(navigator, 'hardwareConcurrency', {
                                        get: () => 8,
                                    });
                                } catch (e) {}

                                // 8. Fake device memory
                                try {
                                    Object.defineProperty(navigator, 'deviceMemory', {
                                        get: () => 8,
                                    });
                                } catch (e) {}

                                // 9. Override toString to hide modifications
                                try {
                                    const nativeToString = Function.prototype.toString;
                                    const toStringProxy = new Proxy(nativeToString, {
                                        apply: function(target, thisArg, args) {
                                            if (thisArg === navigator.permissions.query) {
                                                return 'function query() { [native code] }';
                                            }
                                            return Reflect.apply(target, thisArg, args);
                                        }
                                    });
                                    Function.prototype.toString = toStringProxy;
                                } catch (e) {}
                            })();

                            // Safe viewport fixing function
                            function fixViewport() {
                                try {
                                    const viewport = document.querySelector('meta[name="viewport"]');
                                    if (viewport) {
                                        viewport.setAttribute('content', 'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no');
                                    }

                                    const docElement = document.documentElement;
                                    const body = document.body;

                                    if (docElement && docElement.style) {
                                        docElement.style.width = '100%';
                                        docElement.style.height = '100%';
                                        docElement.style.margin = '0';
                                        docElement.style.padding = '0';
                                        docElement.style.overflow = 'hidden';
                                    }

                                    if (body && body.style) {
                                        body.style.width = '100%';
                                        body.style.height = '100%';
                                        body.style.margin = '0';
                                        body.style.padding = '0';
                                        body.style.overflow = 'hidden';
                                    }

                                    const containers = document.querySelectorAll('.container, .main, #main, .content, .app');
                                    containers.forEach(container => {
                                        if (container && container.style) {
                                            container.style.width = '100%';
                                            container.style.height = '100%';
                                            container.style.maxWidth = 'none';
                                            container.style.maxHeight = 'none';
                                        }
                                    });
                                } catch (error) {}
                            }

                            // Run viewport fix with error handling
                            try {
                                fixViewport();
                                window.addEventListener('load', fixViewport);
                                window.addEventListener('resize', fixViewport);
                                window.addEventListener('DOMContentLoaded', fixViewport);
                                setInterval(fixViewport, 1000);
                            } catch (error) {}
                        """)
                    except Exception as e:
                        self.logger.warning(f"Failed to add init script: {str(e)}")
                except Exception as e:
                    self.logger.error(f"Failed to create page or add scripts: {str(e)}")
                    await self.cleanup_browser_session()
                    return False
                
                self.logger.info("Browser session initialized successfully")
                return True

        except Exception as e:
            self.logger.error(f"Failed to setup browser session: {str(e)}")
            await self.cleanup_browser_session()
            return False

        return True

    def _is_browser_alive(self) -> bool:
        """Check if browser, context and page are still alive and usable."""
        try:
            if not self.browser:
                return False
            if not self.context:
                return False
            if not self.page:
                return False
            # Check if page is closed
            if self.page.is_closed():
                return False
            return True
        except Exception:
            return False

    async def authenticate_tradingview(self) -> bool:
        """Simplified TradingView authentication with direct navigation approach."""
        if not self.page:
            return False

        try:
            # Try direct navigation to target chart first
            self.logger.info("🔐 Attempting direct navigation to target chart...")
            if await self._authenticate_simplified():
                self.logger.info("✅ Successfully authenticated via direct navigation")
                return True

            # If direct navigation fails, try existing session
            self.logger.info("🔐 Checking for existing session...")
            if await self._try_existing_session():
                self.logger.info("✅ Successfully authenticated with existing session")
                return True

            # If both fail, try manual login as last resort
            self.logger.info("❌ Direct authentication failed, trying manual login...")
            success = await self._handle_manual_login()
            return success

        except Exception as e:
            self.logger.error(f"TradingView authentication error: {str(e)}")
            return False
    
    async def navigate_to_chart(self, symbol: str, timeframe: str) -> bool:
        """Navigate to specific chart using watchlist on TradingView."""
        # Normalize symbol for internal use and API calls
        normalized_symbol = normalize_symbol_for_bybit(symbol)

        if not self.page:
            return False

        try:
            # First, make sure we're on the main TradingView page with charts
            current_url = self.page.url
            if 'tradingview.com' not in current_url or 'chart' not in current_url:
                self.logger.info("Navigating to TradingView chart page")
                try:
                    await self.page.goto("https://www.tradingview.com/chart/", timeout=self.tv_config.browser.timeout)
                    self.logger.info("Chart page navigation initiated, waiting for load...")
                    await self.page.wait_for_load_state('networkidle', timeout=50000)
                    self.logger.info("Chart page loaded successfully")
                except Exception as nav_error:
                    self.logger.error(f"Chart page navigation failed: {str(nav_error)}")
                    # Try with domcontentloaded as fallback
                    try:
                        await self.page.wait_for_load_state('domcontentloaded', timeout=20000)
                        self.logger.info("Chart page loaded with domcontentloaded state")
                    except Exception as dom_error:
                        self.logger.error(f"Dom content load also failed: {str(dom_error)}")
                        raise nav_error
                await asyncio.sleep(3)  # Wait for page to fully load

                # Check if we hit the "can't open chart layout" error page
                if await self._detect_login_required_page():
                    self.logger.warning("🔒 Login required detected after navigation")
                    if await self._handle_login_required_and_retry():
                        # Re-navigate after successful login
                        self.logger.info("🔄 Retrying navigation after successful login...")
                        await self.page.goto("https://www.tradingview.com/chart/", timeout=self.tv_config.browser.timeout)
                        await self.page.wait_for_load_state('networkidle', timeout=50000)
                        await asyncio.sleep(3)
                    else:
                        self.logger.error("❌ Login failed - cannot access chart")
                        return False
            
            # Look for symbol search box or watchlist
            symbol_search_selectors = [
                'input[data-role="search"]',
                'input[placeholder*="symbol" i]',
                'input[placeholder*="search" i]',
                '.symbol-search-input',
                '[data-name="symbol-search"]',
                '.js-symbol-search'
            ]
            
            symbol_input_found = False
            for selector in symbol_search_selectors:
                try:
                    self.logger.debug(f"Looking for symbol search with selector: {selector}")
                    await self.page.wait_for_selector(selector, timeout=5000)
                    
                    # Clear and type the normalized symbol
                    await self.page.fill(selector, normalized_symbol.upper())
                    await asyncio.sleep(1)
                    
                    # Press Enter or look for search results
                    await self.page.keyboard.press('Enter')
                    await asyncio.sleep(2)
                    
                    self.logger.info(f"Successfully searched for symbol: {normalized_symbol}")
                    symbol_input_found = True
                    break
                    
                except Exception as e:
                    self.logger.debug(f"Symbol search selector {selector} failed: {str(e)}")
                    continue
            
            if not symbol_input_found:
                # Try using watchlist approach - look for watchlist items
                self.logger.info("Symbol search not found, trying watchlist approach")
                
                watchlist_selectors = [
                    '.watchlist',
                    '[class*="watchlist"]',
                    '.symbol-list',
                    '[data-name="watchlist"]',
                    '.js-watchlist'
                ]
                
                for selector in watchlist_selectors:
                    try:
                        watchlist = await self.page.query_selector(selector)
                        if watchlist:
                            # Look for the normalized symbol in the watchlist
                            symbol_items = await watchlist.query_selector_all(f'[title*="{normalized_symbol}" i], [data-symbol*="{normalized_symbol}" i]')
                            if symbol_items:
                                await symbol_items[0].click()
                                self.logger.info(f"Clicked on {normalized_symbol} in watchlist")
                                symbol_input_found = True
                                break
                    except Exception:
                        continue
            
            if not symbol_input_found:
                self.logger.warning(f"Could not find symbol search or {normalized_symbol} in watchlist, using URL fallback")
                # Fallback to URL navigation using normalized symbol
                tv_timeframe = self._convert_timeframe(timeframe)
                chart_url = self.tv_config.chart_url_template.format(
                    symbol=normalized_symbol.upper(),
                    interval=tv_timeframe  # Use 'interval' to match TradingView URL parameter
                )
                self.logger.info(f"Navigating to chart URL: {chart_url}")
                await self.page.goto(chart_url, timeout=self.tv_config.browser.timeout)
                await self.page.wait_for_load_state('networkidle')
            
            # Wait for chart container to be visible
            await self.page.wait_for_selector(
                self.tv_config.screenshot.chart_selector,
                timeout=self.tv_config.browser.timeout
            )
            
            # Set timeframe if needed
            await self._set_timeframe(timeframe)
            
            self.logger.info(f"Successfully navigated to {normalized_symbol} chart ({timeframe})")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to navigate to chart: {str(e)}")
            return False
    
    async def _set_timeframe(self, timeframe: str) -> bool:
        """Set the chart timeframe using TradingView interface."""
        try:
            tv_timeframe = self._convert_timeframe(timeframe)
            
            # Look for timeframe buttons
            timeframe_selectors = [
                f'button:has-text("{tv_timeframe}")',
                f'[data-value="{tv_timeframe}"]',
                f'[data-timeframe="{tv_timeframe}"]',
                f'.timeframe-{tv_timeframe}',
                f'[title*="{tv_timeframe}"]'
            ]
            
            for selector in timeframe_selectors:
                try:
                    if self.page:
                        element = await self.page.query_selector(selector)
                        if element:
                            await element.click()
                            self.logger.info(f"Set timeframe to {timeframe}")
                            await asyncio.sleep(1)  # Wait for chart to update
                            return True
                except Exception:
                    continue
            
            self.logger.warning(f"Could not set timeframe to {timeframe}")
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to set timeframe: {str(e)}")
            return False
    
    async def wait_for_chart_load(self) -> bool:
        """Wait for chart data to fully load."""
        if not self.page:
            return False
        
        try:
            # Wait for the specified time
            await asyncio.sleep(self.tv_config.screenshot.wait_for_load / 1000)
            
            # Use a simpler approach that doesn't violate CSP
            # Wait for chart container to be visible and stable
            try:
                await self.page.wait_for_selector(
                    self.tv_config.screenshot.chart_selector,
                    state='visible',
                    timeout=self.tv_config.browser.timeout
                )
                self.logger.info("Chart container is visible")
            except Exception as e:
                self.logger.warning(f"Chart container not found: {str(e)}")
            
            # Additional wait for chart to stabilize
            await asyncio.sleep(3)
            
            # Try to wait for loading indicators to disappear using selector-based approach
            loading_selectors = [
                '[class*="loading"]',
                '[class*="spinner"]',
                '[class*="loader"]',
                '.loading',
                '.spinner'
            ]
            
            for selector in loading_selectors:
                try:
                    # Wait for loading elements to be hidden (if they exist)
                    await self.page.wait_for_selector(selector, state='hidden', timeout=5000)
                    self.logger.debug(f"Loading indicator {selector} disappeared")
                except Exception:
                    # Loading indicator might not exist, which is fine
                    pass
            
            self.logger.info("Chart loaded successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Chart loading timeout: {str(e)}")
            # Don't fail completely - chart might still be usable
            self.logger.info("Proceeding with chart capture despite loading timeout")
            return True
    
    async def capture_screenshot(self, symbol: str, timeframe: str) -> Optional[str]:
        """Take clean screenshot of chart area with enhanced error handling."""
        # Normalize symbol before saving the chart
        normalized_symbol = normalize_symbol_for_bybit(symbol)

        # Check if browser is still alive
        if not self._is_browser_alive():
            self.logger.warning("Browser session closed, cannot capture screenshot")
            return None

        try:
            # Detect and close any popups before taking screenshot
            await self._detect_and_close_popups()

            # Enhanced chart element detection with fallback selectors
            chart_element = await self._find_chart_element()
            if not chart_element:
                self.logger.warning("No chart element found with configured selectors, trying fallback")
                # Try fallback selectors for modern TradingView
                fallback_selectors = [
                    '[class*="chart"]',
                    '[data-widget-type="chart"]',
                    '.chart-widget',
                    '[class*="tradingview-widget"]',
                    'canvas',  # Direct canvas element
                    '.chart-container-fallback'
                ]

                for selector in fallback_selectors:
                    try:
                        chart_element = await self.page.query_selector(selector)
                        if chart_element:
                            # Check if element is visible
                            is_visible = await chart_element.is_visible()
                            if is_visible:
                                self.logger.info(f"Found chart element with fallback selector: {selector}")
                                break
                    except Exception as e:
                        self.logger.debug(f"Fallback selector {selector} failed: {str(e)}")
                        continue

            if not chart_element:
                self.logger.error("Could not find any chart element to capture")
                # Fallback to full page screenshot
                self.logger.info("Falling back to full page screenshot")
                screenshot_bytes = await self.page.screenshot(
                    full_page=True,
                    type="jpeg",
                    quality=self.tv_config.screenshot.quality
                )
            else:
                # Hide unwanted elements safely
                await self._hide_unwanted_elements_safely()

                # Wait a moment for UI changes
                await asyncio.sleep(1)

                # Take screenshot of chart area
                try:
                    screenshot_bytes = await chart_element.screenshot(
                        type="jpeg",
                        quality=self.tv_config.screenshot.quality
                    )
                except Exception as e:
                    self.logger.warning(f"Chart element screenshot failed: {str(e)}, trying full page")
                    screenshot_bytes = await self.page.screenshot(
                        full_page=True,
                        type="jpeg",
                        quality=self.tv_config.screenshot.quality
                    )

            # Crop screenshot before saving (if enabled)
            if getattr(self.tv_config.screenshot, 'enable_crop', True):
                screenshot_bytes = self._crop_screenshot(screenshot_bytes)

            # Save screenshot using existing method with normalized symbol
            screenshot_path = self.save_chart(screenshot_bytes, normalized_symbol, timeframe)

            self.logger.info(f"Screenshot saved: {screenshot_path}")
            return screenshot_path

        except Exception as e:
            self.logger.error(f"Failed to capture screenshot: {str(e)}")
            return None

    async def _find_chart_element(self) -> Optional[Any]:
        """Find the main chart element using multiple detection methods."""
        if not self.page:
            return None

        # Primary selector from config
        primary_selector = self.tv_config.screenshot.chart_selector

        try:
            element = await self.page.query_selector(primary_selector)
            if element:
                is_visible = await element.is_visible()
                if is_visible:
                    return element
        except Exception as e:
            self.logger.debug(f"Primary chart selector failed: {str(e)}")

        # Try variations of the primary selector
        selector_variations = [
            primary_selector.replace('.', ''),
            f'[class*="{primary_selector.replace(".", "")}"]',
            f'[data-name*="{primary_selector.replace(".", "")}"]'
        ]

        for selector in selector_variations:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    is_visible = await element.is_visible()
                    if is_visible:
                        self.logger.debug(f"Found chart element with variation: {selector}")
                        return element
            except Exception:
                continue

        return None

    async def _detect_and_close_popups(self) -> None:
        """Detect and close TradingView popups before taking screenshots."""
        if not self.page:
            return

        try:
            self.logger.info("🔍 Detecting and closing popups...")

            # Common popup/modal selectors for TradingView
            popup_selectors = [
                # Close buttons for popups
                'button[aria-label="Close"]',
                'button[class*="close"]',
                '.close-button',
                '[data-testid="close-button"]',
                '[class*="modal"] [class*="close"]',
                # Generic close buttons
                'button:contains("×")',
                'button:contains("✕")',
                'button:contains("Close")',
                # Specific TradingView popup selectors
                '[class*="popup"] [class*="close"]',
                '[class*="modal"] [class*="close"]',
                '[class*="overlay"] [class*="close"]',
                # Discount/offer popup specific selectors
                '[class*="discount"] [class*="close"]',
                '[class*="offer"] [class*="close"]',
                '[class*="promotion"] [class*="close"]',
                # Generic modal close buttons
                '.modal-close',
                '.popup-close',
                '.dialog-close',
                # X button in top-right corner
                'button[title="Close"]',
                'button[alt="Close"]',
            ]

            # Try to find and click close buttons
            for selector in popup_selectors:
                try:
                    close_button = await self.page.query_selector(selector)
                    if close_button:
                        is_visible = await close_button.is_visible()
                        if is_visible:
                            self.logger.info(f"Found popup close button: {selector}")
                            await close_button.click()
                            await asyncio.sleep(1)  # Wait for popup to close
                            self.logger.info("✅ Popup closed successfully")
                            return  # Success, exit method
                except Exception as e:
                    self.logger.debug(f"Close button selector {selector} failed: {str(e)}")
                    continue

            # If no close button found, try to press Escape key
            try:
                self.logger.info("No close button found, trying Escape key...")
                await self.page.keyboard.press('Escape')
                await asyncio.sleep(1)
                self.logger.info("✅ Escape key pressed")
            except Exception as e:
                self.logger.debug(f"Escape key failed: {str(e)}")

            # Additional check: Look for specific discount popup elements and try to close them
            try:
                discount_popup_selectors = [
                    '[class*="discount"]',
                    '[class*="offer"]',
                    '[class*="promotion"]',
                    '[class*="ultimate"]',
                    'button:contains("Explore offers")'
                ]

                for selector in discount_popup_selectors:
                    try:
                        element = await self.page.query_selector(selector)
                        if element:
                            # Try to find parent container and look for close button
                            parent = await element.query_selector('xpath=ancestor-or-self::*[contains(@class, "modal") or contains(@class, "popup") or contains(@class, "overlay")]')
                            if parent:
                                close_btn = await parent.query_selector('button[class*="close"], .close, [aria-label="Close"]')
                                if close_btn:
                                    await close_btn.click()
                                    await asyncio.sleep(1)
                                    self.logger.info("✅ Discount popup closed")
                                    return
                    except Exception:
                        continue

            except Exception as e:
                self.logger.debug(f"Discount popup handling failed: {str(e)}")

            self.logger.info("Popup detection and closing completed")

        except Exception as e:
            self.logger.warning(f"Error during popup detection: {str(e)}")

    async def _hide_unwanted_elements_safely(self) -> None:
        """Hide unwanted elements before screenshot with safe error handling."""
        if not self.page:
            return

        # Hide unwanted elements with null checks
        for selector in self.tv_config.screenshot.hide_elements:
            try:
                # Use evaluate with null checks
                await self.page.evaluate(f"""
                    () => {{
                        try {{
                            const elements = document.querySelectorAll('{selector}');
                            elements.forEach(el => {{
                                if (el && el.style) {{
                                    el.style.display = 'none';
                                }}
                            }});
                        }} catch (error) {{
                            // Silently ignore errors for missing elements
                        }}
                    }}
                """)
            except Exception as e:
                # Log but don't fail - element hiding is not critical
                self.logger.debug(f"Failed to hide element {selector}: {str(e)}")
    
    async def cleanup_browser_session(self) -> None:
        """Proper browser resource cleanup."""
        try:
            if self.page:
                try:
                    await self.page.close()
                except Exception:
                    pass  # Page might already be closed
                self.page = None
            
            if self.context:
                try:
                    await self.context.close()
                except Exception:
                    pass  # Context might already be closed
                self.context = None
            
            if self.browser:
                try:
                    await self.browser.close()
                except Exception:
                    pass  # Browser might already be closed
                self.browser = None
            
            self.logger.info("Browser session cleaned up")
            
        except Exception as e:
            self.logger.error(f"Error during browser cleanup: {str(e)}")
        
        # Force cleanup of any remaining Playwright resources
        try:
            import gc
            gc.collect()
        except Exception:
            pass
    
    # Helper Methods
    
    async def _check_system_resources(self) -> bool:
        """Check if system has sufficient resources for browser automation."""
        try:
            import psutil
            import gc
            
            # Get system memory info
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            available_memory_mb = memory.available / (1024 * 1024)
            
            # Get CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Get disk usage
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            
            self.logger.info(f"System resources - Memory: {memory_percent:.1f}%, CPU: {cpu_percent:.1f}%, Disk: {disk_percent:.1f}%")
            
            # Check resource thresholds - be more lenient when VNC is enabled
            memory_threshold = 95 if self.tv_config.browser.use_vnc else 85

            if memory_percent > memory_threshold:
                self.logger.warning(f"High memory usage: {memory_percent:.1f}% (threshold: {memory_threshold}%)")
                # Try to free up memory
                gc.collect()
                # For VNC mode, be much more lenient with memory usage
                if not self.tv_config.browser.use_vnc:
                    self.logger.error("Non-VNC mode requires more available memory")
                    return False
                else:
                    self.logger.info("VNC mode: Continuing despite high memory usage (this is normal)")
            
            if cpu_percent > 90:
                self.logger.warning(f"High CPU usage: {cpu_percent:.1f}%")
                return False
            
            if disk_percent > 95:
                self.logger.warning(f"Low disk space: {available_memory_mb:.0f}MB available")
                return False
            
            # Check for available file descriptors
            try:
                import resource
                fd_soft, fd_hard = resource.getrlimit(resource.RLIMIT_NOFILE)
                # This is just a basic check - we can't easily check actual usage
                if fd_soft < 1024:
                    self.logger.warning(f"Low file descriptor limit: {fd_soft}")
            except Exception:
                pass  # Not critical on all systems
            
            return True
            
        except ImportError:
            # psutil not available, proceed with caution
            self.logger.warning("psutil not available - skipping resource checks")
            return True
        except Exception as e:
            self.logger.warning(f"Error checking system resources: {str(e)}")
            return True  # Proceed anyway if resource check fails
    
    def _force_cleanup_playwright(self) -> None:
        """Force cleanup of Playwright processes."""
        try:
            import psutil
            import signal
            
            # Find and kill any orphaned Playwright/Chromium processes
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if any(name in proc.info['name'].lower() for name in ['chromium', 'chrome', 'playwright']):
                        self.logger.info(f"Killing orphaned process: {proc.info['name']} (PID: {proc.info['pid']})")
                        proc.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
        except ImportError:
            pass  # psutil not available
        except Exception as e:
            self.logger.warning(f"Error during force cleanup: {str(e)}")
    
    async def _respect_rate_limits(self) -> None:
        """Implement rate limiting to respect TradingView terms."""
        # Handle case where rate_limit config is None
        if not self.tv_config or not self.tv_config.rate_limit:
            return
        if not self.tv_config.rate_limit.respect_rate_limits:
            return

        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        min_delay = self.tv_config.rate_limit.delay_between_requests

        if time_since_last < min_delay:
            sleep_time = min_delay - time_since_last
            self.logger.info(f"Rate limiting: sleeping for {sleep_time:.2f} seconds")
            await asyncio.sleep(sleep_time)

        self.last_request_time = time.time()

    async def _load_session_from_db(self) -> dict | None:
        """Load encrypted session from database (supports both SQLite and PostgreSQL)."""
        try:
            from trading_bot.core.secrets_manager import SecretsManager
            username = os.getenv('TRADINGVIEW_EMAIL', '')

            conn = get_connection()

            # Check if table exists (tradingview_sessions for PostgreSQL, sessions for SQLite)
            if DB_TYPE == 'postgres':
                table_check = query_one(conn, """
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'tradingview_sessions'
                    )
                """)
                if not table_check or not table_check[0]:
                    conn.close()
                    return None

                # Get most recent valid session
                row = query_one(conn, """
                    SELECT encrypted_data FROM tradingview_sessions
                    WHERE username = ? AND is_valid = true
                    ORDER BY created_at DESC LIMIT 1
                """, (username,))
            else:
                # SQLite
                table_check = query_one(conn, """
                    SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'
                """)
                if not table_check:
                    conn.close()
                    return None

                # Get most recent valid session
                row = query_one(conn, """
                    SELECT encrypted_data FROM sessions
                    WHERE username = ? AND is_valid = 1
                    ORDER BY created_at DESC LIMIT 1
                """, (username,))

            conn.close()

            if not row:
                return None

            # Decrypt session data
            secrets = SecretsManager()
            encrypted_data = row[0] if isinstance(row, tuple) else row.get('encrypted_data')
            decrypted = secrets.decrypt(encrypted_data)
            self.logger.info(f"✅ Loaded session from {DB_TYPE} database for user: {username}")
            return json.loads(decrypted)

        except Exception as e:
            self.logger.debug(f"Could not load session from database: {e}")
            return None
    
    async def _save_session_data(self) -> None:
        """Save current session data to database (encrypted only - no file storage)."""
        try:
            if not self.context:
                return

            cookies = await self.context.cookies()
            session_data = {
                'timestamp': time.time(),
                'cookies': cookies,
                'user_agent': getattr(self, '_current_user_agent', get_random_user_agent()),
                'saved_by': 'sourcer'
            }

            # Save to database only (encrypted)
            await self._save_session_to_db(session_data)

            self.session_data = session_data
            self.logger.info(f"✅ Session saved to database ({len(cookies)} cookies, user_agent stored)")

        except Exception as e:
            self.logger.warning(f"Failed to save session data: {str(e)}")

    async def _save_session_to_db(self, session_data: dict) -> None:
        """Save session to database with encryption (supports both SQLite and PostgreSQL)."""
        try:
            from trading_bot.core.secrets_manager import SecretsManager
            username = os.getenv('TRADINGVIEW_EMAIL', 'unknown')

            # Encrypt session data
            secrets = SecretsManager()
            encrypted = secrets.encrypt(json.dumps(session_data))

            conn = get_connection()

            if DB_TYPE == 'postgres':
                # Create tradingview_sessions table if not exists (custom table to avoid Supabase auth conflict)
                execute(conn, """
                    CREATE TABLE IF NOT EXISTS tradingview_sessions (
                        id SERIAL PRIMARY KEY,
                        username TEXT NOT NULL,
                        encrypted_data TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP,
                        is_valid BOOLEAN DEFAULT true
                    )
                """)

                # Invalidate old sessions for this user
                execute(conn, "UPDATE tradingview_sessions SET is_valid = false WHERE username = ?", (username,))

                # Insert new session
                execute(conn, """
                    INSERT INTO tradingview_sessions (username, encrypted_data, is_valid)
                    VALUES (?, ?, true)
                """, (username, encrypted))
            else:
                # SQLite
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
                execute(conn, "UPDATE sessions SET is_valid = 0 WHERE username = ?", (username,))

                # Insert new session
                execute(conn, """
                    INSERT INTO sessions (username, encrypted_data, is_valid)
                    VALUES (?, ?, 1)
                """, (username, encrypted))

            conn.commit()
            conn.close()
            self.logger.info(f"✅ Session saved to {DB_TYPE} database for user: {username}")

        except Exception as e:
            self.logger.warning(f"Could not save session to database: {e}")
    
    async def _test_existing_session(self) -> bool:
        """Test if the existing session is still valid by checking current page state."""
        if not self.page:
            return False

        try:
            # Try to access a protected page to test session validity
            current_url = self.page.url
            self.logger.info(f"Testing session validity from current URL: {current_url}")

            # If we're already on a chart page, try to access user menu
            if 'chart' in current_url and 'signin' not in current_url:
                # Check for user menu which indicates authentication
                user_menu_selectors = [
                    '.user-menu',
                    '.profile-menu',
                    '[data-testid="user-menu"]',
                    '[class*="user"]',
                    '[class*="profile"]'
                ]

                for selector in user_menu_selectors:
                    try:
                        element = await self.page.query_selector(selector)
                        if element:
                            is_visible = await element.is_visible()
                            if is_visible:
                                self.logger.info(f"Found user menu element: {selector} - session appears valid")
                                return True
                    except Exception:
                        continue

                # Try to access settings page briefly
                try:
                    await self.page.goto("https://www.tradingview.com/settings/", timeout=10000)
                    await asyncio.sleep(1)

                    # Check if we got redirected to login
                    current_url_after = self.page.url
                    if 'signin' not in current_url_after and 'login' not in current_url_after:
                        # We're still on settings or a valid page
                        self.logger.info("Settings page accessible - session valid")
                        # Go back to chart page
                        await self.page.goto("https://www.tradingview.com/chart/", timeout=10000)
                        return True
                    else:
                        self.logger.info("Redirected to login page - session invalid")
                        return False
                except Exception as e:
                    self.logger.warning(f"Settings page test failed: {str(e)}")
                    # If we can't access settings, assume session is still valid for now
                    return True

            # If we're on login page, session is definitely invalid
            elif 'signin' in current_url or 'login' in current_url:
                self.logger.info("Currently on login page - session invalid")
                return False

            # For other pages, try a quick navigation test
            else:
                try:
                    await self.page.goto("https://www.tradingview.com/chart/", timeout=15000)
                    await asyncio.sleep(2)

                    new_url = self.page.url
                    if 'chart' in new_url and 'signin' not in new_url:
                        self.logger.info("Successfully navigated to chart page - session valid")
                        return True
                    else:
                        self.logger.info("Failed to access chart page - session invalid")
                        return False
                except Exception as e:
                    self.logger.warning(f"Navigation test failed: {str(e)}")
                    return False

        except Exception as e:
            self.logger.warning(f"Session test failed: {str(e)}")
            # If we can't determine, assume session is still valid to avoid unnecessary re-auth
            return True

    async def _detect_login_required_page(self) -> bool:
        """Detect if current page shows 'We can't open this chart layout for you' error.

        This error appears when trying to access a private chart without being logged in.
        Returns True if login is required, False if page is accessible.
        """
        if not self.page:
            return False

        try:
            # Check for the specific error message text
            error_indicators = [
                "We can't open this chart layout for you",
                "you need to log in to see it",
                "please ask the owner to enable chart layout sharing",
                "Go to homepage"
            ]

            page_content = await self.page.content()
            page_content_lower = page_content.lower()

            for indicator in error_indicators:
                if indicator.lower() in page_content_lower:
                    self.logger.warning(f"🔒 Login required - detected: '{indicator}'")
                    return True

            # Also check for specific selectors that indicate the error page
            error_selectors = [
                'text="We can\'t open this chart layout for you"',
                'text="log in"',
                'button:has-text("Go to homepage")',
            ]

            for selector in error_selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        # Verify it's the error page by checking for the homepage button
                        homepage_btn = await self.page.query_selector('button:has-text("Go to homepage")')
                        if homepage_btn:
                            self.logger.warning(f"🔒 Login required - found error page element: {selector}")
                            return True
                except Exception:
                    continue

            return False

        except Exception as e:
            self.logger.debug(f"Error checking for login required page: {str(e)}")
            return False

    async def _check_page_for_login_required(self) -> bool:
        """Check if the current page shows login prompts/text indicating user is not logged in.

        This checks the actual page content (after closing popups) for login indicators,
        not just the URL. TradingView sometimes shows login prompts on the chart page itself.

        Returns True if login is required, False if user appears to be logged in.
        """
        if not self.page:
            return False

        try:
            page_content = await self.page.content()
            page_content_lower = page_content.lower()

            # Indicators that suggest user is NOT logged in
            login_indicators = [
                "sign in",
                "log in",
                "create account",
                "join now",
                "start free trial",
                "get started for free",
                "sign up",
                "register now",
                "we can't open this chart layout for you",
                "you need to log in to see it",
            ]

            # Check for login indicators in page content
            for indicator in login_indicators:
                if indicator in page_content_lower:
                    # Make sure it's not just a menu item - check for prominent placement
                    # Look for login buttons/prompts that are visible
                    try:
                        login_elements = await self.page.query_selector_all(
                            f'button:has-text("{indicator}"), a:has-text("{indicator}"), '
                            f'[class*="signin"], [class*="login"], [class*="auth"]'
                        )
                        for elem in login_elements:
                            if await elem.is_visible():
                                self.logger.warning(f"🔒 Login indicator found: '{indicator}'")
                                return True
                    except Exception:
                        pass

            # Also check for user menu/avatar which indicates logged in state
            logged_in_indicators = [
                '.tv-header__user-menu-button',
                '[data-name="user-button"]',
                '.user-menu',
                '.tv-header__user-menu',
                '[class*="userMenu"]',
                '[class*="avatar"]',
            ]

            for selector in logged_in_indicators:
                try:
                    elem = await self.page.query_selector(selector)
                    if elem and await elem.is_visible():
                        self.logger.info(f"✅ Logged in indicator found: {selector}")
                        return False  # User IS logged in
                except Exception:
                    continue

            # If we didn't find positive logged-in indicators, be cautious
            # Check if watchlist is accessible (would indicate logged in)
            try:
                watchlist = await self.page.query_selector('[data-name="watchlist"]')
                if watchlist:
                    return False  # Watchlist found, probably logged in
            except Exception:
                pass

            # Default: assume logged in if no login prompts found
            return False

        except Exception as e:
            self.logger.debug(f"Error checking page for login required: {str(e)}")
            return False

    async def _handle_login_required_and_retry(self) -> bool:
        """Handle login required error by prompting manual login, saving session, and retrying.

        Returns True if login was successful and session saved.
        """
        self.logger.warning("🔐 Private chart detected - manual login required!")
        print("\n" + "="*80)
        print("🔒 PRIVATE CHART - LOGIN REQUIRED")
        print("="*80)
        print("The chart you're trying to access is private and requires authentication.")
        print("Please log in manually in the browser window.")
        print("After logging in, return here and press ENTER to continue.")
        print("Your session will be saved for future use.")
        print("="*80 + "\n")

        # Trigger manual login flow
        success = await self._handle_manual_login()

        if success:
            self.logger.info("✅ Login successful - session saved for future use")
            return True
        else:
            self.logger.error("❌ Manual login failed or was cancelled")
            return False

    async def _is_authenticated(self) -> bool:
        """Check if currently authenticated with TradingView by trying to access settings page."""
        if not self.page:
            return False

        try:
            # Try to navigate to the settings page (requires authentication)
            self.logger.info("Checking authentication by accessing settings page...")
            await self.page.goto("https://www.tradingview.com/settings/", timeout=self.tv_config.browser.timeout)
            await self.page.wait_for_load_state('networkidle')
            await asyncio.sleep(2)  # Give time for page to load

            current_url = self.page.url
            self.logger.info(f"Settings page check - Current URL: {current_url}")

            # Check for login message or login button on the settings page
            login_indicators = [
                'button:has-text("Log in")',
                'a:has-text("Log in")',
                'button:has-text("Sign in")',
                'a:has-text("Sign in")',
                ':has-text("Please log in")',
                ':has-text("Please sign in")',
                ':has-text("You need to log in")',
                ':has-text("Login required")',
                '[href*="signin"]',
                '[href*="login"]'
            ]

            for selector in login_indicators:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        self.logger.info(f"❌ Found login indicator: {selector} - not authenticated")
                        return False
                except Exception:
                    continue

            # If no login indicators found, we're authenticated
            self.logger.info("✅ No login indicators found on settings page - authenticated")
            return True

        except Exception as e:
            self.logger.warning(f"Authentication check failed: {str(e)}")
            return False
    
    async def _check_for_captcha(self) -> bool:
        """Check if CAPTCHA is present on the page."""
        if not self.page:
            return False

        try:
            # Common CAPTCHA selectors
            captcha_selectors = [
                '.captcha',
                '[class*="captcha"]',
                '.recaptcha',
                '[class*="recaptcha"]',
                '.g-recaptcha',
                '#captcha',
                '[id*="captcha"]',
                '.hcaptcha',
                '[class*="hcaptcha"]',
                'iframe[src*="recaptcha"]',
                'iframe[src*="hcaptcha"]'
            ]

            for selector in captcha_selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        self.logger.info(f"CAPTCHA detected with selector: {selector}")
                        return True
                except Exception:
                    continue

            return False

        except Exception as e:
            self.logger.warning(f"CAPTCHA check failed: {str(e)}")
            return False

    async def _verify_vnc_connection(self) -> bool:
        """Verify VNC display is available when VNC is enabled."""
        if not self.tv_config.browser.use_vnc:
            return True  # Skip if VNC not enabled

        try:
            display = os.environ.get('DISPLAY', self.tv_config.browser.vnc_display)

            # Check if Xvfb process is running
            result = await asyncio.create_subprocess_exec(
                'pgrep', '-f', f'Xvfb {display}',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                self.logger.info(f"✅ VNC display {display} is active")
                return True
            else:
                self.logger.warning(f"⚠️ VNC display {display} not detected")
                self.logger.warning("Make sure to run: ./setup-playwright-vnc.sh")
                return False
        except Exception as e:
            self.logger.warning(f"Could not verify VNC: {str(e)}")
            return False

    async def _check_page_responsiveness(self) -> bool:
        """Check if the current page is responsive and not stuck loading."""
        if not self.page:
            return False

        try:
            # Try to execute a simple JavaScript command to check if page is responsive
            result = await self.page.evaluate("""
                () => {
                    try {
                        // Check if document is ready
                        if (document.readyState !== 'complete') {
                            return {responsive: false, state: document.readyState};
                        }

                        // Check if there are any loading indicators or spinners
                        const loadingElements = document.querySelectorAll('[class*="loading"], [class*="spinner"], [class*="progress"]');
                        if (loadingElements.length > 0) {
                            return {responsive: false, loadingElements: loadingElements.length};
                        }

                        // Check if main content is visible
                        const mainContent = document.querySelector('main, .main, #main, body > div:first-child');
                        if (mainContent && mainContent.offsetHeight === 0) {
                            return {responsive: false, contentHidden: true};
                        }

                        return {responsive: true};
                    } catch (error) {
                        return {responsive: false, error: error.message};
                    }
                }
            """)

            if result.get('responsive'):
                self.logger.debug("Page is responsive")
                return True
            else:
                self.logger.warning(f"Page not responsive: {result}")
                return False

        except Exception as e:
            self.logger.error(f"Error checking page responsiveness: {str(e)}")
            return False

    async def _check_browser_connection_health(self) -> bool:
        """Check if the browser connection is healthy and responsive."""
        if not self.page:
            self.logger.debug("No page available for connection check")
            return False

        try:
            # Try multiple approaches to test browser health

            # Approach 1: Check if page is closed
            try:
                is_closed = self.page.is_closed()
                if is_closed:
                    self.logger.error("Browser page is closed")
                    return False
            except Exception:
                # Some browsers might not support is_closed()
                pass

            # Approach 2: Try to get page URL
            try:
                url = self.page.url
                if url and len(url) > 0:
                    self.logger.debug(f"Browser page has URL: {url}")
                else:
                    self.logger.debug("Browser page has no URL yet")
            except Exception as e:
                self.logger.warning(f"Could not get page URL: {str(e)}")

            # Approach 3: Try to get page title (with fallback)
            try:
                title = await self.page.title()
                if title and len(title.strip()) > 0:
                    self.logger.debug(f"Browser connection is healthy - title: {title}")
                    return True
                else:
                    self.logger.debug("Browser page has empty title, but connection might still be OK")
                    # Don't fail just because title is empty - page might not be loaded yet
            except Exception as e:
                error_msg = str(e)
                if "Connection closed" in error_msg or "connection" in error_msg.lower():
                    self.logger.error(f"Browser connection is dead: {error_msg}")
                    return False
                else:
                    self.logger.debug(f"Could not get page title: {error_msg}")

            # Approach 4: Try to evaluate a simple JavaScript expression
            try:
                result = await self.page.evaluate("() => { return 'test'; }")
                if result == 'test':
                    self.logger.debug("Browser JavaScript execution works")
                    return True
                else:
                    self.logger.warning(f"Unexpected JavaScript result: {result}")
            except Exception as e:
                error_msg = str(e)
                if "Connection closed" in error_msg or "connection" in error_msg.lower():
                    self.logger.error(f"Browser connection is dead: {error_msg}")
                    return False
                else:
                    self.logger.debug(f"JavaScript execution failed: {error_msg}")

            # If we get here, the connection might be unhealthy but not completely dead
            self.logger.warning("Browser connection health check inconclusive - assuming unhealthy")
            return False

        except Exception as e:
            self.logger.error(f"Error checking browser connection health: {str(e)}")
            return False

    async def _restart_browser_with_session_recovery(self) -> bool:
        """Restart browser session while preserving authentication."""
        self.logger.info("Attempting browser restart with session recovery...")

        try:
            # Clean up current session
            await self.cleanup_browser_session()

            # Setup fresh browser session (also loads session data with cookies & user_agent)
            if not await self.setup_browser_session():
                self.logger.error("Failed to setup fresh browser session")
                return False

            # Navigate to chart page to restore state
            if self.page:
                self.logger.info("Restoring browser state after restart...")
                await self.page.goto("https://www.tradingview.com/chart/", timeout=30000)
                await self.page.wait_for_load_state('domcontentloaded')
                await asyncio.sleep(3)
            else:
                self.logger.error("No page available after browser restart")
                return False

            self.logger.info("Browser restart with session recovery completed")
            return True

        except Exception as e:
            self.logger.error(f"Browser restart failed: {str(e)}")
            return False

    async def _check_browser_running(self) -> bool:
        """Check if the browser is running and properly initialized."""
        try:
            # Check if browser instance exists
            if not self.browser:
                self.logger.debug("Browser instance is None")
                return False

            # Check if context exists
            if not self.context:
                self.logger.debug("Browser context is None")
                return False

            # Check if page exists
            if not self.page:
                self.logger.debug("Browser page is None")
                return False

            # Try to get browser info to verify it's still running
            try:
                # Access browser version as a property (not a method)
                browser_info = getattr(self.browser, 'version', None)
                if browser_info:
                    self.logger.debug(f"Browser is running: {browser_info}")
                    return True
                else:
                    self.logger.warning("Browser version check returned empty")
                    return False
            except Exception as e:
                self.logger.warning(f"Browser version check failed: {str(e)}")
                return False

        except Exception as e:
            self.logger.error(f"Error checking browser status: {str(e)}")
            return False

    async def _wait_for_captcha_confirmation(self) -> bool:
        """
        Wait for CAPTCHA confirmation from either terminal input OR Telegram (whichever comes first).
        
        Returns:
            True if confirmed, False if cancelled or timeout
        """
        import threading
        
        # Create a shared result container
        result_container = {"confirmed": None, "completed": False}
        
        def terminal_input_handler():
            """Handle terminal input in a separate thread"""
            try:
                input()  # Wait for ENTER key
                if not result_container["completed"]:
                    result_container["confirmed"] = True
                    result_container["completed"] = True
            except KeyboardInterrupt:
                if not result_container["completed"]:
                    result_container["confirmed"] = False
                    result_container["completed"] = True
            except Exception:
                if not result_container["completed"]:
                    result_container["confirmed"] = False
                    result_container["completed"] = True
        
        async def telegram_handler():
            """Handle Telegram confirmation"""
            # try:
            #     # Try to get VNC connection info
            #     vnc_info = self._get_vnc_info()
                
            #     # Try to import and use the Telegram controller
            #     try:
            #         # Check if Telegram controller exists before importing
            #         import os
            #         telegram_controller_path = os.path.join(os.path.dirname(__file__), 'telegram_controller.py')
            #         if os.path.exists(telegram_controller_path):
            #             from trading_bot.core.telegram_controller import get_telegram_controller
                        
            #             # Get telegram controller instance
            #             telegram_controller = get_telegram_controller()
                        
            #             # Create a callback to handle confirmation
            #             def on_captcha_confirmed():
            #                 if not result_container["completed"]:
            #                     result_container["confirmed"] = True
            #                     result_container["completed"] = True
                        
            #             # Send CAPTCHA alert with callback
            #             await telegram_controller.send_captcha_alert("TradingView", on_captcha_confirmed)
                        
            #             # Wait for confirmation (the callback will set the result)
            #             while not result_container["completed"]:
            #                 await asyncio.sleep(0.5)
            #         else:
            #             self.logger.debug("Telegram controller not available, using terminal input only")
                        
            #     except ImportError:
            #         self.logger.debug("Telegram controller not available, using terminal input only")
            #     except Exception as e:
            #         self.logger.error(f"Error with Telegram confirmation: {e}")
                    
            # except Exception as e:
            #     self.logger.error(f"Error in telegram handler: {e}")
        
        # Start terminal input in a separate thread
        terminal_thread = threading.Thread(target=terminal_input_handler, daemon=True)
        terminal_thread.start()
        
        # Start telegram handler as async task
        telegram_task = asyncio.create_task(telegram_handler())
        
        # Wait for either confirmation method to complete (indefinite wait)
        self.logger.info("⏳ Waiting for user confirmation... Press ENTER when login is complete, or use Telegram if available")

        while not result_container["completed"]:
            # Sleep briefly to avoid busy waiting
            await asyncio.sleep(0.1)
        
        # Cancel telegram task if still running
        if not telegram_task.done():
            telegram_task.cancel()
            try:
                await telegram_task
            except asyncio.CancelledError:
                pass
        
        return result_container["confirmed"] or False

    def _get_vnc_info(self) -> dict:
        """Get VNC connection information for CAPTCHA notification"""
        import socket
        
        # Try to get the container's IP address
        try:
            # Get hostname IP (works in Docker)
            hostname = socket.gethostname()
            ip_address = socket.gethostbyname(hostname)
        except Exception:
            ip_address = "localhost"
        
        # Get VNC password from environment or secrets
        vnc_password = "Check secrets"
        try:
            # Try to get VNC password from environment
            vnc_password = os.getenv('VNC_PASSWORD', 'Check secrets')
            
            # Try to get from secrets file if available
            if vnc_password == 'Check secrets':
                try:
                    with open('/run/secrets/vnc_password', 'r') as f:
                        vnc_password = f.read().strip()
                except Exception:
                    pass
        except Exception:
            pass
        
        return {
            "ip": ip_address,
            "port": "5901",
            "password": vnc_password
        }
    
    def _convert_timeframe(self, timeframe: str) -> str:
        """Convert timeframe to TradingView format."""
        timeframe_map = {
            '1m': '1',
            '5m': '5',
            '15m': '15',
            '30m': '30',
            '1h': '60',
            '2h': '120',
            '4h': '240',
            '6h': '360',
            '12h': '720',
            '1d': 'D',
            '1D': 'D',
            '3d': '3D',
            '1w': 'W',
            '1W': 'W',
            '1M': 'M'
        }

        return timeframe_map.get(timeframe.lower(), timeframe)

    def _crop_screenshot(self, image_data: bytes, crop_config: Optional[Dict[str, int]] = None) -> bytes:
        """
        Crop screenshot image based on configuration.

        Args:
            image_data: Raw image bytes
            crop_config: Dictionary with crop parameters:
                        - left: Left margin to crop (pixels)
                        - top: Top margin to crop (pixels)
                        - right: Right margin to crop (pixels)
                        - bottom: Bottom margin to crop (pixels)
                        If None, uses default cropping from config

        Returns:
            Cropped image bytes
        """
        if not IMAGE_PROCESSING_AVAILABLE:
            self.logger.warning("PIL not available, returning original image")
            return image_data

        if not crop_config:
            # Use default crop configuration from config
            crop_config = getattr(self.tv_config.screenshot, 'crop', None)
            if not crop_config:
                # Default crop: remove browser UI elements
                crop_config = {
                    'left': 50,
                    'top': 40,
                    'right': 320,
                    'bottom': 40
                }

        try:
            # Load image from bytes
            image = Image.open(io.BytesIO(image_data))

            # Get original dimensions
            width, height = image.size
            self.logger.debug(f"Original image size: {width}x{height}")

            # Calculate crop box (left, upper, right, lower)
            left = crop_config.get('left', 0)
            top = crop_config.get('top', 0)
            right = width - crop_config.get('right', 0)
            bottom = height - crop_config.get('bottom', 0)

            # Ensure crop box is valid
            if left >= right or top >= bottom:
                self.logger.warning(f"Invalid crop box: left={left}, top={top}, right={right}, bottom={bottom}")
                return image_data

            # Crop the image
            cropped_image = image.crop((left, top, right, bottom))

            # Get cropped dimensions
            cropped_width, cropped_height = cropped_image.size
            self.logger.debug(f"Cropped image size: {cropped_width}x{cropped_height}")

            # Convert back to bytes
            output_buffer = io.BytesIO()
            cropped_image.save(output_buffer, format='PNG')
            cropped_bytes = output_buffer.getvalue()

            self.logger.info(f"Screenshot cropped successfully: {width}x{height} -> {cropped_width}x{cropped_height}")
            return cropped_bytes

        except Exception as e:
            self.logger.error(f"Error cropping screenshot: {str(e)}")
            return image_data
    
    # Integration Methods
    
    def get_chart_with_fallback(self, symbol: str, timeframe: str = "1d") -> Optional[str]:
        """
        Get chart with TradingView automation and fallback to local charts.
        This is the main integration method for the existing workflow.
        """
        if self.tradingview_enabled:
            try:
                # Run async method in sync context
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(
                        self.capture_tradingview_chart(symbol, timeframe)
                    )
                    if result:
                        return result
                finally:
                    loop.close()
            except Exception as e:
                self.logger.error(f"TradingView automation failed: {str(e)}")
        
        # Fallback to local charts
        return self.get_local_chart(symbol, timeframe)
    
    # Watchlist Automation Methods
    
    async def get_watchlist_symbols(self, already_authenticated: bool = False) -> List[str]:
        """Get all symbols from the TradingView watchlist with retry logic and connection recovery.

        Args:
            already_authenticated: If True, skip redundant authentication check since auth was already performed
        """
        if not self.page:
            self.logger.error("No page available for watchlist access")
            return []

        # Get retry configuration from config
        max_attempts = self.config.tradingview.retry.max_attempts
        backoff_factor = self.config.tradingview.retry.backoff_factor
        base_delay = self.config.tradingview.retry.base_delay

        # Add overall timeout for the entire watchlist discovery process (3 minutes max)
        overall_timeout = 3 * 60  # 3 minutes in seconds
        start_time = time.time()

        # Import shutdown handler for proper signal checking
        import signal

        for attempt in range(max_attempts):
            # Check if we've exceeded overall timeout
            elapsed_time = time.time() - start_time
            if elapsed_time > overall_timeout:
                self.logger.error(f"Watchlist discovery timeout after {elapsed_time:.1f} seconds")
                # Ensure browser cleanup on timeout
                await self.cleanup_browser_session()
                return []

            # Check for shutdown signal (Ctrl+C)
            try:
                from trading_bot.core.shutdown_handler import is_shutdown_requested
                if is_shutdown_requested():
                    self.logger.info("Shutdown requested during watchlist discovery")
                    return []
            except ImportError:
                # Fallback to basic signal checking if shutdown handler not available
                pass

            try:
                # Add timeout wrapper around the entire attempt
                attempt_task = asyncio.create_task(self._get_watchlist_symbols_attempt(already_authenticated))
                timeout_task = asyncio.create_task(asyncio.sleep(30))  # 30 second timeout per attempt

                done, pending = await asyncio.wait(
                    [attempt_task, timeout_task],
                    return_when=asyncio.FIRST_COMPLETED
                )

                # Cancel the pending task
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                # Check if we got a result or timed out
                if attempt_task in done:
                    result = await attempt_task
                    if result:
                        self.logger.info(f"✅ Found {len(result)} symbols in watchlist: {result}")
                        return result
                    else:
                        self.logger.warning(f"⚠️ Attempt {attempt + 1} returned no symbols")
                else:
                    self.logger.warning(f"⚠️ Attempt {attempt + 1} timed out after 30 seconds")

                # If not the last attempt, wait before retrying
                if attempt < max_attempts - 1:
                    delay = base_delay * (backoff_factor ** attempt)
                    self.logger.warning(f"⚠️ Attempt {attempt + 1} failed, retrying in {delay}s...")
                    await asyncio.sleep(delay)

            except asyncio.CancelledError:
                self.logger.warning(f"Attempt {attempt + 1} was cancelled")
                break
            except Exception as e:
                self.logger.error(f"Error in attempt {attempt + 1}: {str(e)}")

                # If not the last attempt, wait before retrying
                if attempt < max_attempts - 1:
                    delay = base_delay * (backoff_factor ** attempt)
                    self.logger.warning(f"⚠️ Attempt {attempt + 1} failed with exception, retrying in {delay}s...")
                    await asyncio.sleep(delay)

        # All attempts failed - log final error and return empty list
        self.logger.error(f"❌ All {max_attempts} watchlist discovery attempts failed after {elapsed_time:.1f} seconds")
        return []

    async def _get_watchlist_symbols_attempt(self, already_authenticated: bool = False) -> List[str]:
        """Simple watchlist symbol discovery - if not redirected to login, we're good!

        Args:
            already_authenticated: If True, skip redundant authentication check since auth was already performed
        """
        if not self.page:
            self.logger.error("No page available for watchlist access")
            return []

        try:
            # If already authenticated, skip the redundant authentication check
            if not already_authenticated:
                # Simple flow: Navigate to target chart from config and check if we get redirected to login
                self.logger.info("📊 Navigating to target chart from config to check authentication...")

                try:
                    # Use target_chart from config (must be set in config.yaml)
                    if not self.tv_config.target_chart:
                        self.logger.error("❌ No target_chart configured in config.yaml")
                        return []

                    target_chart_url = self.tv_config.target_chart
                    await self.page.goto(target_chart_url, timeout=30000)
                    await self.page.wait_for_load_state('domcontentloaded')
                    await asyncio.sleep(3)

                    # Check if we got redirected to login
                    current_url = self.page.url
                    if 'signin' in current_url or 'login' in current_url:
                        self.logger.error("❌ Redirected to login - authentication failed")
                        return []

                    # Check for "We can't open this chart layout" error page
                    if await self._detect_login_required_page():
                        self.logger.warning("🔒 Private chart detected - switching to manual login (single attempt)")
                        if await self._handle_manual_login():
                            # Re-navigate after successful login
                            self.logger.info("🔄 Retrying navigation after successful login...")
                            await self.page.goto(target_chart_url, timeout=30000)
                            await self.page.wait_for_load_state('domcontentloaded')
                            await asyncio.sleep(3)

                            # Verify login worked
                            if await self._detect_login_required_page():
                                self.logger.error("❌ Still showing login error after manual login")
                                return []
                        else:
                            self.logger.error("❌ Login failed or cancelled")
                            return []

                    # If NOT redirected to login, we're authenticated and can proceed!
                    self.logger.info("✅ Successfully on target chart - we're authenticated!")
                    self.logger.info(f"📍 Current URL: {current_url}")

                except Exception as e:
                    self.logger.error(f"❌ Chart page navigation failed: {str(e)}")
                    return []
            else:
                # Already authenticated - just ensure we're on a chart page
                self.logger.info("📊 Skipping authentication check (already authenticated)")
                current_url = self.page.url
                if 'chart' not in current_url:
                    self.logger.info("📊 Navigating to standard chart page since we're already authenticated")
                    await self.page.goto("https://www.tradingview.com/chart/", timeout=30000)
                    await self.page.wait_for_load_state('domcontentloaded')
                    await asyncio.sleep(3)

            # Wait for chart to fully load
            await asyncio.sleep(5)  # Increased wait time for watchlist to render

            # Take debug screenshot to see page state (only if browser is alive)
            if self._is_browser_alive():
                try:
                    debug_path = Path(self.debug_dir) / "debug_watchlist.png"
                    await self.page.screenshot(path=str(debug_path))
                    self.logger.info(f"📸 Debug screenshot saved to {debug_path}")
                except Exception as e:
                    self.logger.debug(f"Could not save debug screenshot: {e}")

            # Debug: Log what elements are on the page
            try:
                # Check for common TradingView elements
                page_html = await self.page.content()
                if 'symbolNameText' in page_html:
                    self.logger.info("✅ 'symbolNameText' found in page HTML")
                if 'watchlist' in page_html.lower():
                    self.logger.info("✅ 'watchlist' found in page HTML")
                if 'widgetbar' in page_html.lower():
                    self.logger.info("✅ 'widgetbar' found in page HTML")

                # Search for common crypto symbol patterns in HTML
                import re
                symbol_patterns = re.findall(r'(BTC|ETH|SOL)[A-Z]*USDT?', page_html)
                if symbol_patterns:
                    self.logger.info(f"✅ Found symbols in HTML: {set(symbol_patterns)}")

                # Try to find all elements with symbol-related classes
                all_symbol_elements = await self.page.query_selector_all("[class*='symbol']")
                self.logger.info(f"📋 Found {len(all_symbol_elements)} elements with 'symbol' in class")

                # Also try common list/row elements
                list_elements = await self.page.query_selector_all("[class*='listRow'], [class*='row-'], [class*='item-']")
                self.logger.info(f"📋 Found {len(list_elements)} list/row/item elements")

                # Look for elements with data attributes containing symbols
                data_symbol_elements = await self.page.query_selector_all("[data-symbol], [data-name*='symbol']")
                self.logger.info(f"📋 Found {len(data_symbol_elements)} elements with data-symbol attributes")

                # Log first few class names for debugging
                for i, elem in enumerate(list_elements[:5]):
                    try:
                        class_name = await elem.get_attribute('class')
                        text = await elem.text_content()
                        if text:
                            text = text.strip()[:50]
                        self.logger.info(f"   List Element {i}: class='{class_name[:60] if class_name else ''}' text='{text}'")
                    except:
                        pass
            except Exception as e:
                self.logger.debug(f"Debug element scan failed: {e}")

            # Try multiple selectors for watchlist items (TradingView changes these)
            watchlist_selectors = [
                ".inner-RsFlttSS.symbolNameText-RsFlttSS",  # Original selector
                "[class*='symbolNameText']",  # Partial class match - more flexible
                ".symbolNameText-RsFlttSS",  # Simplified selector
                "[data-name='legend-source-item'] .title-l31H9iuA",  # Legend items
                ".listContainer-RsFlttSS .symbolRow-RsFlttSS .symbolNameText-RsFlttSS",  # Full path
                ".widgetbar-widget-watchlist .symbolRow-RsFlttSS",  # Watchlist widget
                "[class*='listRow'] [class*='symbolName']",  # Alternative
                ".symbol-RsFlttSS",  # Symbol class
            ]

            watchlist_items = []
            used_selector = None

            for selector in watchlist_selectors:
                try:
                    items = await self.page.query_selector_all(selector)
                    if items:
                        watchlist_items = items
                        used_selector = selector
                        self.logger.info(f"✅ Found {len(items)} watchlist items with selector: {selector}")
                        break
                except Exception as e:
                    self.logger.debug(f"Selector {selector} failed: {e}")
                    continue

            if not watchlist_items:
                # Try to open watchlist panel if not visible
                self.logger.info("🔍 Watchlist not found, trying to open watchlist panel...")

                # Try clicking watchlist button
                watchlist_buttons = [
                    "[data-name='watchlists-button']",
                    "button[aria-label*='Watchlist']",
                    ".widgetbar-widget-watchlist",
                    "[class*='watchlist']",
                ]

                for btn_selector in watchlist_buttons:
                    try:
                        btn = await self.page.query_selector(btn_selector)
                        if btn:
                            await btn.click()
                            await asyncio.sleep(2)
                            self.logger.info(f"Clicked watchlist button: {btn_selector}")

                            # Try selectors again
                            for selector in watchlist_selectors:
                                items = await self.page.query_selector_all(selector)
                                if items:
                                    watchlist_items = items
                                    used_selector = selector
                                    self.logger.info(f"✅ Found {len(items)} items after opening panel")
                                    break
                            if watchlist_items:
                                break
                    except Exception:
                        continue

            if not watchlist_items:
                self.logger.warning("No watchlist items found with any selector")
                return []

            # Extract symbol names
            symbols = []
            for item in watchlist_items:
                try:
                    symbol_text = await item.text_content()
                    if symbol_text:
                        # Clean up symbol text (remove exchange prefix if present)
                        clean_symbol = symbol_text.strip()
                        if ':' in clean_symbol:
                            clean_symbol = clean_symbol.split(':')[-1]
                        # Remove .P suffix if present
                        if clean_symbol.endswith('.P'):
                            clean_symbol = clean_symbol[:-2]
                        symbols.append(clean_symbol)
                except Exception as e:
                    self.logger.warning(f"Error reading symbol: {str(e)}")
                    continue

            self.logger.info(f"📋 Found {len(symbols)} symbols in watchlist: {', '.join(symbols[:5])}{'...' if len(symbols) > 5 else ''}")
            return symbols

        except Exception as e:
            self.logger.error(f"Error in watchlist symbols attempt: {str(e)}")
            return []
    
    async def navigate_to_watchlist_symbol(self, symbol_index: int) -> bool:
        """Navigate to a specific symbol in the watchlist by index."""
        if not self.page:
            self.logger.error("No page available for navigation")
            return False

        try:
            # First, ensure we're on the chart page
            current_url = self.page.url
            if 'chart' not in current_url:
                self.logger.info("Navigating to TradingView chart page for symbol navigation")
                await self.page.goto("https://www.tradingview.com/chart/", timeout=30000)
                await self.page.wait_for_load_state('domcontentloaded')
                await asyncio.sleep(3)

            # Detect and close any popups that might interfere with clicking
            await self._detect_and_close_popups()

            # Additional check for any overlay/modal elements that might block clicks
            await self._ensure_no_blocking_overlays()

            # Use the working selector from guided teaching
            watchlist_selector = ".inner-RsFlttSS.symbolNameText-RsFlttSS"

            # Get all watchlist items
            watchlist_items = await self.page.query_selector_all(watchlist_selector)

            if not watchlist_items:
                self.logger.error("No watchlist items found")
                return False

            if symbol_index >= len(watchlist_items):
                self.logger.error(f"Symbol index {symbol_index} out of range (max: {len(watchlist_items)-1})")
                return False

            # Get symbol name for logging
            symbol_text = await watchlist_items[symbol_index].text_content()
            self.logger.info(f"Navigating to symbol {symbol_index}: {symbol_text}")

            # Try multiple click strategies to handle overlays
            click_success = False

            # Strategy 1: Direct click with force
            try:
                await watchlist_items[symbol_index].click(force=True, timeout=5000)
                click_success = True
                self.logger.info(f"Direct click successful for {symbol_text}")
            except Exception as e:
                self.logger.debug(f"Direct click failed: {str(e)}")

                # Strategy 2: Try to scroll element into view first
                try:
                    await watchlist_items[symbol_index].scroll_into_view_if_needed()
                    await asyncio.sleep(1)
                    await watchlist_items[symbol_index].click(force=True, timeout=5000)
                    click_success = True
                    self.logger.info(f"Scroll and click successful for {symbol_text}")
                except Exception as e2:
                    self.logger.debug(f"Scroll and click failed: {str(e2)}")

                    # Strategy 3: Use JavaScript click as last resort
                    try:
                        await self.page.evaluate(f"""
                            () => {{
                                const items = document.querySelectorAll('.inner-RsFlttSS.symbolNameText-RsFlttSS');
                                if (items[{symbol_index}] && items[{symbol_index}].click) {{
                                    items[{symbol_index}].click();
                                    return true;
                                }}
                                return false;
                            }}
                        """)
                        click_success = True
                        self.logger.info(f"JavaScript click successful for {symbol_text}")
                    except Exception as e3:
                        self.logger.error(f"All click strategies failed for {symbol_text}: {str(e3)}")

            if not click_success:
                self.logger.error(f"Failed to click on symbol: {symbol_text}")
                return False

            # Wait for chart to load after successful click
            await asyncio.sleep(3)

            # Verify that we've navigated to the correct symbol by checking the chart
            try:
                # Look for the symbol in the chart header or title
                chart_symbol_selectors = [
                    '.chart-symbol',
                    '[data-symbol]',
                    '.symbol-name',
                    'span[class*="symbol"]'
                ]

                for selector in chart_symbol_selectors:
                    try:
                        element = await self.page.query_selector(selector)
                        if element:
                            chart_symbol = await element.text_content()
                            if chart_symbol and symbol_text and symbol_text.strip() in chart_symbol.upper():
                                self.logger.info(f"Verified navigation to {symbol_text} in chart")
                                return True
                    except Exception:
                        continue

                # If we can't verify, assume success and continue
                self.logger.info(f"Navigation completed for {symbol_text} (verification not available)")
                return True

            except Exception as e:
                self.logger.warning(f"Could not verify navigation for {symbol_text}: {str(e)}")
                return True  # Assume success

        except Exception as e:
            self.logger.error(f"Error navigating to symbol {symbol_index}: {str(e)}")
            return False

    async def _ensure_no_blocking_overlays(self) -> None:
        """Ensure there are no blocking overlays before attempting clicks."""
        if not self.page:
            return

        try:
            # Check for common overlay/modal containers that might block clicks
            overlay_selectors = [
                '[id*="overlap"]',
                '[class*="overlap"]',
                '[class*="modal"]',
                '[class*="popup"]',
                '[class*="overlay"]',
                '[data-qa*="overlap"]',
                '.container-VeoIyDt4',  # From the error message
            ]

            for selector in overlay_selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        is_visible = await element.is_visible()
                        if is_visible:
                            self.logger.debug(f"Found potential overlay: {selector}")
                            # Try to close it using Escape key
                            await self.page.keyboard.press('Escape')
                            await asyncio.sleep(1)

                            # Try clicking a close button if it exists
                            close_btn = await element.query_selector('button[class*="close"], .close, [aria-label="Close"]')
                            if close_btn:
                                await close_btn.click()
                                await asyncio.sleep(1)
                                self.logger.info(f"Closed overlay: {selector}")
                except Exception as e:
                    self.logger.debug(f"Error handling overlay {selector}: {str(e)}")

        except Exception as e:
            self.logger.warning(f"Error checking for blocking overlays: {str(e)}")
    
    async def capture_all_watchlist_screenshots(self, output_dir: Optional[str] = None, target_chart: Optional[str] = None, timeframe: Optional[str] = None) -> Dict[str, str]:
        """
        Capture screenshots for all symbols in the watchlist or a specific target chart.
        Skips capturing if charts already exist for the current boundary.

        Args:
            output_dir: Directory to save screenshots (default: data/charts/watchlist_TIMESTAMP)
            target_chart: Optional specific chart URL to capture instead of watchlist
            timeframe: Timeframe for the charts (e.g., '1h', '4h', '1d')

        Returns:
            Dict mapping symbol names to screenshot file paths
        """
        if not self.page:
            self.logger.error("No page available for screenshot capture")
            return {}

        try:
            # Check if charts already exist for current boundary
            if timeframe:
                existing_charts = self.get_charts_for_current_boundary(timeframe)
                if existing_charts:
                    self.logger.info(f"🎯 Reusing {len(existing_charts)} existing charts for current boundary")
                    return existing_charts

            # Setup output directory - save directly to data/charts
            if not output_dir:
                output_path = self.config_dir  # Use the charts directory directly
            else:
                output_path = Path(output_dir)

            output_path.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Saving screenshots to: {output_path}")
            
            # Debug screenshot helper - only takes screenshot if browser is alive
            async def save_debug_screenshot(stage: str):
                """Save debug screenshot for live browser view."""
                if not self._is_browser_alive():
                    self.logger.debug(f"Skipping debug screenshot ({stage}): browser closed")
                    return
                try:
                    debug_path = Path(self.debug_dir) / "debug_watchlist.png"
                    await self.page.screenshot(path=str(debug_path))
                    self.logger.info(f"📸 Debug screenshot: {stage}")
                except Exception as e:
                    self.logger.debug(f"Debug screenshot failed: {e}")

            # SIMPLIFIED FLOW: Just try to get watchlist symbols directly (cookies already loaded)
            # If it fails due to login required, then go to manual login
            self.logger.info("📊 Attempting to access watchlist with stored session cookies...")

            # Navigate to chart page to load watchlist
            try:
                chart_url = target_chart or "https://www.tradingview.com/chart/"
                self.logger.info(f"Navigating to chart: {chart_url}")
                await self.page.goto(chart_url, timeout=30000)
                await self.page.wait_for_load_state('domcontentloaded')
                await asyncio.sleep(3)
                await save_debug_screenshot("after_chart_load")
            except Exception as nav_error:
                self.logger.warning(f"Chart navigation timeout: {nav_error}")
                # Continue anyway - we might still be able to get watchlist

            # Try to get watchlist symbols directly
            symbols = await self.get_watchlist_symbols(already_authenticated=True)

            # If no symbols, check if login is required
            if not symbols:
                self.logger.warning("❌ No symbols found - checking if login required...")
                await self._detect_and_close_popups()

                login_required = await self._check_page_for_login_required()
                current_url = self.page.url if self.page else ""

                if login_required or 'signin' in current_url:
                    self.logger.warning("🔒 Login required - switching to manual login")
                    if await self._handle_manual_login():
                        self.logger.info("✅ Manual login successful - retrying watchlist")
                        # Navigate back to chart and retry
                        chart_url = target_chart or "https://www.tradingview.com/chart/"
                        await self.page.goto(chart_url, timeout=30000)
                        await self.page.wait_for_load_state('domcontentloaded')
                        await asyncio.sleep(3)
                        symbols = await self.get_watchlist_symbols(already_authenticated=True)
                    else:
                        self.logger.error("❌ Manual login failed")
                        return {}
            if not symbols:
                self.logger.error("No symbols found in watchlist")
                return {}

            # Ensure we're on the chart page for symbol navigation
            current_url = self.page.url
            if 'chart' not in current_url:
                self.logger.info("Navigating to TradingView chart page for symbol navigation")
                await self.page.goto("https://www.tradingview.com/chart/", timeout=30000)
                await self.page.wait_for_load_state('domcontentloaded')
                await asyncio.sleep(5)

            # Capture screenshots for each symbol in the watchlist
            screenshot_paths = {}
            successful_captures = 0

            for i, symbol in enumerate(symbols):
                # Check if browser is still alive before each capture
                if not self._is_browser_alive():
                    self.logger.warning("Browser session closed, stopping screenshot capture")
                    break

                try:
                    self.logger.info(f"Processing symbol {i+1}/{len(symbols)}: {symbol}")

                    # Navigate to symbol using watchlist click
                    if await self.navigate_to_watchlist_symbol(i):
                        # Normalize symbol name for filename
                        symbol_clean = symbol.replace('/', '_').replace(':', '_').replace(' ', '_')
                        symbol_clean = normalize_symbol_for_bybit(symbol_clean)

                        # Wait for chart to load after navigation
                        await self.wait_for_chart_load()

                        # Take screenshot with timestamp and timeframe (check browser alive again)
                        if not self._is_browser_alive():
                            self.logger.warning("Browser closed during chart load, stopping")
                            break

                        screenshot_bytes = await self.page.screenshot()

                        # Crop screenshot before saving (if enabled)
                        if getattr(self.tv_config.screenshot, 'enable_crop', True):
                            screenshot_bytes = self._crop_screenshot(screenshot_bytes)

                        # Save using existing method
                        screenshot_path = self.save_chart(screenshot_bytes, symbol_clean, timeframe or "1d")

                        screenshot_paths[symbol] = str(screenshot_path)
                        successful_captures += 1
                        self.logger.info(f"Screenshot saved: {Path(screenshot_path).name}")
                    else:
                        self.logger.error(f"Failed to navigate to symbol: {symbol}")

                except Exception as e:
                    # Check if it's a browser closed error
                    if "Target page, context or browser has been closed" in str(e):
                        self.logger.warning("Browser was closed externally, stopping capture")
                        break
                    self.logger.error(f"Error capturing screenshot for {symbol}: {str(e)}")
                    continue
            
            # Create summary
            summary_file = output_path / "capture_summary.txt"
            with open(summary_file, 'w') as f:
                f.write(f"TradingView Screenshot Summary\n")
                f.write(f"Timestamp: {datetime.now(timezone.utc).isoformat()}\n")
                f.write(f"Timeframe: {timeframe or 'Not specified'}\n")
                f.write(f"Mode: {'Watchlist with Target Chart Auth' if target_chart else 'Watchlist'}\n")

                if target_chart:
                    # Watchlist mode with target chart authentication
                    f.write(f"Authentication URL: {target_chart}\n")
                    f.write(f"Total symbols: {len(symbols)}\n")
                    f.write(f"Successful captures: {successful_captures}\n")
                    f.write(f"Failed captures: {len(symbols) - successful_captures}\n")
                    f.write(f"Success rate: {successful_captures/len(symbols)*100:.1f}%\n\n")
                else:
                    # Standard watchlist mode summary
                    f.write(f"Total symbols: {len(symbols)}\n")
                    f.write(f"Successful captures: {successful_captures}\n")
                    f.write(f"Failed captures: {len(symbols) - successful_captures}\n")
                    f.write(f"Success rate: {successful_captures/len(symbols)*100:.1f}%\n\n")

                f.write("Captured symbols:\n")
                for symbol, path in screenshot_paths.items():
                    f.write(f"  {symbol}: {Path(path).name}\n")

            if target_chart:
                self.logger.info(f"Watchlist capture with target chart auth complete: {successful_captures}/{len(symbols)} successful")
            else:
                self.logger.info(f"Watchlist capture complete: {successful_captures}/{len(symbols)} successful")
            self.logger.info(f"Summary saved: {summary_file}")
            
            return screenshot_paths
            
        except Exception as e:
            self.logger.error(f"Error in watchlist screenshot capture: {str(e)}")
            return {}
    
    def capture_all_watchlist_screenshots_sync(self, output_dir: Optional[str] = None) -> Dict[str, str]:
        """
        Synchronous wrapper for capture_all_watchlist_screenshots.
        This method can be called from non-async code.
        """
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(
                    self.capture_all_watchlist_screenshots(output_dir)
                )
            finally:
                loop.close()
        except Exception as e:
            self.logger.error(f"Error in sync watchlist capture: {str(e)}")
            return {}
    
    async def capture_and_analyze_symbols(self, analyzer, output_dir: Optional[str] = None, target_chart: Optional[str] = None, timeframe: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """
        Capture and analyze screenshots for all symbols in the watchlist in parallel.
        Each chart is analyzed immediately after capture.
        
        Args:
            analyzer: ChartAnalyzer instance for analysis
            output_dir: Directory to save screenshots (default: data/charts)
            target_chart: Optional specific chart URL to capture instead of watchlist
            timeframe: Timeframe for analysis
            
        Returns:
            Dict mapping symbol names to analysis results
        """
        if not self.page:
            self.logger.error("No page available for screenshot capture")
            return {}
        
        try:
            # Setup output directory - save directly to data/charts
            if not output_dir:
                output_path = self.config_dir  # Use the charts directory directly
            else:
                output_path = Path(output_dir)
            
            output_path.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Saving screenshots to: {output_path}")
            
            # Get all symbols from watchlist
            symbols = await self.get_watchlist_symbols()
            if not symbols:
                self.logger.error("No symbols found in watchlist")
                return {}
            
            # Initialize queue for parallel processing
            self.analysis_queue = queue.Queue()
            self.analysis_results = {}
            
            # Start analysis processor in background
            analysis_task = asyncio.create_task(
                self.process_analysis_queue(analyzer, output_path)
            )
            
            # Capture charts in parallel
            capture_tasks = []
            for symbol in symbols:
                task = asyncio.create_task(
                    self.capture_symbol_chart(symbol, output_path, target_chart, timeframe)
                )
                capture_tasks.append(task)
            
            # Wait for all captures to complete
            await asyncio.gather(*capture_tasks)
            
            # Signal analysis processor to stop
            self.analysis_queue.put(None)
            await analysis_task
            
            return self.analysis_results
            
        except Exception as e:
            self.logger.error(f"Error in parallel capture and analysis: {str(e)}")
            return {}
    
    async def capture_symbol_chart(self, symbol: str, output_path: Path, target_chart: Optional[str] = None, timeframe: Optional[str] = None) -> None:
        """Capture chart for a single symbol and queue it for analysis."""
        # Normalize symbol
        normalized_symbol = normalize_symbol_for_bybit(symbol)

        try:
            # Construct chart URL
            if target_chart:
                chart_url = target_chart
            else:
                chart_url = f"https://www.tradingview.com/chart/?symbol={normalized_symbol}"
            
            # Navigate to chart
            if self.page:
                await self.page.goto(chart_url, wait_until='networkidle')
                await asyncio.sleep(2)  # Allow chart to load
                
                # Take screenshot with timeframe
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                screenshot_path = output_path / f"{normalized_symbol}_{timeframe}_{timestamp}.png"
                await self.page.screenshot(path=str(screenshot_path), full_page=True)
            else:
                self.logger.error("No page available for chart capture")
                return
            
            # Queue for analysis
            self.analysis_queue.put({
                'symbol': normalized_symbol,
                'image_path': str(screenshot_path),
                'timeframe': timeframe
            })
            
            self.logger.info(f"Captured and queued {normalized_symbol} for analysis")
            
        except Exception as e:
            self.logger.error(f"Error capturing chart for {normalized_symbol}: {str(e)}")
    
    async def process_analysis_queue(self, analyzer, output_path: Path) -> None:
        """Process analysis queue in parallel with chart capture."""
        try:
            while True:
                item = self.analysis_queue.get()
                
                if item is None:  # Stop signal
                    break
                
                symbol = item['symbol']
                image_path = item['image_path']
                timeframe = item['timeframe']
                
                try:
                    # Analyze the chart
                    analysis_result = await analyzer.analyze_chart_async(
                        image_path=image_path,
                        symbol=symbol,
                        timeframe=timeframe
                    )
                    
                    # Store result
                    self.analysis_results[symbol] = {
                        'analysis': analysis_result,
                        'image_path': image_path,
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    self.logger.info(f"Completed analysis for {symbol}")
                    
                except Exception as e:
                    self.logger.error(f"Error analyzing {symbol}: {str(e)}")
                    self.analysis_results[symbol] = {
                        'error': str(e),
                        'image_path': image_path,
                        'timestamp': datetime.now().isoformat()
                    }
                    
        except Exception as e:
            self.logger.error(f"Error in analysis queue processor: {str(e)}")
    
    async def get_watchlist_symbols_async(self) -> List[str]:
        """Get all symbols from the watchlist before starting capture."""
        try:
            if not self.page:
                self.logger.error("No page available for watchlist access")
                return []
            
            # Navigate to watchlist
            watchlist_url = "https://www.tradingview.com/chart/"
            await self.page.goto(watchlist_url, wait_until='networkidle')
            await asyncio.sleep(3)  # Allow page to fully load
            
            # Get symbols from watchlist
            symbols = []
            
            # Try multiple methods to get symbols
            try:
                # Method 1: Look for watchlist panel
                watchlist_elements = await self.page.query_selector_all('[data-name="symbol-search-item"]')
                for element in watchlist_elements:
                    symbol_text = await element.text_content()
                    if symbol_text:
                        symbols.append(symbol_text.strip())
                        
            except Exception:
                pass
            
            # Method 2: Try to get from URL or page title
            if not symbols:
                page_title = await self.page.title()
                # Extract symbols from title if possible
                import re
                symbol_matches = re.findall(r'([A-Z]{2,})', page_title)
                symbols.extend(symbol_matches)
            
            # Method 3: Use predefined symbols if none found
            if not symbols:
                # Fallback to common symbols for testing
                symbols = ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'NVDA']
                self.logger.warning("Using fallback symbols for testing")
            
            self.logger.info(f"Found {len(symbols)} symbols in watchlist: {symbols}")
            return symbols
            
        except Exception as e:
            self.logger.error(f"Error getting watchlist symbols: {str(e)}")
            return [""]  # Fallback

    async def _authenticate_simplified(self) -> bool:
        """Simplified authentication: Navigate directly to target chart with basic error handling."""
        if not self.page:
            return False

        try:
            self.logger.info("🔐 Direct navigation to target chart")

            # Navigate directly to target chart
            target_url = self.tv_config.target_chart
            if not target_url:
                self.logger.error("No target chart URL configured")
                return False

            await self.page.goto(target_url, timeout=30000)

            # Simple check if we're on a chart page
            current_url = self.page.url
            if 'chart' in current_url and 'signin' not in current_url:
                self.logger.info("✅ Chart page reached successfully")
                return True
            else:
                self.logger.info(f"❌ Not on chart page, current URL: {current_url}")
                return False

        except Exception as e:
            self.logger.warning(f"⚠️ Direct navigation failed: {str(e)}")
            return False

    async def _authenticate_with_retry(self) -> bool:
        """Authenticate with TradingView - single attempt only, NO retries.

        IMPORTANT: Only ONE automated login attempt to avoid TradingView rate limiting.
        The authenticate_tradingview() method already handles manual login as fallback.

        Flow:
        1. Load session from database (done in setup_browser_session)
        2. Go to target chart
        3. If session works → continue
        4. If no valid session → manual login (handled by authenticate_tradingview)
        """
        try:
            self.logger.info("🔐 Single authentication attempt (no retries to avoid rate limiting)")

            # Try standard authentication once - this already includes manual login fallback
            success = await self.authenticate_tradingview()

            if success:
                self.logger.info("✅ Authentication successful")
                return True

            # authenticate_tradingview already tried manual login, so if we're here it failed
            self.logger.error("❌ Authentication failed (including manual login attempt)")
            return False

        except Exception as e:
            self.logger.error(f"Authentication failed with error: {str(e)}")
            return False

    async def _try_existing_session(self) -> bool:
        """Try to authenticate using existing session data (never consider session expired)."""
        if not self.page:
            return False

        try:
            # Check if we have session data
            if self.session_data:
                self.logger.info("Found session file - trying to use existing session")

                # Try to navigate to target chart
                target_url = self.tv_config.target_chart
                if target_url:
                    await self.page.goto(target_url, timeout=30000)  # 30 seconds

                    # Use the same reliable authentication check as manual login
                    if await self._is_authenticated():
                        self.logger.info("✅ Existing session is valid")
                        return True
                    else:
                        self.logger.info("❌ Existing session is invalid")
                        return False
                else:
                    self.logger.error("No target chart URL configured")
                    return False
            else:
                self.logger.info("No session file found")
                return False

        except Exception as e:
            self.logger.warning(f"Error trying existing session: {str(e)}")
            return False

    async def _ensure_authentication(self) -> bool:
        """Ensure we're properly authenticated before accessing protected pages."""
        if not self.page:
            self.logger.error("No page available for authentication check")
            return False

        try:
            # First try to use existing session
            if await self._try_existing_session():
                self.logger.info("✅ Existing session is valid")
                return True

            # If existing session fails, try simplified authentication
            if await self._authenticate_simplified():
                self.logger.info("✅ Simplified authentication successful")
                return True

            # If both fail, try manual login as last resort
            self.logger.info("🔐 Both session methods failed, trying manual login...")
            return await self._handle_manual_login()

        except Exception as e:
            self.logger.error(f"Authentication check failed: {str(e)}")
            return False

    async def _handle_manual_login(self) -> bool:
        """Handle manual login by opening browser and waiting for dashboard confirmation.

        This function:
        1. Sets login state to 'waiting_for_login' for dashboard to detect
        2. In VNC mode: waits for user to click "Open Browser" button before launching browser
        3. In local mode: immediately switches to visible browser
        4. Navigates to TradingView signin page
        5. Polls for dashboard confirmation (user clicks 'Confirm Login' button)
        6. Verifies login, saves session, and continues
        """
        from trading_bot.core.login_state_manager import (
            set_waiting_for_login, set_waiting_for_browser_open, set_browser_opened,
            is_login_confirmed, is_browser_open_requested, set_idle, get_login_state, LoginState
        )

        try:
            original_headless = self.tv_config.browser.headless

            # VNC MODE: Wait for user to click "Open Browser" button before launching browser
            if self.tv_config.browser.use_vnc:
                self.logger.info("🖥️ VNC mode detected - waiting for user to click 'Open Browser' button")
                set_waiting_for_browser_open("Click 'Open Browser' to start VNC and launch browser")

                # Poll for browser open request (max 5 minutes)
                max_wait_seconds = 300
                poll_interval = 2
                waited = 0

                while waited < max_wait_seconds:
                    if is_browser_open_requested():
                        self.logger.info("✅ Browser open requested - VNC is ready, launching browser")
                        break

                    await asyncio.sleep(poll_interval)
                    waited += poll_interval

                if waited >= max_wait_seconds:
                    self.logger.error("❌ Timeout waiting for browser open request")
                    set_idle()
                    return False
            else:
                # LOCAL MODE: Set state immediately
                set_waiting_for_login("TradingView session expired - manual login required")
                self.logger.info("🔐 Manual login required - notifying dashboard")

            # Switch to non-headless mode for manual login
            if self.tv_config.browser.headless:
                self.logger.info("🔄 Switching to visible browser mode for manual login")
                await self.cleanup_browser_session()
                self.tv_config.browser.headless = False

                # Restart browser session in visible mode
                if not await self.setup_browser_session():
                    self.logger.error("Failed to restart browser in visible mode")
                    self.tv_config.browser.headless = original_headless
                    set_idle()
                    return False

            # Check if page is available
            if not self.page:
                self.logger.error("No browser page available for manual login")
                self.tv_config.browser.headless = original_headless
                set_idle()
                return False

            # Navigate to TradingView homepage (NOT signin page to avoid rate limits)
            # User clicks login button themselves - appears more natural to TradingView
            tv_url = "https://www.tradingview.com/"
            self.logger.info(f"🌐 Opening TradingView: {tv_url}")
            await self.page.goto(tv_url, timeout=30000)
            await self.page.wait_for_load_state('domcontentloaded')

            # Mark browser as opened ONLY if NOT in VNC mode
            # In VNC mode, browser is not visible to user - they need to connect via VNC client
            if not self.tv_config.browser.use_vnc:
                set_browser_opened()
                self.logger.info("📺 Browser opened for manual login - waiting for dashboard confirmation")
            else:
                self.logger.info("🖥️ VNC mode: Browser opened - connect via VNC to login")

            # Poll for dashboard confirmation (max 5 minutes)
            max_wait_seconds = 380
            poll_interval = 2
            waited = 0

            while waited < max_wait_seconds:
                # Check if user confirmed login from dashboard
                if is_login_confirmed():
                    self.logger.info("✅ Login confirmation received from dashboard")
                    break

                await asyncio.sleep(poll_interval)
                waited += poll_interval

                # Log every 30 seconds
                if waited % 30 == 0:
                    self.logger.info(f"⏳ Waiting for login confirmation... ({waited}s / {max_wait_seconds}s)")

            if waited >= max_wait_seconds:
                self.logger.error("❌ Login confirmation timeout - user did not confirm")
                self.tv_config.browser.headless = original_headless
                set_idle()
                return False

            # User confirmed - FIRST save the session from current browser state
            # (before any navigation that might fail)
            self.logger.info("💾 Saving session cookies immediately after confirmation...")
            await self._save_session_data()
            self.logger.info("✅ Session cookies saved to database!")

            # Now try to verify login (optional - if it fails, we still have the session)
            self.logger.info("🔍 Verifying login status...")

            try:
                # Navigate to target chart to verify login
                target_chart = self.tv_config.target_chart or "https://www.tradingview.com/chart/"
                await self.page.goto(target_chart, timeout=60000)  # Increased timeout
                await self.page.wait_for_load_state('domcontentloaded')
                await asyncio.sleep(2)

                # Close any popups
                await self._detect_and_close_popups()
                await asyncio.sleep(1)

                # Check if still showing login required
                login_required = await self._check_page_for_login_required()

                if login_required:
                    self.logger.warning("⚠️ Verification shows login may still be required")
                    self.logger.info("Session was saved - will verify on next run")
                else:
                    self.logger.info("✅ Login verification successful!")

            except Exception as verify_error:
                self.logger.warning(f"⚠️ Verification navigation failed: {verify_error}")
                self.logger.info("Session was saved - will verify on next run")

            self.logger.info("✅ Manual login successful - session saved!")

            # Reset to idle state
            set_idle()

            # Close browser to free resources (especially important on Railway)
            # Session is already saved, browser will be reopened in headless mode when needed
            self.logger.info("🔄 Closing browser to free resources...")
            await self.cleanup_browser_session()

            # Restore headless setting for next browser session
            self.tv_config.browser.headless = original_headless
            return True

        except Exception as e:
            self.logger.error(f"Error during manual login: {str(e)}")
            import traceback
            self.logger.debug(traceback.format_exc())
            set_idle()
            return False
