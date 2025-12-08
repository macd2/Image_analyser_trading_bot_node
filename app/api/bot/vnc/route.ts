import { NextRequest, NextResponse } from 'next/server';
import { spawn, ChildProcess } from 'child_process';
import path from 'path';

// Store browser process reference
let browserProcess: ChildProcess | null = null;

const PYTHON_PATH = path.join(process.cwd(), 'python');
const BROWSER_SCRIPT = path.join(PYTHON_PATH, 'vnc_browser.py');

export async function GET() {
  return NextResponse.json({
    running: browserProcess !== null && !browserProcess.killed,
    mode: 'interactive',
    message: browserProcess ? 'Browser window is open - check your desktop' : 'No browser running',
  });
}

export async function POST(request: NextRequest) {
  // Get action from URL params (primary) or body (fallback)
  const { searchParams } = new URL(request.url);
  let action = searchParams.get('action') || 'start';

  // Try to parse body only if no URL action
  if (!searchParams.has('action')) {
    try {
      const body = await request.text();
      if (body && body.trim()) {
        const json = JSON.parse(body);
        action = json.action || 'start';
      }
    } catch {
      // Ignore parse errors, use default
    }
  }

  if (action === 'start') {
    if (browserProcess && !browserProcess.killed) {
      return NextResponse.json({
        success: false,
        error: 'Interactive browser already running'
      });
    }

    try {
      console.log('Starting interactive browser...');

      // Launch browser with visible window (non-headless)
      browserProcess = spawn('python3', [BROWSER_SCRIPT], {
        cwd: PYTHON_PATH,
        env: {
          ...process.env,
          DISPLAY: process.env.DISPLAY || ':0',  // Use default display
          PYTHONUNBUFFERED: '1',  // Force unbuffered output for real-time logs
        },
        stdio: ['ignore', 'pipe', 'pipe'],
        detached: false,
      });

      // Log output
      browserProcess.stdout?.on('data', (data) => {
        console.log(`Browser: ${data.toString()}`);
      });
      browserProcess.stderr?.on('data', (data) => {
        console.error(`Browser Error: ${data.toString()}`);
      });

      browserProcess.on('exit', (code) => {
        console.log(`Interactive browser exited with code ${code}`);
        browserProcess = null;
      });

      // Wait for browser to start
      await new Promise(resolve => setTimeout(resolve, 3000));

      return NextResponse.json({
        success: true,
        message: 'Interactive browser started - check your desktop!',
      });
    } catch (error) {
      return NextResponse.json({
        success: false,
        error: String(error)
      }, { status: 500 });
    }
  }

  if (action === 'stop') {
    if (browserProcess) {
      browserProcess.kill('SIGTERM');
      browserProcess = null;
      return NextResponse.json({ success: true, message: 'Interactive browser stopped' });
    }
    return NextResponse.json({ success: false, error: 'No browser running' });
  }

  return NextResponse.json({ error: 'Invalid action' }, { status: 400 });
}

