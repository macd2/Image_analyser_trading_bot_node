#!/bin/bash

# VNC Test Runner
# Runs all VNC tests with proper setup and reporting

set -e

echo "🧪 VNC Integration Test Suite"
echo "=============================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running in test environment
if [ "$NODE_ENV" != "test" ]; then
    echo -e "${YELLOW}⚠️  NODE_ENV is not 'test'. Setting to test mode...${NC}"
    export NODE_ENV=test
fi

# Check if ENABLE_VNC is set
if [ "$ENABLE_VNC" != "true" ]; then
    echo -e "${YELLOW}⚠️  ENABLE_VNC is not 'true'. Setting for tests...${NC}"
    export ENABLE_VNC=true
fi

echo -e "${GREEN}✓${NC} Environment configured"
echo ""

# Run tests
echo "Running VNC Flow Tests..."
npm test -- tests/vnc/test-vnc-flow.ts --run
echo ""

echo "Running VNC API Tests..."
npm test -- tests/vnc/test-vnc-api.ts --run
echo ""

echo "Running VNC Modal Tests..."
npm test -- tests/vnc/test-vnc-modal.tsx --run
echo ""

echo "Running VNC State Tests..."
npm test -- tests/vnc/test-vnc-state.ts --run
echo ""

echo -e "${GREEN}✅ All VNC tests completed!${NC}"
echo ""
echo "📋 Test Summary:"
echo "  - VNC Flow: Complete login flow"
echo "  - VNC API: Individual endpoint tests"
echo "  - VNC Modal: React component tests"
echo "  - VNC State: State manager tests"
echo ""
echo "📖 For manual testing, see: tests/vnc/MANUAL_TEST_GUIDE.md"

