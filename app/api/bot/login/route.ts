/**
 * Bot Login State API - Manages manual login flow for TradingView
 * 
 * GET - Returns current login state
 * POST - Actions: confirm_login, open_browser, reset
 */

import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

// State file path - matches Python login_state_manager.py
const STATE_FILE = path.join(process.cwd(), 'python', 'trading_bot', 'data', 'login_state.json');

interface LoginState {
  state: 'idle' | 'waiting_for_login' | 'login_confirmed' | 'browser_opened';
  message: string | null;
  timestamp: string | null;
  browser_opened: boolean;
}

interface LoginAction {
  action: 'confirm_login' | 'open_browser' | 'reset';
}

function getLoginState(): LoginState {
  try {
    if (fs.existsSync(STATE_FILE)) {
      const data = fs.readFileSync(STATE_FILE, 'utf-8');
      return JSON.parse(data);
    }
  } catch (error) {
    console.error('Error reading login state:', error);
  }
  
  // Default state
  return {
    state: 'idle',
    message: null,
    timestamp: null,
    browser_opened: false
  };
}

function setLoginState(state: Partial<LoginState>): void {
  try {
    // Ensure directory exists
    const dir = path.dirname(STATE_FILE);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    
    const currentState = getLoginState();
    const newState = {
      ...currentState,
      ...state,
      timestamp: new Date().toISOString()
    };
    
    fs.writeFileSync(STATE_FILE, JSON.stringify(newState, null, 2));
  } catch (error) {
    console.error('Error writing login state:', error);
  }
}

/**
 * GET /api/bot/login - Get current login state
 */
export async function GET() {
  const state = getLoginState();
  
  return NextResponse.json({
    success: true,
    ...state,
    requires_action: state.state === 'waiting_for_login',
    can_confirm: state.state === 'waiting_for_login' && state.browser_opened
  });
}

/**
 * POST /api/bot/login - Perform login action
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json() as LoginAction;
    const { action } = body;
    
    const currentState = getLoginState();
    
    switch (action) {
      case 'confirm_login':
        // User clicked "Confirm Login" - signal bot to verify and continue
        if (currentState.state !== 'waiting_for_login') {
          return NextResponse.json({
            success: false,
            message: 'Not waiting for login confirmation'
          }, { status: 400 });
        }
        
        setLoginState({
          state: 'login_confirmed',
          message: 'Login confirmed by user - verifying...'
        });
        
        return NextResponse.json({
          success: true,
          message: 'Login confirmation sent to bot'
        });
        
      case 'reset':
        // Reset to idle state
        setLoginState({
          state: 'idle',
          message: null,
          browser_opened: false
        });
        
        return NextResponse.json({
          success: true,
          message: 'Login state reset'
        });
        
      default:
        return NextResponse.json({
          success: false,
          message: `Invalid action: ${action}`
        }, { status: 400 });
    }
  } catch (error) {
    console.error('Login POST error:', error);
    return NextResponse.json({
      success: false,
      message: 'Failed to execute login action'
    }, { status: 500 });
  }
}

