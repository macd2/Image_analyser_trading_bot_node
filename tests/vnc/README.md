# VNC Integration Tests

Dedicated test suite for VNC functionality in isolation.

## Test Structure

```
tests/vnc/
├── README.md (this file)
├── test-vnc-flow.ts (Main VNC flow test)
├── test-vnc-api.ts (API endpoint tests)
├── test-vnc-modal.tsx (React modal component tests)
└── test-vnc-state.ts (Login state manager tests)
```

## Running Tests

```bash
# Run all VNC tests
npm test -- tests/vnc

# Run specific test file
npm test -- tests/vnc/test-vnc-flow.ts

# Run with verbose output
npm test -- tests/vnc --verbose

# Run with coverage
npm test -- tests/vnc --coverage
```

## Test Scenarios

### 1. VNC Flow Test (`test-vnc-flow.ts`)
- Start VNC services
- Start browser
- Confirm login
- Kill VNC
- Test recovery from browser crash
- Test multiple button clicks

### 2. VNC API Test (`test-vnc-api.ts`)
- POST /api/vnc/control (start/stop/restart)
- GET /api/vnc/status
- POST /api/vnc/browser-ready
- Error handling

### 3. VNC Modal Test (`test-vnc-modal.tsx`)
- Modal renders correctly
- All 4 buttons are always clickable
- No disabled states
- Loading states show spinner
- VNC status indicator updates

### 4. Login State Test (`test-vnc-state.ts`)
- State transitions work correctly
- File-based state persistence
- Python integration

## Key Requirements

✅ ALL buttons MUST be functional at ALL times
✅ No disabled states on any button
✅ Buttons show loading spinner but remain clickable
✅ Each button can be clicked multiple times
✅ Browser crash recovery works
✅ VNC status indicator updates correctly

