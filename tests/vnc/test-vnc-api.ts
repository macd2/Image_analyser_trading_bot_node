/**
 * VNC API Endpoint Tests
 * Tests individual API endpoints in isolation
 */

import { describe, it, expect } from 'vitest';

describe('VNC API Endpoints', () => {
  const API_BASE = 'http://localhost:3000/api';

  describe('POST /api/vnc/control', () => {
    it('should accept start action', async () => {
      const response = await fetch(`${API_BASE}/vnc/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'start' })
      });

      expect(response.ok).toBe(true);
      const data = await response.json();
      expect(data.success).toBe(true);
      expect(data.action).toBe('start');
    });

    it('should accept stop action', async () => {
      const response = await fetch(`${API_BASE}/vnc/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'stop' })
      });

      expect(response.ok).toBe(true);
      const data = await response.json();
      expect(data.success).toBe(true);
      expect(data.action).toBe('stop');
    });

    it('should accept restart action', async () => {
      const response = await fetch(`${API_BASE}/vnc/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'restart' })
      });

      expect(response.ok).toBe(true);
      const data = await response.json();
      expect(data.success).toBe(true);
      expect(data.action).toBe('restart');
    });

    it('should accept status action', async () => {
      const response = await fetch(`${API_BASE}/vnc/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'status' })
      });

      expect(response.ok).toBe(true);
      const data = await response.json();
      expect(data.success).toBe(true);
      expect(data.action).toBe('status');
    });

    it('should reject invalid action', async () => {
      const response = await fetch(`${API_BASE}/vnc/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'invalid' })
      });

      expect(response.status).toBe(400);
      const data = await response.json();
      expect(data.success).toBe(false);
    });
  });

  describe('GET /api/vnc/status', () => {
    it('should return VNC status', async () => {
      const response = await fetch(`${API_BASE}/vnc/status`);

      expect(response.ok).toBe(true);
      const data = await response.json();
      expect(data).toHaveProperty('available');
      expect(data).toHaveProperty('enableVnc');
      expect(data).toHaveProperty('message');
    });

    it('should include connection info when available', async () => {
      const response = await fetch(`${API_BASE}/vnc/status`);
      const data = await response.json();

      if (data.available) {
        expect(data).toHaveProperty('vncUrl');
        expect(data).toHaveProperty('vncPort');
      }
    });
  });

  describe('POST /api/vnc/browser-ready', () => {
    it('should accept browser ready signal', async () => {
      const response = await fetch(`${API_BASE}/vnc/browser-ready`, {
        method: 'POST'
      });

      expect(response.ok).toBe(true);
      const data = await response.json();
      expect(data.success).toBe(true);
    });

    it('should allow multiple browser ready signals', async () => {
      for (let i = 0; i < 3; i++) {
        const response = await fetch(`${API_BASE}/vnc/browser-ready`, {
          method: 'POST'
        });
        expect(response.ok).toBe(true);
      }
    });
  });

  describe('POST /api/bot/login - confirm_login', () => {
    it('should accept confirm_login action', async () => {
      const response = await fetch(`${API_BASE}/bot/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'confirm_login' })
      });

      // Should succeed or fail gracefully (depends on state)
      expect(response.status).toBeGreaterThanOrEqual(200);
      expect(response.status).toBeLessThan(500);
    });

    it('should allow multiple confirm_login calls', async () => {
      for (let i = 0; i < 3; i++) {
        const response = await fetch(`${API_BASE}/bot/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'confirm_login' })
        });
        expect(response.status).toBeGreaterThanOrEqual(200);
        expect(response.status).toBeLessThan(500);
      }
    });
  });
});

