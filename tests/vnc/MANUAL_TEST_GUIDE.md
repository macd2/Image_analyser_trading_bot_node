# VNC Manual Test Guide

Step-by-step manual testing guide for VNC functionality.

## Prerequisites

- Railway deployment with `ENABLE_VNC=true`
- VNC client installed (RealVNC Viewer or TigerVNC)
- Access to Railway dashboard

## Test Scenario 1: Complete VNC Flow

### Setup
1. Navigate to instance overview page
2. Click "VNC Login" button in Account section
3. VNC modal should open

### Test Steps

**Step 1: Start VNC**
- [ ] Click "1. Start VNC" button
- [ ] Button should show "Starting..." spinner
- [ ] Button should remain clickable
- [ ] VNC status indicator should update to "● VNC Running"

**Step 2: Connect VNC Client**
- [ ] Open your VNC client
- [ ] Enter Railway TCP Proxy address (from modal)
- [ ] Port: 5900
- [ ] Connect (no password required)
- [ ] You should see a desktop

**Step 3: Start Browser**
- [ ] Click "2. Start Browser" button
- [ ] Button should show "Starting..." spinner
- [ ] Button should remain clickable
- [ ] Browser should appear in VNC window (may take 10-15 seconds)

**Step 4: Login to TradingView**
- [ ] In VNC window, browser should show TradingView login page
- [ ] Enter your credentials
- [ ] Complete login process
- [ ] Navigate to your chart to verify

**Step 5: Confirm Login**
- [ ] Return to modal
- [ ] Click "3. Confirm Login" button
- [ ] Button should show "Confirming..." spinner
- [ ] Button should remain clickable
- [ ] Modal should close or show success message

**Step 6: Kill VNC**
- [ ] Click "4. Kill VNC" button
- [ ] Button should show "Stopping..." spinner
- [ ] Button should remain clickable
- [ ] VNC connection should close
- [ ] Status indicator should update

## Test Scenario 2: Browser Crash Recovery

### Setup
1. Complete Steps 1-3 from Scenario 1
2. Browser is running in VNC

### Test Steps
- [ ] In VNC window, force browser to crash (Alt+F4 or kill process)
- [ ] Return to modal
- [ ] Click "2. Start Browser" again
- [ ] Button should be clickable (not disabled)
- [ ] New browser should launch
- [ ] Verify you can login again

## Test Scenario 3: Multiple Button Clicks

### Setup
1. Open VNC modal
2. VNC is NOT running

### Test Steps
- [ ] Click "1. Start VNC" 3 times rapidly
- [ ] Each click should work
- [ ] No errors should occur
- [ ] Click "2. Start Browser" 3 times rapidly
- [ ] Each click should work
- [ ] Click "3. Confirm Login" 3 times rapidly
- [ ] Each click should work
- [ ] Click "4. Kill VNC" 3 times rapidly
- [ ] Each click should work

## Test Scenario 4: Button States

### Setup
1. Open VNC modal

### Test Steps
- [ ] All 4 buttons should be visible
- [ ] All 4 buttons should be clickable (no disabled state)
- [ ] Buttons should NOT have opacity-50 or cursor-not-allowed
- [ ] When clicked, button should show spinner but remain clickable
- [ ] VNC status indicator should show current state

## Expected Results

✅ All buttons ALWAYS clickable
✅ No disabled states
✅ Spinners show during loading
✅ Multiple clicks work
✅ Browser crash recovery works
✅ VNC status updates correctly
✅ All 4 steps complete successfully

## Troubleshooting

**Browser doesn't appear in VNC:**
- Wait 15 seconds (Xvfb initialization)
- Check Railway logs for errors
- Try clicking "2. Start Browser" again

**VNC connection fails:**
- Verify Railway TCP Proxy is configured
- Check ENABLE_VNC=true in environment
- Verify port 5900 is accessible

**Buttons don't respond:**
- Check browser console for errors
- Verify API endpoints are working
- Check Railway logs for API errors

**Login confirmation fails:**
- Verify you're logged in to TradingView
- Check that browser is still running
- Try clicking "3. Confirm Login" again

