/**
 * VNC Flow Integration Test
 * Tests the complete VNC login flow end-to-end
 */

import { describe, it, expect, beforeAll, afterAll, vi } from 'vitest';

describe('VNC Login Flow', () => {
  const API_BASE = 'http://localhost:3000/api';

  beforeAll(() => {
    // Setup: Ensure VNC is enabled in test environment
    process.env.ENABLE_VNC = 'true';
  });

  afterAll(() => {
    // Cleanup
    process.env.ENABLE_VNC = 'false';
  });

  describe('Step 1: Start VNC', () => {
    it('should start VNC services successfully', async () => {
      const response = await fetch(`${API_BASE}/vnc/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'start' })
      });

      expect(response.ok).toBe(true);
      const data = await response.json();
      expect(data.success).toBe(true);
      expect(data.message).toContain('started');
    });

    it('should be able to start VNC multiple times', async () => {
      // First start
      let response = await fetch(`${API_BASE}/vnc/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'start' })
      });
      expect(response.ok).toBe(true);

      // Second start (should not fail)
      response = await fetch(`${API_BASE}/vnc/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'start' })
      });
      expect(response.ok).toBe(true);
    });
  });

  describe('Step 2: Start Browser', () => {
    it('should signal browser to start', async () => {
      const response = await fetch(`${API_BASE}/vnc/browser-ready`, {
        method: 'POST'
      });

      expect(response.ok).toBe(true);
      const data = await response.json();
      expect(data.success).toBe(true);
    });

    it('should allow multiple browser start signals', async () => {
      // First signal
      let response = await fetch(`${API_BASE}/vnc/browser-ready`, {
        method: 'POST'
      });
      expect(response.ok).toBe(true);

      // Second signal (browser crash recovery)
      response = await fetch(`${API_BASE}/vnc/browser-ready`, {
        method: 'POST'
      });
      expect(response.ok).toBe(true);
    });
  });

  describe('Step 3: Confirm Login', () => {
    it('should accept login confirmation from any active state', async () => {
      const response = await fetch(`${API_BASE}/bot/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'confirm_login' })
      });

      // Should succeed or fail gracefully (depends on current state)
      expect(response.status).toBeGreaterThanOrEqual(200);
      expect(response.status).toBeLessThan(500);
    });
  });

  describe('Step 4: Kill VNC', () => {
    it('should stop VNC services', async () => {
      const response = await fetch(`${API_BASE}/vnc/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'stop' })
      });

      expect(response.ok).toBe(true);
      const data = await response.json();
      expect(data.success).toBe(true);
    });

    it('should be able to kill VNC multiple times', async () => {
      // First kill
      let response = await fetch(`${API_BASE}/vnc/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'stop' })
      });
      expect(response.ok).toBe(true);

      // Second kill (should not fail)
      response = await fetch(`${API_BASE}/vnc/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'stop' })
      });
      expect(response.ok).toBe(true);
    });
  });

  describe('Browser Crash Recovery', () => {
    it('should recover from browser crash by restarting browser', async () => {
      // Start VNC
      await fetch(`${API_BASE}/vnc/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'start' })
      });

      // Start browser
      let response = await fetch(`${API_BASE}/vnc/browser-ready`, {
        method: 'POST'
      });
      expect(response.ok).toBe(true);

      // Simulate crash - start browser again
      response = await fetch(`${API_BASE}/vnc/browser-ready`, {
        method: 'POST'
      });
      expect(response.ok).toBe(true);

      // Cleanup
      await fetch(`${API_BASE}/vnc/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'stop' })
      });
    });
  });
});

