# Railway VNC Setup Guide

This guide explains how to set up VNC access on Railway using TCP Proxy for manual TradingView login.

## Why VNC is Needed

On Railway (headless server environment), when the bot needs manual TradingView login:
1. Bot detects session expired
2. Bot switches to visible browser mode
3. **Problem**: You can't see the browser on Railway
4. **Solution**: VNC allows you to remotely view and control the browser

## Railway TCP Proxy Setup

Railway supports exposing TCP ports (like VNC) using **TCP Proxy** feature.

### Step 1: Enable TCP Proxy in Railway

1. Go to your Railway project
2. Click on your service
3. Go to **Settings** tab
4. Scroll to **Public Networking** section
5. Click **Add TCP Proxy**
6. Enter port: `6080` (noVNC WebSocket port)
7. Railway will generate a public address like: `interchange.proxy.rlwy.net:13575`

### Step 2: Configure Environment Variables

Add these environment variables in Railway:

```bash
# Enable VNC
ENABLE_VNC=true
VNC_PORT=6080

# Railway TCP Proxy configuration (get these from Railway dashboard)
# Example: interchange.proxy.rlwy.net:13575
RAILWAY_TCP_PROXY_DOMAIN=interchange.proxy.rlwy.net
RAILWAY_TCP_PROXY_PORT=13575
```

**Important**: Replace `interchange.proxy.rlwy.net` and `13575` with the actual values from Railway's TCP Proxy settings.

### Step 3: Deploy

Push your changes and Railway will redeploy with VNC enabled.

## Using VNC for Manual Login

### When Login is Required

1. Dashboard will show "Manual Login Required" banner
2. Click **"Open Browser Login"** button
3. Modal will show VNC connection instructions

### Option 1: Desktop VNC Client (Recommended)

1. Download a VNC client:
   - **RealVNC Viewer**: https://www.realvnc.com/en/connect/download/viewer/
   - **TigerVNC**: https://tigervnc.org/
   - **TightVNC**: https://www.tightvnc.com/

2. Connect to the address shown in the modal (e.g., `interchange.proxy.rlwy.net:13575`)

3. No password required

4. You'll see the browser window - log in to TradingView

5. Return to dashboard and click **"Confirm Login"**

### Option 2: Web Browser (noVNC)

1. Click the "Open noVNC" link in the modal
2. Opens noVNC web client in new tab
3. Log in to TradingView
4. Return to dashboard and click **"Confirm Login"**

## Security Considerations

### Is TCP Proxy Secure?

✅ **Yes, when configured properly:**

1. **No authentication required** - VNC server has no password
   - ⚠️ Anyone with the address can connect
   - ✅ Railway generates random port numbers (hard to guess)
   - ✅ Only needed temporarily for login

2. **Recommendations**:
   - Only enable VNC when needed for login
   - Disable TCP Proxy after login is complete
   - Use strong TradingView password
   - Monitor Railway logs for unexpected connections

### Alternative: Disable VNC After Login

If you're concerned about security:

1. Complete the manual login
2. Go to Railway Settings → Public Networking
3. Remove the TCP Proxy (click trash icon)
4. Set `ENABLE_VNC=false` in environment variables
5. Redeploy

The bot will use the saved session until it expires again.

## Troubleshooting

### VNC Not Available

**Check**:
1. `ENABLE_VNC=true` is set in Railway
2. TCP Proxy is configured for port 6080
3. `RAILWAY_TCP_PROXY_DOMAIN` and `RAILWAY_TCP_PROXY_PORT` are set correctly
4. Service has redeployed after changes

**Test**:
- Visit: `https://yourapp.railway.app/api/vnc/test`
- Should show VNC server reachable

### Can't Connect with VNC Client

**Check**:
1. Using correct address from Railway TCP Proxy (not localhost)
2. Port number matches Railway's assigned port
3. VNC client is not behind restrictive firewall
4. Try different VNC client

### Browser Not Visible in VNC

**Check**:
1. Xvfb is running (check Railway logs for "spawned: 'xvfb'")
2. x11vnc is running (check Railway logs for "spawned: 'x11vnc'")
3. noVNC is running (check Railway logs for "spawned: 'novnc'")

## Architecture

```
User's VNC Client
       ↓
Railway TCP Proxy (interchange.proxy.rlwy.net:13575)
       ↓
noVNC WebSocket Server (localhost:6080)
       ↓
x11vnc VNC Server (localhost:5900)
       ↓
Xvfb Virtual Display (:99)
       ↓
Playwright Browser (Chromium)
```

## HTTP and TCP Together

Railway supports **both HTTP and TCP** on the same service:
- HTTP domain: `yourapp.railway.app` (Next.js dashboard)
- TCP Proxy: `interchange.proxy.rlwy.net:13575` (VNC)

Both work simultaneously without conflicts.

