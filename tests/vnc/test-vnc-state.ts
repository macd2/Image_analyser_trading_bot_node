/**
 * VNC Login State Manager Tests
 * Tests state transitions and persistence
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { spawn } from 'child_process';
import path from 'path';

describe('VNC Login State Manager', () => {
  const pythonDir = path.join(process.cwd(), 'python');

  const runPythonCode = (code: string): Promise<string> => {
    return new Promise((resolve, reject) => {
      const process = spawn('python3', ['-c', code], { cwd: pythonDir });
      let output = '';
      let error = '';

      process.stdout.on('data', (data) => {
        output += data.toString();
      });

      process.stderr.on('data', (data) => {
        error += data.toString();
      });

      process.on('close', (code) => {
        if (code !== 0) {
          reject(new Error(`Python error: ${error}`));
        } else {
          resolve(output.trim());
        }
      });
    });
  };

  describe('State Transitions', () => {
    it('should set waiting_for_browser_open state', async () => {
      const code = `
from trading_bot.core.login_state_manager import set_waiting_for_browser_open, get_login_state
set_waiting_for_browser_open()
state = get_login_state()
print(state['state'])
`;
      const result = await runPythonCode(code);
      expect(result).toBe('waiting_for_browser_open');
    });

    it('should set browser_open_requested state', async () => {
      const code = `
from trading_bot.core.login_state_manager import set_browser_open_requested, get_login_state
set_browser_open_requested()
state = get_login_state()
print(state['state'])
`;
      const result = await runPythonCode(code);
      expect(result).toBe('browser_open_requested');
    });

    it('should set login_confirmed state', async () => {
      const code = `
from trading_bot.core.login_state_manager import set_login_confirmed, get_login_state
set_login_confirmed()
state = get_login_state()
print(state['state'])
`;
      const result = await runPythonCode(code);
      expect(result).toBe('login_confirmed');
    });

    it('should set idle state', async () => {
      const code = `
from trading_bot.core.login_state_manager import set_idle, get_login_state
set_idle()
state = get_login_state()
print(state['state'])
`;
      const result = await runPythonCode(code);
      expect(result).toBe('idle');
    });
  });

  describe('State Persistence', () => {
    it('should persist state to file', async () => {
      const code = `
from trading_bot.core.login_state_manager import set_waiting_for_browser_open, get_login_state
set_waiting_for_browser_open('Test message')
state = get_login_state()
print(f"{state['state']}|{state['message']}")
`;
      const result = await runPythonCode(code);
      expect(result).toContain('waiting_for_browser_open');
      expect(result).toContain('Test message');
    });

    it('should read persisted state', async () => {
      // First write
      await runPythonCode(`
from trading_bot.core.login_state_manager import set_browser_open_requested
set_browser_open_requested()
`);

      // Then read
      const code = `
from trading_bot.core.login_state_manager import get_login_state
state = get_login_state()
print(state['state'])
`;
      const result = await runPythonCode(code);
      expect(result).toBe('browser_open_requested');
    });
  });

  describe('State Checks', () => {
    it('should check if browser open is requested', async () => {
      const code = `
from trading_bot.core.login_state_manager import set_browser_open_requested, is_browser_open_requested
set_browser_open_requested()
result = is_browser_open_requested()
print('true' if result else 'false')
`;
      const result = await runPythonCode(code);
      expect(result).toBe('true');
    });

    it('should check if login is confirmed', async () => {
      const code = `
from trading_bot.core.login_state_manager import set_login_confirmed, is_login_confirmed
set_login_confirmed()
result = is_login_confirmed()
print('true' if result else 'false')
`;
      const result = await runPythonCode(code);
      expect(result).toBe('true');
    });
  });

  describe('VNC Mode Detection', () => {
    it('should support VNC-specific states', async () => {
      const code = `
from trading_bot.core.login_state_manager import LoginState
states = [
    LoginState.WAITING_FOR_BROWSER_OPEN,
    LoginState.BROWSER_OPEN_REQUESTED
]
for state in states:
    print(state)
`;
      const result = await runPythonCode(code);
      expect(result).toContain('waiting_for_browser_open');
      expect(result).toContain('browser_open_requested');
    });
  });
});

