# VNC-in-Dashboard Login Setup

## Overview

This feature enables TradingView manual login on Railway (headless server) using a minimal VNC setup for browser access.

## How It Works

1. **Railway Detection**: Bot automatically detects Railway environment and enables VNC mode
2. **Minimal VNC Server**: Only Xvfb (virtual display) + x11vnc (VNC server) - no window manager or web proxy
3. **Dashboard Integration**: Kill VNC button in modal for lifecycle management
4. **Session Persistence**: Login session saved to PostgreSQL database

## Why Minimal?

The VNC setup is intentionally minimal to prevent browser crashes:
- **No Fluxbox**: Window manager unnecessary for login-only use case
- **No noVNC**: Web proxy disabled for security and stability
- **Minimal browser flags**: Only 5 essential flags to prevent conflicts
- **On-demand lifecycle**: VNC services can be stopped from dashboard when not needed

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Railway Container                                            │
│                                                              │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌─────────┐ │
│  │  Xvfb    │──▶│ Fluxbox  │──▶│  x11vnc  │──▶│ noVNC   │ │
│  │ (DISPLAY │   │ (Window  │   │ (VNC     │   │ (Web    │ │
│  │  :99)    │   │  Manager)│   │  Server) │   │  Viewer)│ │
│  └──────────┘   └──────────┘   └──────────┘   └─────────┘ │
│       │                              │              │       │
│       │                              │              │       │
│       ▼                              ▼              ▼       │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Chromium Browser (Playwright)                        │  │
│  │ - Runs on DISPLAY=:99                                │  │
│  │ - Opens TradingView for manual login                 │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP Proxy (/vnc/*)
                              ▼
                    ┌──────────────────┐
                    │ Next.js Dashboard│
                    │ - VNC Modal      │
                    │ - Embedded Viewer│
                    └──────────────────┘
```

## User Flow

1. **Login Required**: Bot detects TradingView session expired
2. **Dashboard Alert**: Banner shows "Manual Login Required"
3. **Open Browser**: User clicks "Open Browser Login" button
4. **VNC Modal**: Modal opens with embedded noVNC viewer
5. **Manual Login**: User logs in to TradingView in the browser
6. **Confirm**: User clicks "Confirm Login" when done
7. **Session Saved**: Bot verifies login and saves session to database
8. **Continue**: Bot resumes normal operation

## Components

### Backend (Python)

- **`python/trading_bot/core/sourcer.py`**
  - `is_railway_environment()` - Detects Railway platform
  - Auto-enables VNC mode on Railway
  - Sets `DISPLAY=:99` for browser automation

### Frontend (Next.js)

- **`components/VncLoginModal.tsx`**
  - VNC connection instructions
  - Kill VNC button for lifecycle management
  - Login confirmation flow

- **`app/api/vnc/status/route.ts`**
  - Check VNC availability
  - Return connection info (x11vnc only)

- **`app/api/vnc/control/route.ts`**
  - Start/stop/restart VNC services via supervisorctl
  - Used by Kill VNC button

### Infrastructure

- **`Dockerfile`**
  - Install minimal VNC dependencies (Xvfb, x11vnc only)
  - No Fluxbox, no noVNC (removed for stability)
  - Set `DISPLAY=:99` environment variable

- **`supervisord.conf`**
  - Manage minimal services (Xvfb, x11vnc, app)
  - Auto-restart on failure
  - Fluxbox and noVNC removed

## Environment Variables

- `RAILWAY_ENVIRONMENT` - Auto-set by Railway (triggers VNC mode)
- `RAILWAY_SERVICE_NAME` - Auto-set by Railway (alternative detection)
- `DISPLAY` - Set to `:99` for VNC display
- `ENABLE_VNC` - Enable/disable VNC (set to `true` on Railway)
- `RAILWAY_TCP_PROXY_DOMAIN` - Railway TCP proxy domain for x11vnc (port 5900)
- `RAILWAY_TCP_PROXY_PORT` - Railway TCP proxy port for x11vnc

## Testing

### Local Testing (without Railway)

VNC mode will NOT activate locally. Use the standard manual login flow (visible browser window).

### Railway Testing

1. Deploy to Railway
2. Set up Railway TCP Proxy for port 5900 (x11vnc)
3. Set environment variables: `RAILWAY_TCP_PROXY_DOMAIN` and `RAILWAY_TCP_PROXY_PORT`
4. Trigger TradingView login requirement (expire session or first run)
5. Check dashboard for "Manual Login Required" banner
6. Click "Open Browser Login"
7. Use desktop VNC client to connect to the provided address
8. Complete TradingView login in VNC window
9. Click "Confirm Login" in dashboard
10. Click "Kill VNC" to stop VNC services and free resources
11. Verify session saved and bot continues

## Troubleshooting

### VNC Not Available

**Symptom**: Modal shows "VNC Not Available"

**Causes**:
- Not running on Railway (local development)
- VNC services not started (check supervisor logs)
- `ENABLE_VNC` not set to `true`

**Solution**:
```bash
# Check supervisor status
supervisorctl status

# Check VNC logs
tail -f /var/log/supervisor/xvfb.log
tail -f /var/log/supervisor/x11vnc.log

# Restart VNC services (minimal)
supervisorctl restart xvfb x11vnc
```

### Browser Not Visible in VNC

**Symptom**: VNC viewer shows blank screen

**Causes**:
- Browser not using DISPLAY=:99
- Xvfb not running
- Browser crashed

**Solution**:
```bash
# Check DISPLAY variable
echo $DISPLAY  # Should be :99

# Check Xvfb process
ps aux | grep Xvfb

# Check browser logs
tail -f logs/bot.log | grep -i browser
```

### Connection Timeout

**Symptom**: Desktop VNC client shows "Connection timeout"

**Causes**:
- Railway TCP Proxy not configured
- x11vnc not running
- Firewall blocking connection

**Solution**:
```bash
# Check x11vnc is running
supervisorctl status x11vnc

# Check port is listening
netstat -tulpn | grep 5900

# Restart x11vnc
supervisorctl restart x11vnc

# Verify Railway TCP Proxy settings in Railway dashboard
```

### Browser Crashes

**Symptom**: Browser crashes immediately or becomes unresponsive in VNC

**Causes**:
- Too many conflicting browser flags
- Insufficient memory
- VNC services consuming too much resources

**Solution**:
- Browser flags reduced to minimal (5 essential flags only)
- Use "Kill VNC" button to stop services when not needed
- Fluxbox window manager removed to reduce overhead

## Security Considerations

- VNC server runs without password (use Railway TCP Proxy for access control)
- Railway provides network isolation
- Session data encrypted in database
- VNC services can be stopped from dashboard when not in use

## Resource Management

**Image Size Savings**:
- Removed noVNC: ~50MB
- Removed Fluxbox: ~20MB
- Total savings: ~70MB

**Runtime Savings**:
- 2 fewer processes (Fluxbox, noVNC)
- Reduced browser flags = lower memory usage
- On-demand lifecycle = VNC only runs when needed
- [ ] Add VNC recording for debugging
- [ ] Add multi-user support (separate VNC sessions)

