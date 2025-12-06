# VNC-in-Dashboard Login Setup

## Overview

This feature enables TradingView manual login on Railway (headless server) by embedding a web-based VNC viewer directly in the dashboard.

## How It Works

1. **Railway Detection**: Bot automatically detects Railway environment and enables VNC mode
2. **VNC Server**: Xvfb + x11vnc + noVNC run in Docker container
3. **Dashboard Integration**: noVNC viewer embedded in modal for seamless UX
4. **Session Persistence**: Login session saved to PostgreSQL database

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
  - Embedded noVNC viewer in modal
  - Connection status checking
  - Login confirmation flow

- **`app/api/vnc/status/route.ts`**
  - Check VNC availability
  - Return connection info

- **`app/api/vnc/proxy/route.ts`**
  - Proxy noVNC requests (avoid CORS)

- **`next.config.js`**
  - Rewrite `/vnc/*` to `http://localhost:6080/*`

### Infrastructure

- **`Dockerfile`**
  - Install VNC dependencies (Xvfb, x11vnc, fluxbox, noVNC)
  - Expose port 6080 for noVNC
  - Set `DISPLAY=:99` environment variable

- **`supervisord.conf`**
  - Manage all services (Xvfb, fluxbox, x11vnc, noVNC, app)
  - Auto-restart on failure

## Environment Variables

- `RAILWAY_ENVIRONMENT` - Auto-set by Railway (triggers VNC mode)
- `RAILWAY_SERVICE_NAME` - Auto-set by Railway (alternative detection)
- `DISPLAY` - Set to `:99` for VNC display
- `VNC_PORT` - noVNC port (default: 6080)
- `VNC_ENABLED` - Enable/disable VNC (default: true)

## Testing

### Local Testing (without Railway)

VNC mode will NOT activate locally. Use the standard manual login flow (visible browser window).

### Railway Testing

1. Deploy to Railway
2. Trigger TradingView login requirement (expire session or first run)
3. Check dashboard for "Manual Login Required" banner
4. Click "Open Browser Login"
5. Verify noVNC viewer loads in modal
6. Complete TradingView login
7. Click "Confirm Login"
8. Verify session saved and bot continues

## Troubleshooting

### VNC Not Available

**Symptom**: Modal shows "VNC Not Available"

**Causes**:
- Not running on Railway (local development)
- VNC services not started (check supervisor logs)
- Port 6080 not exposed

**Solution**:
```bash
# Check supervisor status
supervisorctl status

# Check noVNC logs
tail -f /var/log/supervisor/novnc-stdout.log

# Restart VNC services
supervisorctl restart xvfb fluxbox x11vnc novnc
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

**Symptom**: VNC viewer shows "Connection timeout"

**Causes**:
- noVNC not running
- Port 6080 not accessible
- Next.js rewrite not working

**Solution**:
```bash
# Check noVNC is running
curl http://localhost:6080/vnc.html

# Check port is listening
netstat -tulpn | grep 6080

# Restart noVNC
supervisorctl restart novnc
```

## Security Considerations

- VNC server runs without password (internal only)
- noVNC only accessible through Next.js proxy
- Railway provides network isolation
- Session data encrypted in database

## Future Enhancements

- [ ] Add VNC password authentication
- [ ] Add session upload fallback (if VNC fails)
- [ ] Add VNC recording for debugging
- [ ] Add multi-user support (separate VNC sessions)

