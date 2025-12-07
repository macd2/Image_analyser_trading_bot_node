

[ ] add the watchlist symbols from capture page somewhere fitting in the instance card

[ ] is the the value from Confidence Calculation from analysis actually used in the bot for trading deccisions?

------

[ ] run production audit in terms of security, efficency and robustness (minal changes )


--------------

[ ] why are we still have 3 attempt

 2025-12-06 12:18:58 | INFO | trading_bot.core.sourcer | 📊 Skipping authentication check (already authenticated)
2025-12-06 12:19:04 | INFO | trading_bot.core.sourcer | 📸 Debug screenshot saved to data/debug_watchlist.png
2025-12-06 12:19:04 | INFO | trading_bot.core.sourcer | ✅ 'watchlist' found in page HTML
2025-12-06 12:19:04 | INFO | trading_bot.core.sourcer | ✅ 'widgetbar' found in page HTML
2025-12-06 12:19:04 | INFO | trading_bot.core.sourcer | 📋 Found 0 elements with 'symbol' in class
2025-12-06 12:19:04 | INFO | trading_bot.core.sourcer | 📋 Found 4 list/row/item elements
2025-12-06 12:19:04 | INFO | trading_bot.core.sourcer | 📋 Found 0 elements with data-symbol attributes
2025-12-06 12:19:04 | INFO | trading_bot.core.sourcer | List Element 0: class='skip-navigation-item-wCFzoXZN item-jFqVJoPk item-mDJVFqQ3' text='Main content'
2025-12-06 12:19:04 | INFO | trading_bot.core.sourcer | List Element 1: class='row-mDJVFqQ3' text='Main content'
2025-12-06 12:19:04 | INFO | trading_bot.core.sourcer | List Element 2: class='tv-header__main-menu-item tv-header__main-menu-item--highlig' text='Community'
2025-12-06 12:19:04 | INFO | trading_bot.core.sourcer | List Element 3: class='item-JUpQSPBo itemStable-JUpQSPBo' text='This website uses cookies. Our policyDon't allowAc'
2025-12-06 12:19:04 | INFO | trading_bot.core.sourcer | 🔍 Watchlist not found, trying to open watchlist panel...
2025-12-06 12:19:04 | WARNING | trading_bot.core.sourcer | No watchlist items found with any selector
2025-12-06 12:19:04 | WARNING | trading_bot.core.sourcer | ⚠️ Attempt 3 returned no symbols
2025-12-06 12:19:04 | ERROR | trading_bot.core.sourcer | ❌ All 3 watchlist discovery attempts failed after 13.6 seconds
2025-12-06 12:19:06 | WARNING | trading_bot.core.sourcer | ❌ No symbols found - checking if login required...
2025-12-06 12:19:06 | INFO | trading_bot.core.sourcer | 🔍 Detecting and closing popups...
2025-12-06 12:19:06 | INFO | trading_bot.core.sourcer | No close button found, trying Escape key...
2025-12-06 12:19:07 | INFO | trading_bot.core.sourcer | ✅ Escape key pressed
2025-12-06 12:19:07 | INFO | trading_bot.core.sourcer | Popup detection and closing completed
2025-12-06 12:19:07 | WARNING | trading_bot.core.sourcer | 🔒 Login indicator found: 'log in'
2025-12-06 12:19:07 | WARNING | trading_bot.core.sourcer | 🔒 Login required - switching to manual login
2025-12-06 12:19:07 | INFO | trading_bot.core.login_state_manager | Login state set to: waiting_for_login
2025-12-06 12:19:07 | INFO | trading_bot.core.sourcer | 🔐 Manual login required - notifying dashboard
2025-12-06 12:19:07 | INFO | trading_bot.core.sourcer | 🔄 Switching to visible browser mode for manual login


[ ]   restore sourcer vnc settings 

                        '--start-maximized',  # Start browser maximized
                            '--kiosk',  # Fullscreen mode for VNC
                            '--app-window',  # App window mode
                            '--window-position=0,0',  # Position at top-left
                            # Critical flags for Linux server compatibility
                            '--disable-dev-shm-usage',  # Overcome limited resource problems
                            '--disable-accelerated-2d-canvas',  # Disable accelerated 2D canvas
                            '--no-first-run',  # Skip first run experience
                            '--disable-default-apps',  # Disable default apps
                            '--disable-extensions',  # Disable extensions for stability
                            '--disable-plugins',  # Disable plugins
                            '--disable-images',  # Disable images to speed up loading
                            '--disable-javascript-harmony',  # Disable experimental JS features
                            '--disable-background-networking',  # Disable background networking
                            '--disable-sync',  # Disable sync
                            '--disable-translate',  # Disable translate
                            '--hide-scrollbars',  # Hide scrollbars
                            '--metrics-recording-only',  # Minimal metrics
                            '--mute-audio',  # Mute audio
                            '--no-default-browser-check',  # Skip default browser check
                            '--disable-component-extensions-with-background-pages',  # Disable background extensions
                            '--disable-features=VizDisplayCompositor',  # Disable display compositor
                            '--disable-accelerated-video-decode',  # Disable accelerated video
                            '--disable-gpu-compositing',  # Disable GPU compositing
                            '--disable-gpu-rasterization',  # Disable GPU rasterization
                            '--disable-background-media-download',  # Disable background media
                            '--disable-print-preview',  # Disable print preview
                            '--disable-component-update',  # Disable component updates
                            # Add flags for better stability on Linux servers
                            '--disable-web-security',  # Allow cross-origin requests
                            '--allow-running-insecure-content',  # Allow insecure content
                            '--ignore-certificate-errors',  # Ignore SSL errors
                            '--ignore-ssl-errors',  # Ignore SSL errors
                            '--ignore-certificate-errors-spki-list',  # Ignore SPKI list
                            '--ignore-ssl-errors-ignore-untrusted',  # Ignore untrusted SSL


